"""Application orchestration: short database units of work around the pure engine."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import insert, select, update
from app.algorithms.layout_config import LayoutConfig, LayoutWeights
from app.models.cem import CanonicalEngineeringModel
from app.models.pdm import PhysicalDesignModel
from app.persistence import models as m
from app.persistence.assets import AssetStore, AssetUnavailable, content_hash, primitive_glb
from app.persistence.parameters import resolve_parameters
from app.persistence.repositories import (CatalogRepository, ProjectRepository, PersistenceError,
    MemoryComponents, MemoryProjects, MemoryEnclosures, identifier, serial)
from app.persistence.revisions import write_revision
from app.services.requirement_engine import RequirementEngine
from app.services.orchestrator import DesignOrchestrator
from app.services.cad_engine import CADEngine
from app.services.schematic_engine import SchematicEngine
from app.services.change_propagation import ChangePropagationEngine
from app.services.design_errors import DesignError

ENGINE_VERSION='db-pipeline-1'


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
            reqs=self.validate(template,pid,data.requirements)
            repo.save_requirements(row,template,reqs,data.requirements)
            return repo.get(pid)

    def update(self,key,data):
        with self.db.sessions.begin() as s:
            repo=ProjectRepository(s);row=repo.check_version(key,data.expected_version)
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

    def _inputs(self,key):
        # All DB reads end here, before optimization or geometry generation begins.
        with self.db.sessions() as s:
            project=ProjectRepository(s).get(key)
            catalog=CatalogRepository(s,self.assets)
            template=catalog.template(project['archetype'],project['archetype_version_id'])
            rows=catalog.engine_catalog()
            enclosures=catalog.enclosures()
            templates=catalog.electrical_templates(template['archetype_version_id'])
            rs=s.scalar(select(m.rule_set_versions.c.id).join(m.rule_sets,m.rule_sets.c.id==m.rule_set_versions.c.rule_set_id)
                .where(m.rule_sets.c.code=='DB_ENGINE_V1',m.rule_set_versions.c.status=='PUBLISHED').order_by(m.rule_set_versions.c.version_no.desc()))
            rules=catalog.rules(str(rs)) if rs else []
            component_models={r['id']:catalog.cad_models(r['component_version_id']) for r in rows}
        layout_data=next((r['parameters']['layout_config'] for r in rules if r['code']=='DB_LAYOUT_CONFIG'),None)
        if not layout_data or rs is None:
            raise PersistenceError('CATALOG_NOT_INITIALIZED','Import the application catalog and rules before generating a design.',503)
        layout_data=deepcopy(layout_data)
        layout_data['weights']=LayoutWeights(**layout_data['weights'])
        for field in ('din_categories','plate_categories'): layout_data[field]=set(layout_data[field])
        layout=LayoutConfig(**layout_data)
        return project,template,rows,enclosures,component_models,templates,rules,str(rs),layout

    def generate(self,key,overrides=None,expected_version=None,configuration=None):
        project,template,rows,enclosures,models,templates,rules,rsv,layout=self._inputs(key)
        if configuration is not None:
            project['configuration']=configuration
        if expected_version is not None and expected_version!=project['lock_version']:
            raise PersistenceError('REVISION_CONFLICT','Project changed. Reopen it before generation.',409)
        values={**project['requirements'],**(overrides or {})}
        reqs=self.validate(template,project['id'],values)
        enclosures,selected=self.configure_enclosures(enclosures,project['configuration'])
        engine=DesignOrchestrator(project_repo=MemoryProjects(project),comp_repo=MemoryComponents(rows),
            enclosure_repo=MemoryEnclosures(enclosures,selected),req_engine=RequirementEngine(templates={'DB':template}),layout_config=layout)
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
            'cad_model_versions':{c['id']:c['cad_model_version_id'] for c in result['cem']['components']},
            'enclosure_component_version_id':enclosure['component_version_id'],'enclosure_cad_model_version_id':enc_model['id'] if enc_model else None,
            'generator':{'name':'panelstudio-primitives','version':'1'},'input_sha256':content_hash({'requirements':values,'configuration':project['configuration']})}
        files=self.generate_files(result)
        with self.db.sessions.begin() as s:
            saved=write_revision(s,project,template,reqs,values,result,manifest,files,project['lock_version'])
        return self.load_revision(project['id'],saved['revision_id'])

    def generate_files(self,result):
        preview=self.assets.put(primitive_glb(result['cad']['primitives']),'glb')
        script=self.assets.put(CADEngine().export_freecad_script(PhysicalDesignModel(**result['pdm'])).encode('utf-8'),'py')
        return [{**preview,'artifact_type':'CAD_PREVIEW','file_format':'GLB','generator_name':'panelstudio-primitives','generator_version':'1'},
                {**script,'artifact_type':'FREECAD_SCRIPT','file_format':'PY','generator_name':'existing-freecad-script','generator_version':ENGINE_VERSION}]

    def load_revision(self,key,revision_id=None):
        with self.db.sessions() as s:
            repo=ProjectRepository(s);project=repo.get(key)
            rid=identifier(revision_id or project['current_revision_id'])
            revision=s.execute(select(m.project_revisions).where(m.project_revisions.c.id==rid,m.project_revisions.c.project_id==identifier(project['database_id']))).mappings().first()
            if revision is None: raise PersistenceError('DESIGN_NOT_FOUND','No saved design revision was found.',404)
            cem=s.execute(select(m.cem_snapshots).where(m.cem_snapshots.c.project_revision_id==rid)).mappings().first()
            pdm=s.execute(select(m.pdm_snapshots).where(m.pdm_snapshots.c.project_revision_id==rid)).mappings().first()
            if not cem or not pdm: raise PersistenceError('DESIGN_NOT_FOUND','This revision has no complete CEM/PDM snapshots.',404)
            if content_hash(cem['snapshot'])!=cem['sha256'] or content_hash(pdm['snapshot'])!=pdm['sha256']:
                raise PersistenceError('SNAPSHOT_INTEGRITY','Saved snapshot integrity verification failed.',409)
            if content_hash({'cem':cem['sha256'],'pdm':pdm['sha256'],'manifest':revision['model_manifest']})!=revision['content_sha256']:
                raise PersistenceError('REVISION_INTEGRITY','Saved revision manifest integrity verification failed.',409)
            catalog=CatalogRepository(s,self.assets)
            artifacts=[catalog.asset_dto(a,True) for a in s.execute(select(m.generated_artifacts).where(m.generated_artifacts.c.project_revision_id==rid).order_by(m.generated_artifacts.c.created_at.desc())).mappings()]
            c,p=deepcopy(cem['snapshot']),deepcopy(pdm['snapshot'])
            manifest=revision['model_manifest']
        cem_model,pdm_model=CanonicalEngineeringModel(**c),PhysicalDesignModel(**p)
        return {'cem':c,'pdm':p,'schematic':SchematicEngine().generate_schematic_data(cem_model),'cad':CADEngine().generate_parametric_geometry(pdm_model),
            'bom':[{'component_id':v.id,'catalog_id':v.catalog_id,'name':v.name,'category':v.category,'quantity':v.quantity,
                    'current_rating_a':v.current_rating,'breaking_capacity_ka':v.breaking_capacity,'heat_loss_w':v.heat_loss} for v in cem_model.components],
            'validation_errors':p['validation_results'],'revision_id':str(rid),'revision_no':revision['revision_no'],'lock_version':project['lock_version'],
            'snapshot_sha256':revision['content_sha256'],'manifest':manifest,'artifacts':artifacts,
            'is_stale':project['current_revision_id']!=str(rid) or manifest.get('input_sha256')!=content_hash({
                'requirements':project['requirements'],'configuration':project['configuration']})}

    def restore(self,key,revision_id,expected_version):
        result=self.load_revision(key,revision_id)
        with self.db.sessions() as s:
            repo=ProjectRepository(s);project=repo.get(key)
            template=CatalogRepository(s,self.assets).template(project['archetype'],result['manifest']['archetype_version_id'])
            stored=s.execute(select(m.generated_artifacts).where(m.generated_artifacts.c.project_revision_id==identifier(revision_id),m.generated_artifacts.c.generation_status=='READY')).mappings().all()
            files=[{k:a[k] for k in ('artifact_type','file_format','storage_backend','storage_key','sha256','byte_size','generator_name','generator_version')} for a in stored]
            requirement_ids=list(s.scalars(select(m.project_requirements.c.id).where(m.project_requirements.c.project_revision_id==identifier(revision_id))))
            historic_answers=repo.answer_values(requirement_ids)
        values={r['id']:r['value'] for r in result['cem']['requirements'] if r['value'] is not None}
        values.update(historic_answers)
        reqs=self.validate(template,key,values)
        project['configuration']=result['manifest'].get('configuration',{})
        manifest={**result['manifest'],'restored_from_revision_id':revision_id}
        with self.db.sessions.begin() as s:
            saved=write_revision(s,project,template,reqs,values,result,manifest,files,expected_version)
        return self.load_revision(key,saved['revision_id'])

    def propagate(self,key,field,value,expected_version=None):
        with self.db.sessions() as s:
            project=ProjectRepository(s).get(key)
        old=self.load_revision(key)
        if field not in {q['id'] for q in self._inputs(key)[1]['questions']}:
            raise DesignError('INVALID_CHANGE','Unknown DB requirement.')
        version=project['lock_version'] if expected_version is None else expected_version
        new=self.generate(key,{field:value},version)
        return {'new_design':new,'diff_report':ChangePropagationEngine().compute_diff(old['cem'],new['cem'],old['pdm'],new['pdm'],field,
            old_values=project['requirements'],new_values={**project['requirements'],field:value})}

    def list_artifacts(self,key):
        with self.db.sessions() as s:
            project=ProjectRepository(s).row(key)
            catalog=CatalogRepository(s,self.assets)
            rows=s.execute(select(m.generated_artifacts).join(m.project_revisions,m.project_revisions.c.id==m.generated_artifacts.c.project_revision_id)
                .where(m.project_revisions.c.project_id==project['id']).order_by(m.generated_artifacts.c.created_at.desc())).mappings()
            return [catalog.asset_dto(a,True) for a in rows]

    def queue_artifact(self,key,file_format,expected_version):
        result=self.load_revision(key)
        if result['manifest'].get('generator')!={'name':'panelstudio-primitives','version':'1'} or result['manifest'].get('engine_version')!=ENGINE_VERSION:
            raise PersistenceError('GENERATOR_VERSION_UNAVAILABLE','This saved revision requires a different CAD generator version.',409)
        if result['is_stale'] or result['lock_version']!=expected_version:
            raise PersistenceError('REVISION_CONFLICT','Generate a revision from the current requirements before exporting.',409)
        if self.executor is None: raise PersistenceError('GENERATOR_UNAVAILABLE','CAD worker is unavailable.',503)
        job=uuid4()
        with self.db.sessions.begin() as s:
            ProjectRepository(s).check_version(key,expected_version)
            s.execute(insert(m.generated_artifacts).values(id=job,project_revision_id=identifier(result['revision_id']),artifact_type='CAD_PREVIEW' if file_format=='GLB' else 'FREECAD_SCRIPT',
                file_format='GLB' if file_format=='GLB' else 'PY',generator_name='panelstudio-primitives' if file_format=='GLB' else 'existing-freecad-script',generator_version='1' if file_format=='GLB' else ENGINE_VERSION,
                source_model_kind='PDM',source_model_sha256=content_hash(result['pdm']),generation_status='PENDING'))
        self.executor.submit(self._artifact_worker,key,result['revision_id'],str(job),file_format)
        return {'id':str(job),'status':'PENDING','project_revision_id':result['revision_id']}

    def _artifact_worker(self,key,rid,job,file_format):
        try:
            result=self.load_revision(key,rid)
            data=primitive_glb(result['cad']['primitives']) if file_format=='GLB' else CADEngine().export_freecad_script(PhysicalDesignModel(**result['pdm'])).encode()
            file=self.assets.put(data,'glb' if file_format=='GLB' else 'py')
            with self.db.sessions.begin() as s:
                s.execute(update(m.generated_artifacts).where(m.generated_artifacts.c.id==identifier(job),m.generated_artifacts.c.generation_status=='PENDING')
                    .values(**file,generation_status='READY',completed_at=datetime.now(timezone.utc)))
        except Exception:
            with self.db.sessions.begin() as s:
                s.execute(update(m.generated_artifacts).where(m.generated_artifacts.c.id==identifier(job)).values(
                    generation_status='FAILED',error={'code':'GENERATION_FAILED','message':'Generation failed; regenerate this saved revision.'},completed_at=datetime.now(timezone.utc)))
