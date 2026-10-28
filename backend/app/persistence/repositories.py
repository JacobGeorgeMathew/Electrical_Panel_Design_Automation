"""SQLAlchemy repositories expose dictionaries/domain DTOs, never ORM sessions."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, exists, func, insert, or_, select, update
from app.persistence import models as m
from app.persistence.assets import AssetStore


class PersistenceError(RuntimeError):
    def __init__(self, code, message, status=422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def serial(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: serial(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [serial(v) for v in value]
    return value


def identifier(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


class ComponentCatalog(Protocol):
    def get_by_id(self, component_id: str) -> dict | None: ...
    def filter_candidates(self, category: str, min_current: float = 0,
                          min_breaking_capacity: float = 0, poles: int | None = None) -> list[dict]: ...


class CatalogRepository:
    def __init__(self, session, assets: AssetStore):
        self.s, self.assets = session, assets

    def _query(self):
        c,v=m.components,m.component_versions
        latest=select(func.max(m.component_versions.c.version_no)).where(
            m.component_versions.c.component_id==c.c.id, m.component_versions.c.status=='PUBLISHED').correlate(c).scalar_subquery()
        return select(c.c.id.label('component_id'),c.c.code,c.c.name,c.c.category_code,c.c.component_kind,v).join(
            v,c.c.id==v.c.component_id).where(v.c.version_no==latest,v.c.status=='PUBLISHED')

    def _component(self, row):
        if row is None:
            return None
        row=dict(row)
        v_id=row['id']
        terminals=[]
        for terminal in self.s.execute(select(m.component_terminals).where(m.component_terminals.c.component_version_id==v_id)).mappings():
            xyz=terminal['coordinate_mm'] or {}
            terminals.append({'id':terminal['code'],'label':terminal['code'],'type':terminal['electrical_role'] or 'POWER',
                              **xyz,'connection_type':terminal['connection_type'],
                              'conductor_min_mm2':terminal['conductor_min_mm2'],'conductor_max_mm2':terminal['conductor_max_mm2']})
        mount=self.s.execute(select(m.component_mounting).where(m.component_mounting.c.component_version_id==v_id)).mappings().first()
        thermal=self.s.execute(select(m.component_thermal_specs).where(m.component_thermal_specs.c.component_version_id==v_id)).mappings().first()
        product=self.s.execute(select(m.products.c.manufacturer_sku,m.manufacturers.c.name.label('manufacturer'),m.product_versions.c.id.label('product_version_id'))
            .select_from(m.product_versions.join(m.products,m.products.c.id==m.product_versions.c.product_id).join(m.manufacturers,m.manufacturers.c.id==m.products.c.manufacturer_id))
            .where(m.product_versions.c.component_version_id==v_id,m.product_versions.c.status=='PUBLISHED')
            .order_by(m.product_versions.c.version_no.desc(),m.products.c.manufacturer_sku)).mappings().first()
        specs=row['specification'] or {}
        result={'id':str(row['component_id']),'code':row['code'],'catalog_id':row['code'],'component_version_id':str(v_id),
            'version_no':row['version_no'],'name':row['name'],'category':row['category_code'],'kind':row['component_kind'],
            'current_rating':row['rated_current_a'] or 0,'rated_voltage_v':row['rated_voltage_v'],
            'breaking_capacity':row['breaking_capacity_ka'] or 0,'poles':row['pole_count'] or 1,
            'width':row['width_mm'] or 0,'height':row['height_mm'] or 0,'depth':row['depth_mm'] or 0,
            'mounting':mount['mounting_code'] if mount else 'PLATE','mounting_parameters':mount['mounting_parameters'] if mount else {},
            'heat_loss':thermal['heat_loss_w'] or 0 if thermal else 0,'terminals':terminals,
            'cad_model':specs.get('cad_source_hint',''),'specification':specs,
            'manufacturer':product['manufacturer'] if product else None,'sku':product['manufacturer_sku'] if product else None,
            'product_version_id':str(product['product_version_id']) if product else None}
        return serial(result)

    def get_component(self, key):
        c=m.components
        row=self.s.execute(self._query().where(or_(c.c.id==identifier(key),c.c.code==key))).mappings().first()
        result=self._component(row)
        if result:
            result['cad_models']=self.cad_models(result['component_version_id'])
            result['clearances']=serial([dict(r) for r in self.s.execute(select(m.component_clearances).where(
                m.component_clearances.c.component_version_id==identifier(result['component_version_id']))).mappings()])
            result['documents']=serial([dict(r) for r in self.s.execute(select(m.component_documents).where(
                m.component_documents.c.component_version_id==identifier(result['component_version_id']))).mappings()])
        return result

    def search(self, q='',category=None,manufacturer=None,page=1,page_size=20,sort='code'):
        query=self._query()
        c,v=m.components,m.component_versions
        if category:
            query=query.where(c.c.category_code==category)
        if manufacturer or q:
            product_match=select(m.product_versions.c.component_version_id).select_from(
                m.product_versions.join(m.products,m.products.c.id==m.product_versions.c.product_id)
                .join(m.manufacturers,m.manufacturers.c.id==m.products.c.manufacturer_id))
            if manufacturer:
                product_match=product_match.where(or_(m.manufacturers.c.id==identifier(manufacturer),m.manufacturers.c.code==manufacturer))
                query=query.where(v.c.id.in_(product_match))
            if q:
                pattern='%'+q+'%'
                product_search=product_match.where(or_(m.products.c.manufacturer_sku.ilike(pattern),m.manufacturers.c.name.ilike(pattern)))
                query=query.where(or_(c.c.name.ilike(pattern),c.c.code.ilike(pattern),v.c.id.in_(product_search)))
        total=self.s.scalar(select(func.count()).select_from(query.subquery()))
        order={'code':c.c.code,'name':c.c.name,'current_rating':v.c.rated_current_a}[sort]
        rows=self.s.execute(query.order_by(order,c.c.id).offset((page-1)*page_size).limit(page_size)).mappings()
        return {'items':[self._component(r) for r in rows],'total':total,'page':page,'page_size':page_size}

    def engine_catalog(self):
        rows=self.s.execute(self._query().where(or_(m.component_versions.c.specification['import_source'].astext=='legacy-json-v1',
            m.component_versions.c.specification['engine_component'].as_boolean()==True))).mappings()
        return [{**self._component(r),'id':r['code']} for r in rows if r['category_code']!='ENCLOSURE']

    def hardware_catalog(self):
        rows=self.s.execute(self._query().where(m.component_versions.c.specification['import_source'].astext=='panel-hardware-v1')).mappings()
        return [self._component(r) for r in rows]

    def enclosures(self):
        rows=self.s.execute(self._query().where(m.components.c.category_code=='ENCLOSURE',
            m.component_versions.c.specification['import_source'].astext=='legacy-json-v1')).mappings()
        result=[]
        for row in rows:
            c=self._component(row)
            result.append({**c,**c['specification'],'id':c['code'],'width':c['width'],'height':c['height'],'depth':c['depth'],
                           'parameters':self.cad_models(c['component_version_id'])})
        return result

    def versions(self,key):
        c=self.get_component(key)
        if not c:
            raise PersistenceError('COMPONENT_NOT_FOUND','Component was not found.',404)
        return serial([dict(r) for r in self.s.execute(select(m.component_versions).where(
            m.component_versions.c.component_id==identifier(c['id'])).order_by(m.component_versions.c.version_no.desc())).mappings()])

    def cad_models(self, version_id):
        query=select(m.cad_model_versions).join(m.component_cad_models,
            m.cad_model_versions.c.id==m.component_cad_models.c.cad_model_version_id).where(
                m.component_cad_models.c.component_version_id==identifier(version_id),m.cad_model_versions.c.status=='PUBLISHED')\
                .order_by(m.cad_model_versions.c.version_no.desc(),m.cad_model_versions.c.id)
        result=[]
        for row in self.s.execute(query).mappings():
            value=serial(dict(row))
            value['parameters']=serial([dict(p) for p in self.s.execute(select(m.cad_parameter_definitions).where(
                m.cad_parameter_definitions.c.cad_model_version_id==row['id'])).mappings()])
            value['assets']=[self.asset_dto(a) for a in self.s.execute(select(m.cad_assets).where(m.cad_assets.c.cad_model_version_id==row['id'])).mappings()]
            result.append(value)
        return result

    def asset_dto(self,row,generated=False):
        row=dict(row)
        ready=self.assets.availability(row) if row['generation_status']=='READY' else row['generation_status']
        return {'id':str(row['id']),'file_format':row['file_format'],'sha256':row.get('sha256'),'byte_size':row.get('byte_size'),
            'status':ready,'type':row.get('artifact_type',row.get('asset_role')),'project_revision_id':serial(row.get('project_revision_id')),
            'url':f"/api/{'artifacts' if generated else 'assets'}/{row['id']}/content" if ready=='READY' else None,
            'generator_name':row.get('generator_name'),'generator_version':row.get('generator_version'),'error':row.get('error')}

    def accessories(self,key):
        c=self.get_component(key)
        if not c:
            raise PersistenceError('COMPONENT_NOT_FOUND','Component was not found.',404)
        ids=self.s.scalars(select(m.component_accessories.c.accessory_component_version_id).where(
            m.component_accessories.c.component_version_id==identifier(c['component_version_id']))).all()
        return [self._component(r) for r in self.s.execute(self._query().where(m.component_versions.c.id.in_(ids))).mappings()]

    def archetypes(self):
        rows=self.s.execute(select(m.panel_archetypes,m.panel_archetype_versions.c.id.label('version_id'),
            m.panel_archetype_versions.c.version_no).join(m.panel_archetype_versions,
            m.panel_archetypes.c.id==m.panel_archetype_versions.c.archetype_id).where(m.panel_archetype_versions.c.status=='PUBLISHED')
            .order_by(m.panel_archetypes.c.code,m.panel_archetype_versions.c.version_no.desc())).mappings()
        return [{**serial(dict(r)),'supported':r['code']=='DB'} for r in rows]

    def template(self, code='DB', version_id=None):
        match=next((a for a in self.archetypes() if (a['code']==code or a['id']==code) and
                    (version_id is None or a['version_id']==str(version_id))),None)
        if match is None:
            raise PersistenceError('ARCHETYPE_NOT_FOUND','Published panel archetype was not found.',404)
        av=identifier(match['version_id'])
        qv=self.s.scalar(select(m.archetype_questionnaires.c.questionnaire_version_id).where(m.archetype_questionnaires.c.archetype_version_id==av)
                         .order_by(m.archetype_questionnaires.c.sequence_no))
        questions=[]
        if qv:
            rows=self.s.execute(select(m.questions).where(m.questions.c.questionnaire_version_id==qv).order_by(m.questions.c.sequence_no)).mappings()
            for q in rows:
                options=list(self.s.scalars(select(m.question_options.c.value).where(m.question_options.c.question_id==q['id']).order_by(m.question_options.c.sequence_no)))
                deps=[]
                for dep in self.s.execute(select(m.question_dependencies,m.questions.c.code.label('parent_code')).join(
                    m.questions,m.questions.c.id==m.question_dependencies.c.depends_on_question_id).where(m.question_dependencies.c.question_id==q['id'])).mappings():
                    deps.append({'field':dep['parent_code'],'operator':dep['operator_code'],'value':dep['expected_value']})
                meta=q['validation'] or {}
                questions.append({'id':q['code'],'question_id':str(q['id']),'label':q['prompt'],
                    'type':meta.get('ui_type',{'INTEGER':'number','DECIMAL':'number','BOOLEAN':'boolean','SINGLE_SELECT':'select','MULTI_SELECT':'multi_select','MEASUREMENT':'number','QUANTITY':'number','OBJECT':'object'}.get(q['value_type'],'text')),
                    'unit':q['unit_code'],'default':meta.get('default'),'required':q['required'],'options':options or None,
                    'depends_on':deps,'validation':{k:meta[k] for k in ('min','max') if k in meta}})
        mods=[]
        for row in self.s.execute(select(m.functional_modules.c.code,m.archetype_modules).join(m.functional_module_versions,
            m.functional_module_versions.c.id==m.archetype_modules.c.module_version_id).join(m.functional_modules,
            m.functional_modules.c.id==m.functional_module_versions.c.module_id).where(m.archetype_modules.c.archetype_version_id==av)).mappings():
            mods.append({'name':row['code'],'required':row['required'],'category':row['configuration'].get('category','OTHER')})
        return {**match,'archetype':match['code'],'archetype_version_id':str(av),'questionnaire_version_id':str(qv) if qv else None,
                'questions':serial(questions),'modules':mods}

    def electrical_templates(self, archetype_version_id):
        rows=self.s.execute(select(m.electrical_template_versions).join(m.archetype_electrical_templates,
            m.archetype_electrical_templates.c.template_version_id==m.electrical_template_versions.c.id).where(
                m.archetype_electrical_templates.c.archetype_version_id==identifier(archetype_version_id))).mappings()
        result=[]
        for r in rows:
            roles=[dict(x) for x in self.s.execute(select(m.template_component_roles).where(m.template_component_roles.c.template_version_id==r['id'])).mappings()]
            for role in roles:
                role['terminals']=[dict(t) for t in self.s.execute(select(m.template_terminals).where(m.template_terminals.c.template_role_id==role['id'])).mappings()]
            connections=[dict(x) for x in self.s.execute(select(m.template_connections).where(m.template_connections.c.template_version_id==r['id'])).mappings()]
            result.append(serial({**dict(r),'roles':roles,'connections':connections}))
        return result

    def rules(self,rule_set_version_id=None):
        latest=select(func.max(m.design_rule_versions.c.version_no)).where(m.design_rule_versions.c.rule_id==m.design_rules.c.id,
            m.design_rule_versions.c.status=='PUBLISHED').correlate(m.design_rules).scalar_subquery()
        query=select(m.design_rules.c.code,m.design_rules.c.name,m.design_rules.c.engine_handler,m.design_rule_versions).join(
            m.design_rule_versions,m.design_rule_versions.c.rule_id==m.design_rules.c.id).where(m.design_rule_versions.c.status=='PUBLISHED')
        if rule_set_version_id:
            query=query.join(m.rule_set_members,m.rule_set_members.c.rule_version_id==m.design_rule_versions.c.id).where(
                m.rule_set_members.c.rule_set_version_id==identifier(rule_set_version_id),m.rule_set_members.c.enabled.is_(True))
        else:
            query=query.where(m.design_rule_versions.c.version_no==latest)
        return serial([dict(r) for r in self.s.execute(query).mappings()])


class ProjectRepository:
    def __init__(self,session):
        self.s=session

    def row(self,key,lock=False):
        stmt=select(m.projects).where(or_(m.projects.c.id==identifier(key),m.projects.c.project_code==key))
        if lock:
            stmt=stmt.with_for_update()
        row=self.s.execute(stmt).mappings().first()
        if row is None:
            raise PersistenceError('PROJECT_NOT_FOUND','Project was not found.',404)
        return dict(row)

    def get(self,key):
        row=self.row(key)
        archetype=self.s.scalar(select(m.panel_archetypes.c.code).join(m.panel_archetype_versions,
            m.panel_archetype_versions.c.archetype_id==m.panel_archetypes.c.id).where(m.panel_archetype_versions.c.id==row['archetype_version_id']))
        reqs=self.s.execute(select(m.project_requirements).where(m.project_requirements.c.project_id==row['id'],
            m.project_requirements.c.project_revision_id.is_(None))).mappings().all()
        if not reqs and row['current_revision_id']:
            reqs=self.s.execute(select(m.project_requirements).where(m.project_requirements.c.project_revision_id==row['current_revision_id'])).mappings().all()
        values={r['code']:r['value'].get('value') if isinstance(r['value'],dict) else r['value'] for r in reqs}
        values={key:value for key,value in values.items() if value is not None}
        req_ids=[r['id'] for r in reqs]
        values.update(self.answer_values(req_ids))
        return {'id':row['project_code'] or str(row['id']),'database_id':str(row['id']),'name':row['name'],'status':row['status'],
                'archetype':archetype,'archetype_version_id':serial(row['archetype_version_id']),'requirements':values,
                'configuration':row['configuration'],'lock_version':row['lock_version'],
                'current_revision_id':serial(row['current_revision_id']),'created_at':serial(row['created_at'])}

    def answer_values(self,requirement_ids):
        rows=self.s.execute(select(m.project_requirements.c.code,m.question_answers.c.answer_value)
            .join(m.requirement_sources,m.requirement_sources.c.requirement_id==m.project_requirements.c.id)
            .join(m.question_answers,m.question_answers.c.id==m.requirement_sources.c.question_answer_id)
            .where(m.project_requirements.c.id.in_(requirement_ids))).mappings()
        return {r['code']:r['answer_value'] for r in rows}

    def list(self,page=1,page_size=50):
        ids=self.s.scalars(select(m.projects.c.id).order_by(m.projects.c.updated_at.desc(),m.projects.c.id).offset((page-1)*page_size).limit(page_size)).all()
        return [self.get(str(i)) for i in ids]

    def create(self,name,archetype_version_id,project_code=None):
        key=uuid4()
        self.s.execute(insert(m.projects).values(id=key,project_code=project_code,name=name,status='ACTIVE',archetype_version_id=identifier(archetype_version_id)))
        return str(key)

    def check_version(self,key,expected_version=None):
        row=self.row(key,lock=True)
        if expected_version is not None and row['lock_version']!=expected_version:
            raise PersistenceError('REVISION_CONFLICT','Project changed in another request. Reopen it before saving.',409)
        return row

    def touch(self,row,**values):
        self.s.execute(update(m.projects).where(m.projects.c.id==row['id']).values(
            **values,updated_at=datetime.now(timezone.utc),lock_version=row['lock_version']+1))

    def save_requirements(self,row,template,req_set,answers):
        old=list(self.s.scalars(select(m.project_requirements.c.id).where(m.project_requirements.c.project_id==row['id'],m.project_requirements.c.project_revision_id.is_(None))))
        if old:
            self.s.execute(delete(m.requirement_sources).where(m.requirement_sources.c.requirement_id.in_(old)))
            self.s.execute(delete(m.project_requirements).where(m.project_requirements.c.id.in_(old)))
        session_id=uuid4()
        if template['questionnaire_version_id']:
            self.s.execute(insert(m.questionnaire_sessions).values(id=session_id,project_id=row['id'],
                questionnaire_version_id=identifier(template['questionnaire_version_id']),status='SUBMITTED',submitted_at=datetime.now(timezone.utc)))
        question_map={q['id']:q for q in template['questions']}
        for item in req_set.items:
            req_id=uuid4()
            self.s.execute(insert(m.project_requirements).values(id=req_id,project_id=row['id'],code=item.id,operator_code='EQ',
                value={'value':item.value,'label':item.label,'source':item.source,'state':item.state.value},unit_code=item.unit,
                resolution_status='CONFLICT' if item.state.value=='CONFLICTING' else 'RESOLVED'))
            answer_id=None
            if item.id in answers and template['questionnaire_version_id']:
                answer_id=uuid4()
                self.s.execute(insert(m.question_answers).values(id=answer_id,session_id=session_id,
                    question_id=identifier(question_map[item.id]['question_id']),answer_value=answers[item.id],actor_id='local-user'))
            self.s.execute(insert(m.requirement_sources).values(requirement_id=req_id,source_kind='ANSWER' if answer_id else 'ENGINEER',
                question_answer_id=answer_id,source_ref='questionnaire-default' if answer_id is None else None,
                details={'questionnaire_version_id':template['questionnaire_version_id']}))

    def revisions(self,key):
        row=self.row(key)
        return serial([dict(r) for r in self.s.execute(select(m.project_revisions.c.id,m.project_revisions.c.revision_no,
            m.project_revisions.c.parent_revision_id,m.project_revisions.c.created_at,m.project_revisions.c.content_sha256,m.project_revisions.c.status)
            .where(m.project_revisions.c.project_id==row['id']).order_by(m.project_revisions.c.revision_no.desc())).mappings()])


class MemoryComponents:
    """Materialized DB catalog for the existing pure selection algorithm."""
    def __init__(self,rows): self.rows=rows
    def get_all(self): return self.rows
    def get_by_id(self,key): return next((r for r in self.rows if r['id']==key),None)
    def filter_candidates(self,category,min_current=0,min_breaking_capacity=0,poles=None):
        return [r for r in self.rows if r['category']==category and r['current_rating']>=min_current and
                r['breaking_capacity']>=min_breaking_capacity and (poles is None or r['poles']==poles)]


class MemoryProjects:
    def __init__(self,project): self.project=project
    def get_by_id(self,key): return self.project if self.project['id']==key else None
    def save(self,project): raise RuntimeError('The engineering pipeline cannot persist projects directly.')


class MemoryEnclosures:
    def __init__(self,rows,selected_id=None): self.rows,self.selected_id=rows,selected_id
    def get_all(self): return self.rows
    def find_best_fit(self,min_width,min_height,min_thermal_dissipation,ip_rating='IP54'):
        order={'IP31':1,'IP42':2,'IP54':3,'IP65':4}
        feasible=[r for r in self.rows if (not self.selected_id or r['id']==self.selected_id) and
            r['mounting_plate_width']>=min_width and r['mounting_plate_height']>=min_height and
            r.get('max_thermal_dissipation',0)>=min_thermal_dissipation and order.get(r.get('ip_rating'),0)>=order.get(ip_rating,99)]
        return min(feasible,key=lambda r:r['width']*r['height']) if feasible else None
