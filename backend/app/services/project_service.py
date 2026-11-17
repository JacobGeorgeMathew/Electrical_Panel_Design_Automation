"""Application orchestration: short database units of work around the pure engine."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import insert, select, update
from app.algorithms.layout_config import LayoutConfig, LayoutWeights
from app.models.cem import CanonicalEngineeringModel
from app.models.pdm import PhysicalDesignModel, DesignValidationPolicy
from app.persistence import models as m
from app.persistence.assets import AssetStore, AssetUnavailable, content_hash, primitive_glb
from app.persistence.parameters import resolve_parameters
from app.persistence.repositories import (CatalogRepository, ProjectRepository, PersistenceError,
    MemoryComponents, MemoryProjects, MemoryEnclosures, identifier, serial)
from app.persistence.revisions import write_revision
from app.persistence.documents import DocumentRepository
from app.persistence.revision_outputs import prepare_outputs
from app.services.requirement_engine import RequirementEngine
from app.services.orchestrator import DesignOrchestrator
from app.services.cad_engine import CADEngine
from app.services.schematic_engine import SchematicEngine
from app.services.change_propagation import ChangePropagationEngine
from app.services.design_errors import DesignError
from app.services.panel_assembly import assembly_bom
from app.services.revision_reader import RevisionReader

ENGINE_VERSION='db-pipeline-4'


class ProjectService:
    def __init__(self,database,executor=None):
        self.db=database
        self.assets=AssetStore(database.settings.asset_root)
        self.executor=executor

    @staticmethod
    def validate(template,project_id,values):
        if template['archetype']!='DB':
            raise PersistenceError('UNSUPPORTED_ARCHETYPE','Only the DB engineering pipeline is implemented.')
        reqs=RequirementEngine(templates={'DB':template}).validate_requirements(project_id,'DB',values)
        if not reqs.is_valid:
            raise DesignError('INVALID_REQUIREMENTS','Requirements must be corrected before saving.',errors=reqs.validation_errors)
        return reqs

    def create(self,data):
        with self.db.sessions.begin() as s:
            catalog=CatalogRepository(s,self.assets)
            template=catalog.template(data.archetype,data.archetype_version_id)
            repo=ProjectRepository(s)
            if data.id and s.scalar(select(m.projects.c.id).where(m.projects.c.project_code==data.id)):
                raise PersistenceError('PROJECT_EXISTS','Project identifier already exists.',409)
            pid=repo.create(data.name,template['archetype_version_id'],data.id)
            row=repo.row(pid)
            s.execute(update(m.projects).where(m.projects.c.id==row['id']).values(description=data.description,location=data.location,last_opened_at=datetime.now(timezone.utc)))
            reqs=self.validate(template,pid,data.requirements)
            repo.save_requirements(row,template,reqs,data.requirements)
            from app.services.document_service import DocumentService
            DocumentService.create_empty(s, row, template)
            return repo.get(pid)

    def update(self,key,data):
        with self.db.sessions.begin() as s:
            repo=ProjectRepository(s);row=repo.check_version(key,data.expected_version)
            if data.expected_recovery_version is not None and row['recovery_version']!=data.expected_recovery_version:
                raise PersistenceError('RECOVERY_CONFLICT','Another session changed this project recovery checkpoint. Reopen before saving.',409)
            if data.requirements is None and data.configuration is None and data.workspace is None:
                changes={field:getattr(data,field) for field in ('name','description','location') if getattr(data,field) is not None}
                repo.touch(row,**changes)
                return repo.get(key)
            project=repo.get(key)
            catalog=CatalogRepository(s,self.assets)
            template=catalog.template(project['archetype'],project['archetype_version_id'])
            values={**project['requirements'],**data.requirements} if data.requirements is not None else project['requirements']
            reqs=self.validate(template,project['id'],values)
            if data.configuration is not None:
                self.configure_enclosures(catalog.enclosures(),data.configuration)
            repo.save_requirements(row,template,reqs,values)
            changes={}
            if data.name is not None: changes['name']=data.name
            if data.configuration is not None: changes['configuration']=data.configuration
            for field in ('description','location','workspace'):
                if getattr(data,field) is not None: changes[field]=getattr(data,field)
            changes.update(recovery=None,recovery_version=row['recovery_version']+1)
            repo.touch(row,**changes)
            return repo.get(key)

    def configure_enclosures(self,enclosures,configuration):
        rows=deepcopy(enclosures)
        selected=configuration.get('enclosure_id')
        supplied=configuration.get('enclosure_parameters',{})
        if supplied and not selected:
            raise PersistenceError('INVALID_CONFIGURATION','Select an enclosure before overriding its parameters.')
        if selected:
            enclosure=next((r for r in rows if r['id']==selected),None)
            if not enclosure: raise PersistenceError('ENCLOSURE_NOT_FOUND','Selected enclosure is unavailable.',404)
            models=enclosure['parameters']
            if not models: raise PersistenceError('CAD_MODEL_UNAVAILABLE','No configurable enclosure model is available.')
            values=resolve_parameters(models[0]['parameters'],supplied)
            old_w,old_h=enclosure['width'],enclosure['height']
            enclosure['width'],enclosure['height'],enclosure['depth']=[values[k+'_mm'] for k in ('width','height','depth')]
            enclosure['mounting_plate_width']+=enclosure['width']-old_w
            enclosure['mounting_plate_height']+=enclosure['height']-old_h
            if enclosure['mounting_plate_width']<=0 or enclosure['mounting_plate_height']<=0 or enclosure['depth']<=enclosure['mounting_plate_offset_z']:
                raise PersistenceError('INVALID_CONFIGURATION','Configured enclosure cannot contain its mounting plate.')
        return rows,selected

    def _inputs(self,key,*,resolve_capabilities=True):
        # All DB reads end here, before optimization or geometry generation begins.
        with self.db.sessions() as s:
            project=ProjectRepository(s).get(key)
            project['_source_document']=DocumentRepository(s).load(ProjectRepository(s).row(key)).model_dump(mode='json')
            catalog=CatalogRepository(s,self.assets)
            template=catalog.template(project['archetype'],project['archetype_version_id'],resolve_capabilities=resolve_capabilities)
            rows=catalog.engine_catalog()
            enclosures=catalog.enclosures()
            templates=catalog.electrical_templates(template['archetype_version_id'])
            rs=s.scalar(select(m.rule_set_versions.c.id).join(m.rule_sets,m.rule_sets.c.id==m.rule_set_versions.c.rule_set_id)
                .where(m.rule_sets.c.code=='DB_ENGINE_V1',m.rule_set_versions.c.status=='PUBLISHED').order_by(m.rule_set_versions.c.version_no.desc()))
            rules=catalog.rules(str(rs)) if rs else []
            component_models={r['id']:catalog.cad_models(r['component_version_id']) for r in rows}
            hardware=catalog.hardware_catalog()
        layout_data=next((r['parameters']['layout_config'] for r in rules if r['code']=='DB_LAYOUT_CONFIG'),None)
        if not layout_data or rs is None:
            raise PersistenceError('CATALOG_NOT_INITIALIZED','Import the application catalog and rules before generating a design.',503)
        layout_data=deepcopy(layout_data)
        layout_data['weights']=LayoutWeights(**layout_data['weights'])
        for field in ('din_categories','plate_categories'): layout_data[field]=set(layout_data[field])
        layout=LayoutConfig(**layout_data)
        policy_data=next((r['parameters'] for r in rules if r['code']=='DB_CONSTRAINT_POLICY'),None)
        if policy_data is None:
            raise PersistenceError('CONSTRAINT_POLICY_NOT_INITIALIZED','Apply migrations and run seed-constraints before generating a design.',503)
        policy=DesignValidationPolicy(**policy_data)
        layout.device_gap_x=policy.din_clearance_mm
        layout.plate_clearance=policy.plate_clearance_mm
        layout.wire_clearance=policy.wire_clearance_mm
        layout.thermal_density_limit_w_per_l=policy.thermal_density_limit_w_per_l
        return project,template,rows,enclosures,component_models,templates,rules,str(rs),layout,hardware

    def generate(self,key,overrides=None,expected_version=None,configuration=None,*,propose=False):
        project,template,rows,enclosures,models,templates,rules,rsv,layout,hardware=self._inputs(key)
        source_document=project['_source_document']['document']
        if not propose and (source_document['document_sequence'] > 0
                or project['_source_document']['snapshots']['cem'] is not None
                or source_document.get('generation_intent')):
            raise PersistenceError('GENERATION_PROPOSAL_REQUIRED',
                'Use a generation proposal and explicit acceptance for this working document.',409)
        if configuration is not None:
            project['configuration']=configuration
        if expected_version is not None and expected_version!=project['lock_version']:
            raise PersistenceError('REVISION_CONFLICT','Project changed. Reopen it before generation.',409)
        if propose:
            source=project['_source_document']
            project['requirements']={r['id']:r['value'] for r in source['snapshots']['requirements']['items'] if r['value'] is not None}
            project['configuration']=source['document']['configuration']
        values={**project['requirements'],**(overrides or {})}
        reqs=self.validate(template,project['id'],values)
        enclosures,selected=self.configure_enclosures(enclosures,project['configuration'])
        engine=DesignOrchestrator(project_repo=MemoryProjects(project),comp_repo=MemoryComponents(rows),
            enclosure_repo=MemoryEnclosures(enclosures,selected),req_engine=RequirementEngine(templates={'DB':template}),layout_config=layout,hardware_catalog=hardware)
        result=engine.generate_design(project['id'],values,persist_requirements=False)
        by_code={r['id']:r for r in rows}
        for c in result['cem']['components']:
            source=by_code[c['catalog_id']]
            c['component_version_id']=source['component_version_id']
            c['product_version_id']=source['product_version_id']
            model=next(iter(models.get(c['catalog_id'],[])),None)
            c['cad_model_version_id']=model['id'] if model else None
            part=next(p for p in result['pdm']['components'] if p['cem_component_id']==c['id'])
            part['cad_model_version_id']=c['cad_model_version_id']
            part['preview_asset']=next((a for a in model['assets'] if a['file_format']=='GLB'),None) if model else None
        enclosure=next(r for r in enclosures if r['id']==result['pdm']['enclosure_id'])
        enc_model=next(iter(enclosure['parameters']),None)
        manifest={'engine_version':ENGINE_VERSION,'archetype_version_id':template['archetype_version_id'],
            'questionnaire_version_id':template['questionnaire_version_id'],'electrical_templates':templates,
            'rule_set_version_id':rsv,'validation_rule_versions':{r['code'].removeprefix('VALIDATION_'):r['id'] for r in rules if r['code'].startswith('VALIDATION_')},
            'rule_versions':[r['id'] for r in rules],'layout_config':serial({**layout.__dict__,'weights':layout.weights.__dict__,
                'din_categories':sorted(layout.din_categories),'plate_categories':sorted(layout.plate_categories)}),
            'component_versions':{c['id']:c['component_version_id'] for c in result['cem']['components']},
            'product_versions':{c['id']:c['product_version_id'] for c in result['cem']['components']},
            'cad_model_versions':{c['id']:c['cad_model_version_id'] for c in result['cem']['components']},
            'enclosure_component_version_id':enclosure['component_version_id'],'enclosure_cad_model_version_id':enc_model['id'] if enc_model else None,
            'hardware_component_versions':{h['code']:h['component_version_id'] for h in hardware},
            'validation_policy_version':result['pdm']['validation_policy']['version'],
            'generator':{'name':'panelstudio-primitives','version':'3'},'input_sha256':content_hash({'requirements':values,'configuration':project['configuration']})}
        if propose:
            return project['_source_document'],reqs,result,manifest
        files=self.generate_files(result)
        outputs=prepare_outputs(project,reqs,values,result,manifest,files,
            project['_source_document'],self.assets,project['lock_version'])
        with self.db.sessions.begin() as s:
            saved=write_revision(s,project,template,reqs,values,result,manifest,files,project['lock_version'],outputs=outputs)
        return self.load_revision(project['id'],saved['revision_id'])

    def generate_files(self,result):
        preview=self.assets.put(primitive_glb(result['cad']['primitives'],generator_version='3'),'glb')
        script=self.assets.put(CADEngine().export_freecad_script(PhysicalDesignModel(**result['pdm'])).encode('utf-8'),'py')
        return [{**preview,'artifact_type':'CAD_PREVIEW','file_format':'GLB','generator_name':'panelstudio-primitives','generator_version':'3'},
                {**script,'artifact_type':'FREECAD_SCRIPT','file_format':'PY','generator_name':'existing-freecad-script','generator_version':ENGINE_VERSION}]

    def load_revision(self,key,revision_id=None):
        return RevisionReader(self.db,self.assets,ENGINE_VERSION).read(key,revision_id)

    def convert_revision(self,key,revision_id,expected_version):
        """Explicitly create new outputs from legacy models; never backfill history."""
        return self.restore(key,revision_id,expected_version,compatibility_conversion=True)

    def restore(self,key,revision_id,expected_version,*,compatibility_conversion=False):
        result=self.load_revision(key,revision_id)
        if result['missing_outputs'] and not compatibility_conversion:
            raise PersistenceError('REVISION_OUTPUT_MISSING',
                'Legacy outputs are missing. Explicit compatibility conversion creates a new revision.',409)
        if compatibility_conversion:
            if not result['missing_outputs']:
                raise PersistenceError('CONVERSION_NOT_REQUIRED','This revision already has complete outputs.',409)
            cem_model,pdm_model=CanonicalEngineeringModel(**result['cem']),PhysicalDesignModel(**result['pdm'])
            result.update(schematic=SchematicEngine().generate_schematic_data(cem_model),
                cad=CADEngine().generate_parametric_geometry(pdm_model),bom=assembly_bom(cem_model,pdm_model))
        with self.db.sessions() as s:
            repo=ProjectRepository(s);project=repo.get(key)
            source=DocumentRepository(s).load(repo.row(key)).model_dump(mode='json')
            template=CatalogRepository(s,self.assets).template(project['archetype'],result['manifest']['archetype_version_id'])
            stored=s.execute(select(m.generated_artifacts).where(m.generated_artifacts.c.project_revision_id==identifier(revision_id),m.generated_artifacts.c.generation_status=='READY')).mappings().all()
            if result['output_manifest'] is not None:
                original_ids={a['id'] for a in result['output_manifest']['artifacts']}
                stored=[a for a in stored if str(a['id']) in original_ids]
            files=[{k:a[k] for k in ('artifact_type','file_format','storage_backend','storage_key','sha256','byte_size','generator_name','generator_version')} for a in stored]
            requirement_ids=list(s.scalars(select(m.project_requirements.c.id).where(m.project_requirements.c.project_revision_id==identifier(revision_id))))
            historic_answers=repo.answer_values(requirement_ids)
        values={r['id']:r['value'] for r in result['cem']['requirements'] if r['value'] is not None}
        values.update(historic_answers)
        reqs=self.validate(template,project['id'],values)
        project['configuration']=result['manifest'].get('configuration',{})
        manifest={**result['manifest'],'restored_from_revision_id':revision_id}
        manifest['input_sha256']=content_hash({'requirements':values,'configuration':project['configuration']})
        if compatibility_conversion:
            manifest.update(engine_version=ENGINE_VERSION,generator={'name':'panelstudio-primitives','version':'3'},
                compatibility_converted_from_revision_id=revision_id)
            files=self.generate_files(result)
        outputs=prepare_outputs(project,reqs,values,result,manifest,files,source,self.assets,expected_version)
        with self.db.sessions.begin() as s:
            saved=write_revision(s,project,template,reqs,values,result,manifest,files,expected_version,outputs=outputs)
        return self.load_revision(key,saved['revision_id'])

    def propagate(self,key,field,value,expected_version=None):
        from app.services.recompute import preview_change
        return preview_change(self,key,field,value,expected_version)

    def list_artifacts(self,key):
        with self.db.sessions() as s:
            project=ProjectRepository(s).row(key)
            catalog=CatalogRepository(s,self.assets)
            rows=s.execute(select(m.generated_artifacts).join(m.project_revisions,m.project_revisions.c.id==m.generated_artifacts.c.project_revision_id)
                .where(m.project_revisions.c.project_id==project['id']).order_by(m.generated_artifacts.c.created_at.desc())).mappings()
            return [catalog.asset_dto(a,True) for a in rows]

    def queue_artifact(self,key,file_format,expected_version):
        file_format='PY' if file_format=='FREECAD_SCRIPT' else file_format
        result=self.load_revision(key)
        if result['manifest'].get('generator')!={'name':'panelstudio-primitives','version':'3'} or result['manifest'].get('engine_version')!=ENGINE_VERSION:
            raise PersistenceError('GENERATOR_VERSION_UNAVAILABLE','This saved revision requires a different CAD generator version.',409)
        if result['is_stale'] or result['lock_version']!=expected_version:
            raise PersistenceError('REVISION_CONFLICT','Generate a revision from the current requirements before exporting.',409)
        if self.executor is None: raise PersistenceError('GENERATOR_UNAVAILABLE','CAD worker is unavailable.',503)
        if file_format not in {'GLB','PY'}:
            raise PersistenceError('INVALID_JOB_INPUT','Unsupported export format.')
        from app.jobs.runner import KIND, signature
        from app.persistence.jobs import JobRepository
        from app.persistence.documents import document_hash
        with self.db.sessions.begin() as s:
            project=ProjectRepository(s).check_version(key,expected_version)
            source=DocumentRepository(s).load(project)
            if str(project['current_revision_id'])!=result['revision_id']:
                raise PersistenceError('REVISION_CONFLICT','Current revision changed.',409)
            inputs=dict(cad=result['cad'],pdm=result['pdm'],format=file_format,
                document_sha256=document_hash(source.document),lock_version=expected_version)
            intent=dict(format=file_format,generator_version='3' if file_format=='GLB' else ENGINE_VERSION)
            digest=signature(inputs,intent)
            job=JobRepository(s).enqueue(execution_key='cad:'+str(project['id'])+':'+digest,
                project_id=project['id'],document_id=source.document.document_id,
                base_sequence=source.document.document_sequence,kind=KIND,
                input_signature=digest,inputs=inputs,artifact_intent=intent,revision_id=result['revision_id'])
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            s.execute(pg_insert(m.generated_artifacts).values(id=job['id'],project_revision_id=identifier(result['revision_id']),artifact_type='CAD_PREVIEW' if file_format=='GLB' else 'FREECAD_SCRIPT',
                file_format='GLB' if file_format=='GLB' else 'PY',generator_name='panelstudio-primitives' if file_format=='GLB' else 'existing-freecad-script',generator_version='3' if file_format=='GLB' else ENGINE_VERSION,
                source_model_kind='PDM',source_model_sha256=content_hash(result['pdm']),generation_status='PENDING').on_conflict_do_nothing(index_elements=[m.generated_artifacts.c.id]))
        status={'QUEUED':'PENDING','RUNNING':'PENDING','SUCCEEDED':'READY'}.get(job['state'],'FAILED')
        return {'id':str(job['id']),'status':status,'project_revision_id':result['revision_id']}
