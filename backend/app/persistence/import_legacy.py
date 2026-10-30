"""Explicit, repeatable migration of prototype JSON. Never used as runtime storage."""
import json
from dataclasses import asdict
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5
from sqlalchemy import insert, select, func
from app.persistence import models as m
from app.persistence.assets import content_hash, primitive_glb
from app.persistence.repositories import CatalogRepository, ProjectRepository
from app.services.requirement_engine import RequirementEngine
from app.algorithms.layout_config import LayoutConfig


def stable(key):
    return uuid5(NAMESPACE_URL, 'panelstudio:legacy:'+key)


def jsonable(value):
    if isinstance(value,dict): return {k:jsonable(v) for k,v in value.items()}
    if isinstance(value,set): return sorted(value)
    if isinstance(value,list): return [jsonable(v) for v in value]
    return value


def import_legacy(database):
    root=Path(__file__).resolve().parents[1]/'data'
    from app.persistence.assets import AssetStore
    assets=AssetStore(database.settings.asset_root)
    with database.sessions.begin() as s:
        def put(table,key,**values):
            uid=stable(key)
            if not s.scalar(select(table.c.id).where(table.c.id==uid)):
                s.execute(insert(table).values(id=uid,**values))
            return uid

        manufacturer=put(m.manufacturers,'manufacturer',code='PROTOTYPE_JSON',name='Prototype JSON fixtures (unverified)')
        family=put(m.product_families,'family',manufacturer_id=manufacturer,code='DB_DEMO',name='Existing application demo catalog')
        components=json.loads((root/'components.json').read_text())
        enclosures=json.loads((root/'enclosures.json').read_text())
        for data in components+enclosures:
            enclosure=data in enclosures
            code=data['id']
            category='ENCLOSURE' if enclosure else data['category']
            cid=put(m.components,'component:'+code,code=code,name=data['name'],category_code=category,
                component_kind='MECHANICAL' if enclosure else 'ELECTRICAL')
            version=stable('component-version:'+code)
            source_hash=content_hash(data)
            old=s.execute(select(m.component_versions).where(m.component_versions.c.id==version)).mappings().first()
            if old and old['specification'].get('source_sha256')!=source_hash:
                raise RuntimeError(f'Legacy source changed for {code}; publish a new version explicitly instead of modifying version 1.')
            standard={'id','name','category','current_rating','breaking_capacity','poles','width','height','depth','mounting','heat_loss','terminals','cad_model'}
            specs={k:v for k,v in data.items() if k not in standard and not k.startswith('clearance_')}
            specs.update(import_source='legacy-json-v1',source_sha256=source_hash,cad_source_hint=data.get('cad_model'),
                         provenance='Existing prototype data; not verified manufacturer specifications',configurable=enclosure)
            put(m.component_versions,'component-version:'+code,component_id=cid,version_no=1,status='PUBLISHED',
                rated_current_a=data.get('current_rating'),breaking_capacity_ka=data.get('breaking_capacity'),pole_count=data.get('poles'),
                width_mm=data['width'],height_mm=data['height'],depth_mm=data['depth'],specification=specs)
            product=put(m.products,'product:'+code,manufacturer_id=manufacturer,family_id=family,manufacturer_sku=code,display_name=data['name'])
            put(m.product_versions,'product-version:'+code,product_id=product,component_version_id=version,version_no=1,status='PUBLISHED',lifecycle_status='UNKNOWN')
            put(m.component_mounting,'mount:'+code,component_version_id=version,mounting_code=data.get('mounting','PLATE'))
            if not s.scalar(select(m.component_thermal_specs.c.component_version_id).where(m.component_thermal_specs.c.component_version_id==version)):
                s.execute(insert(m.component_thermal_specs).values(component_version_id=version,heat_loss_w=data.get('heat_loss',0)))
            for terminal in data.get('terminals',[]):
                put(m.component_terminals,'terminal:'+code+':'+terminal['id'],component_version_id=version,code=terminal['id'],
                    terminal_kind='PROTOTYPE',electrical_role=terminal.get('type','POWER'),connection_type='UNVERIFIED',
                    coordinate_mm={k:terminal.get(k,0) for k in ('x','y','z')})
            for direction in ('top','bottom','sides'):
                if 'clearance_'+direction in data:
                    put(m.component_clearances,'clearance:'+code+':'+direction,component_version_id=version,direction_code=direction.upper(),
                        distance_mm=data['clearance_'+direction],provenance={'source':'legacy-json','verified':False})
            model=put(m.cad_models,'cad:'+code,code='PROTO_'+code,name=data['name']+' prototype geometry',model_kind='PART')
            mv=put(m.cad_model_versions,'cad-version:'+code,cad_model_id=model,version_no=1,status='PUBLISHED',
                coordinate_system={'handedness':'right','source_length_unit':'mm','glb_length_unit':'m','origin':'centre'},
                feature_definition={'handler':'box_v1','dimension_source':'component-version','illustrative':True},
                generator_name='panelstudio-primitives',generator_version='1')
            for axis in ('width','height','depth'):
                put(m.cad_parameter_definitions,'param:'+code+':'+axis,cad_model_version_id=mv,code=axis+'_mm',
                    value_type='DECIMAL',unit_code='mm',default_value=data[axis],min_value=1,editable=enclosure,derived=False,
                    description='Positive prototype geometry dimension; not a certified product range.')
            if not s.scalar(select(m.component_cad_models.c.component_version_id).where(
                m.component_cad_models.c.component_version_id==version,m.component_cad_models.c.cad_model_version_id==mv)):
                s.execute(insert(m.component_cad_models).values(component_version_id=version,cad_model_version_id=mv))
            file=assets.put(primitive_glb([{'type':'BOX','id':code,'name':data['name'],'dimensions':{k:data[k] for k in ('width','height','depth')},'color':'#94A3B8'}],generator_version='1'),'glb')
            put(m.cad_assets,'preview:'+code,cad_model_version_id=mv,asset_role='PREVIEW',file_format='GLB',
                **file,media_type='model/gltf-binary',generator_name='panelstudio-primitives',generator_version='1',generation_status='READY')

        templates=json.loads((root/'panel_templates.json').read_text())
        for data in templates:
            code=data['archetype']
            arch=put(m.panel_archetypes,'archetype:'+code,code=code,name=data['name'],description=data.get('description'))
            av=put(m.panel_archetype_versions,'archetype-version:'+code,archetype_id=arch,version_no=1,status='PUBLISHED',
                defaults={'import_source':'legacy-json-v1','source_sha256':content_hash(data),'engine_handler':'db_v1'})
            q=put(m.questionnaires,'questionnaire:'+code,code=code+'_REQUIREMENTS',name=data['name']+' requirements')
            qv=put(m.questionnaire_versions,'questionnaire-version:'+code,questionnaire_id=q,version_no=1,status='PUBLISHED')
            if not s.scalar(select(m.archetype_questionnaires.c.archetype_version_id).where(m.archetype_questionnaires.c.archetype_version_id==av)):
                s.execute(insert(m.archetype_questionnaires).values(archetype_version_id=av,questionnaire_version_id=qv))
            for i,question in enumerate(data['questions']):
                qid=put(m.questions,'question:'+code+':'+question['id'],questionnaire_version_id=qv,code=question['id'],prompt=question['label'],
                    value_type={'number':'DECIMAL','select':'SINGLE_SELECT','text':'TEXT','boolean':'BOOLEAN'}[question['type']],
                    unit_code=question.get('unit'),required=question.get('required',True),sequence_no=i,
                    validation={**question.get('validation',{}),'default':question.get('default'),'ui_type':question['type']})
                for j,option in enumerate(question.get('options',[])):
                    put(m.question_options,'option:'+code+':'+question['id']+':'+str(j),question_id=qid,option_code=str(option),label=str(option),value=option,sequence_no=j)
            for question in data['questions']:
                for dep in question.get('depends_on',[]):
                    put(m.question_dependencies,'dep:'+code+':'+question['id']+':'+dep['field'],question_id=stable('question:'+code+':'+question['id']),
                        depends_on_question_id=stable('question:'+code+':'+dep['field']),operator_code=dep['operator'],expected_value=dep['value'])
            for i,module in enumerate(data.get('modules',[])):
                # Reuse a pre-existing generic module identity, but never alter its published version.
                mid=s.scalar(select(m.functional_modules.c.id).where(m.functional_modules.c.code==module['name']))
                if mid is None: mid=put(m.functional_modules,'module:'+module['name'],code=module['name'],name=module['name'])
                next_version=(s.scalar(select(func.max(m.functional_module_versions.c.version_no)).where(m.functional_module_versions.c.module_id==mid)) or 0)+1
                mv=put(m.functional_module_versions,'module-version:'+module['name'],module_id=mid,version_no=next_version,status='PUBLISHED')
                if not s.scalar(select(m.archetype_modules.c.module_version_id).where(m.archetype_modules.c.archetype_version_id==av,m.archetype_modules.c.module_version_id==mv)):
                    s.execute(insert(m.archetype_modules).values(archetype_version_id=av,module_version_id=mv,sequence_no=i,required=module['required'],configuration={'category':module['category']}))
                put(m.module_role_requirements,'module-role:'+module['name'],module_version_id=mv,role_code=module['name'],required_properties={'category':module['category']})
            et=put(m.electrical_templates,'template:'+code,code=code+'_NETLIST_V1',name='Existing DB netlist generator contract')
            etv=put(m.electrical_template_versions,'template-version:'+code,template_id=et,version_no=1,status='PUBLISHED',
                validation_rules=[{'engine_handler':'db_netlist_v1','description':'Existing Python netlist engine; terminals resolved from selected catalog versions.'}])
            if not s.scalar(select(m.archetype_electrical_templates.c.archetype_version_id).where(m.archetype_electrical_templates.c.archetype_version_id==av)):
                s.execute(insert(m.archetype_electrical_templates).values(archetype_version_id=av,template_version_id=etv))
            for module in data['modules']:
                put(m.template_component_roles,'template-role:'+code+':'+module['category'],template_version_id=etv,role_code=module['name'],component_category=module['category'])
            if code=='DB':
                incoming=put(m.template_terminals,'template-terminal:DB:INCOMER:LOAD',template_role_id=stable('template-role:DB:MCCB'),terminal_code='LOAD_PHASE',terminal_role='LOAD')
                busbar=put(m.template_terminals,'template-terminal:DB:BUSBAR:LINE',template_role_id=stable('template-role:DB:BUSBAR'),terminal_code='SUPPLY_PHASE',terminal_role='LINE')
                put(m.template_connections,'template-connection:DB:INCOMER:BUSBAR',template_version_id=etv,from_template_terminal_id=incoming,
                    to_template_terminal_id=busbar,connection_code='INCOMER_TO_BUSBAR',connection_type='POWER',directionality='UNDIRECTED',
                    properties={'mapping_handler':'db_netlist_v1','terminal_codes_are_abstract':True})
        for code,role,operator,mapping in [('incomer_rating','INCOMER','MIN',{'property':'rated_current_a','unit':'A'}),
                ('num_feeders','OUTGOING_FEEDERS','QUANTITY',{'property':'quantity'}),('ip_rating','ENCLOSURE','EQ',{'property':'ip_rating'})]:
            put(m.requirement_role_mappings,'requirement-role:'+code,requirement_code=code,role_code=role,mapping_operator=operator,mapping=mapping)

        rules=json.loads((root/'rules.json').read_text())
        rs=put(m.rule_sets,'rule-set',code='DB_ENGINE_V1',name='DB prototype engine rules (unverified)')
        rsv=put(m.rule_set_versions,'rule-set-version',rule_set_id=rs,version_no=1,status='PUBLISHED')
        layout=jsonable(asdict(LayoutConfig()))
        rules += [{'id':'DB_LAYOUT_CONFIG','name':'Existing layout configuration','category':'LAYOUT','layout_config':layout}]
        rules += [{'id':'VALIDATION_'+kind,'name':kind+' check','category':kind,'handler':'pdm_v1'}
                  for kind in ('BOUNDARY','OVERLAP','CLEARANCE','THERMAL','IDENTITY','TERMINAL','ROUTE_CLEARANCE')]
        for rule in rules:
            rid=put(m.design_rules,'rule:'+rule['id'],code=rule['id'],name=rule['name'],engine_handler=rule.get('handler','prototype_metadata'))
            rv=put(m.design_rule_versions,'rule-version:'+rule['id'],rule_id=rid,version_no=1,status='PUBLISHED',severity='WARNING',hardness='SOFT',
                parameters=rule,provenance={'source':'existing-prototype','verified':False,'engine_version':'db_v1'})
            put(m.rule_applicability,'rule-applicability:'+rule['id'],rule_version_id=rv,target_kind=rule.get('category','DESIGN'),predicate={'archetype':'DB'})
            if not s.scalar(select(m.rule_set_members.c.rule_version_id).where(m.rule_set_members.c.rule_set_version_id==rsv,m.rule_set_members.c.rule_version_id==rv)):
                s.execute(insert(m.rule_set_members).values(rule_set_version_id=rsv,rule_version_id=rv))
        catalog=CatalogRepository(s,assets)
        template=catalog.template('DB',resolve_capabilities=False)
        engine=RequirementEngine(templates={'DB':template})
        repo=ProjectRepository(s)
        for project in json.loads((root/'sample_projects.json').read_text()):
            if s.scalar(select(m.projects.c.id).where(m.projects.c.project_code==project['id'])):
                continue
            pid=repo.create(project['name'],template['archetype_version_id'],project['id'])
            row=repo.row(pid)
            requirements=engine.validate_requirements(project['id'],'DB',project.get('requirements',{}))
            if not requirements.is_valid:
                raise RuntimeError('Existing project requirements need correction before import: '+project['id'])
            repo.save_requirements(row,template,requirements,project.get('requirements',{}))
            put(m.provenance,'project-import:'+project['id'],project_id=row['id'],subject_kind='PROJECT',subject_key=project['id'],
                source_kind='IMPORT',source_ref='sample_projects.json',details={'original':project,'source_sha256':content_hash(project)})
    from app.persistence.import_panel_hardware import import_panel_hardware
    hardware = import_panel_hardware(database)
    from app.persistence.seed_constraints import seed_constraints
    policy = seed_constraints(database)
    return {'components':len(components),'enclosures':len(enclosures),'archetypes':len(templates),'source_files_unchanged':True,**hardware,'constraints':policy}
