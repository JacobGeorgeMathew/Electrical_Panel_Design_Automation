"""Atomic snapshot + projection writer. No geometry calculations or file I/O here."""
import math
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import func, insert, select
from app.persistence import models as m
from app.persistence.assets import content_hash
from app.persistence.repositories import ProjectRepository, identifier


def transform(position,angle=0):
    half=math.radians(angle)/2
    return {'translation_mm':[position[k] for k in ('x','y','z')], 'quaternion_xyzw':[0,0,math.sin(half),math.cos(half)]}


def write_revision(session,project,template,req_set,answers,result,manifest,files,expected_version):
    repo=ProjectRepository(session)
    row=repo.check_version(project['id'],expected_version)
    # All writes below participate in the caller's single session.begin transaction.
    repo.save_requirements(row,template,req_set,answers)
    rid=uuid4()
    number=(session.scalar(select(func.max(m.project_revisions.c.revision_no)).where(m.project_revisions.c.project_id==row['id'])) or 0)+1
    cem,pdm=result['cem'],result['pdm']
    cem_hash,pdm_hash=content_hash(cem),content_hash(pdm)
    manifest={**manifest,'configuration':project.get('configuration',{}),'saved_lock_version':row['lock_version']+1}
    revision_hash=content_hash({'cem':cem_hash,'pdm':pdm_hash,'manifest':manifest})
    session.execute(insert(m.project_revisions).values(id=rid,project_id=row['id'],revision_no=number,parent_revision_id=row['current_revision_id'],
        status='PUBLISHED',archetype_version_id=identifier(template['archetype_version_id']),rule_set_version_id=identifier(manifest.get('rule_set_version_id')),
        questionnaire_version_ids=[identifier(template['questionnaire_version_id'])] if template['questionnaire_version_id'] else [],
        schema_version=1,model_manifest=manifest,content_sha256=revision_hash,created_by='local-user'))
    session.execute(insert(m.cem_snapshots).values(project_revision_id=rid,schema_version=1,snapshot=cem,sha256=cem_hash))
    session.execute(insert(m.pdm_snapshots).values(project_revision_id=rid,schema_version=1,snapshot=pdm,sha256=pdm_hash))
    drafts=session.execute(select(m.project_requirements).where(m.project_requirements.c.project_id==row['id'],m.project_requirements.c.project_revision_id.is_(None))).mappings().all()
    for req in drafts:
        new_id=uuid4()
        session.execute(insert(m.project_requirements).values(id=new_id,project_id=row['id'],project_revision_id=rid,code=req['code'],
            operator_code=req['operator_code'],value=req['value'],unit_code=req['unit_code'],resolution_status=req['resolution_status']))
        for source in session.execute(select(m.requirement_sources).where(m.requirement_sources.c.requirement_id==req['id'])).mappings():
            session.execute(insert(m.requirement_sources).values(requirement_id=new_id,source_kind=source['source_kind'],
                question_answer_id=source['question_answer_id'],source_ref=source['source_ref'],details=source['details']))
    for code,value in project.get('configuration',{}).get('enclosure_parameters',{}).items():
        session.execute(insert(m.project_parameter_overrides).values(project_revision_id=rid,target_kind='ENCLOSURE',target_code=code,
            value=value,unit_code='mm',source_kind='USER'))

    roles={r['component_category']:r['id'] for t in manifest.get('electrical_templates',[]) for r in t.get('roles',[])}
    components,terminals={},{}
    enclosure_version=identifier(manifest['enclosure_component_version_id'])
    for c in cem['components']:
        ci=uuid4()
        version=identifier(c['component_version_id'])
        product=identifier(c.get('product_version_id'))
        session.execute(insert(m.revision_components).values(project_revision_id=rid,component_version_id=version,
            product_version_id=product,role_code=c['category'],selected_by='SELECTOR',selection_evidence={'catalog_code':c['catalog_id'],'engine_version':manifest['engine_version']}))
        session.execute(insert(m.cem_component_instances).values(id=ci,project_revision_id=rid,stable_key=c['id'],role_code=c['category'],
            component_version_id=version,product_version_id=product,display_name=c['name'],properties={'electrical':c},
            source_template_role_id=identifier(roles.get(c['category']))))
        components[c['id']]=ci
        for t in c.get('terminals',[]):
            ti=uuid4()
            session.execute(insert(m.cem_terminal_instances).values(id=ti,component_instance_id=ci,stable_key=t['id'],terminal_code=t['id'],
                terminal_role=t.get('type'),electrical_properties={k:v for k,v in t.items() if k not in {'x','y','z'}}))
            terminals[(c['id'],t['id'])]=ti
    # The existing CEM graph has a panel earth reference outside its purchased-parts list.
    # Project it as the enclosure's terminal interface, without adding a purchased BOM item.
    root=uuid4()
    session.execute(insert(m.cem_component_instances).values(id=root,project_revision_id=rid,stable_key='PANEL_ROOT',role_code='ENCLOSURE_INTERFACE',
        component_version_id=enclosure_version,display_name='Panel reference terminals',properties={'snapshot_source':'electrical_graph:PANEL_ROOT','external_reference':True}))
    for connection in cem['connections']:
        for side in ('from','to'):
            key=(connection[side+'_component'],connection[side+'_terminal'])
            if key[0]=='PANEL_ROOT' and key not in terminals:
                ti=uuid4()
                session.execute(insert(m.cem_terminal_instances).values(id=ti,component_instance_id=root,stable_key=key[1],terminal_code=key[1],terminal_role='PE'))
                terminals[key]=ti
    nets,conductors={},{}
    for n in cem['nets']:
        ni=uuid4()
        nets[n['id']]=ni
        session.execute(insert(m.cem_nets).values(id=ni,project_revision_id=rid,stable_key=n['id'],net_code=n['name'],wire_class=n['wire_class'],nominal_voltage_v=n['voltage_level']))
        members=set()
        for connection in n['connections']:
            ends=[terminals[(connection[side+'_component'],connection[side+'_terminal'])] for side in ('from','to')]
            members.update(ends)
            conductor=uuid4()
            session.execute(insert(m.cem_conductors).values(id=conductor,net_id=ni,conductor_code=connection['id'],
                conductor_type=connection.get('wire_class','POWER'),properties={'source_connection':connection},
                from_terminal_instance_id=ends[0],to_terminal_instance_id=ends[1]))
            conductors[connection['id']]=conductor
        for terminal in members:
            session.execute(insert(m.cem_net_terminals).values(net_id=ni,terminal_instance_id=terminal))
    enc=uuid4()
    session.execute(insert(m.pdm_enclosures).values(id=enc,project_revision_id=rid,stable_key=pdm['enclosure_id'],component_version_id=enclosure_version,
        cad_model_version_id=identifier(manifest.get('enclosure_cad_model_version_id')),width_mm=pdm['enclosure_width'],height_mm=pdm['enclosure_height'],depth_mm=pdm['enclosure_depth'],
        coordinate_frame={'origin':'lower-left-front','handedness':'right','length_unit':'mm'},parameters={
            'width_mm':pdm['enclosure_width'],'height_mm':pdm['enclosure_height'],'depth_mm':pdm['enclosure_depth']}))
    structures={}
    structures['BACKPLATE']=uuid4()
    session.execute(insert(m.pdm_mounting_structures).values(id=structures['BACKPLATE'],project_revision_id=rid,enclosure_id=enc,stable_key='BACKPLATE',structure_kind='BACKPLATE',
        transform=transform({'x':pdm['mounting_plate_x'],'y':pdm['mounting_plate_y'],'z':pdm['mounting_plate_z']}),
        dimensions_mm={'width':pdm['mounting_plate_width'],'height':pdm['mounting_plate_height'],'depth':3}))
    for rail in pdm.get('rails',[]):
        uid=uuid4(); structures[rail['id']]=uid
        session.execute(insert(m.pdm_mounting_structures).values(id=uid,project_revision_id=rid,enclosure_id=enc,stable_key=rail['id'],structure_kind='DIN_RAIL',
            transform=transform(rail),dimensions_mm={'length':rail['length'],'height':rail['profile_height'],'depth':rail['profile_depth']},parameters={'orientation':rail['orientation']}))
    for kind,collection in (('WIRE_DUCT',pdm.get('ducts',[])),('BUSBAR',pdm.get('busbars',[]))):
        for item in collection:
            uid=uuid4();structures[item['id']]=uid
            session.execute(insert(m.pdm_mounting_structures).values(id=uid,project_revision_id=rid,enclosure_id=enc,stable_key=item['id'],structure_kind=kind,
                transform=transform(item),dimensions_mm={k:item[k] for k in ('width','height','depth')},parameters=item))
    physical={}
    c_by_id={c['id']:c for c in cem['components']}
    for p in pdm['components']:
        pi=uuid4(); physical[p['id']]=pi
        c=c_by_id[p['cem_component_id']]
        session.execute(insert(m.pdm_component_instances).values(id=pi,project_revision_id=rid,stable_key=p['id'],cem_component_instance_id=components[p['cem_component_id']],
            cad_model_version_id=identifier(c.get('cad_model_version_id')),parameters={'width_mm':p['width'],'height_mm':p['height'],'depth_mm':p['depth']}))
        pos=p['position']
        session.execute(insert(m.pdm_placements).values(pdm_component_instance_id=pi,mounting_structure_id=structures.get(p.get('rail_id'),structures['BACKPLATE']),
            transform=transform(pos,p.get('rotation_deg',0)),bounding_box_mm={'min':[pos[k] for k in ('x','y','z')],
                'max':[pos['x']+p['width'],pos['y']+p['height'],pos['z']+p['depth']]},zone_code=p['zone_name'],evaluated_geometry_hash=pdm_hash))
        if c.get('cad_model_version_id'):
            session.execute(insert(m.project_cad_instances).values(project_revision_id=rid,cad_model_version_id=identifier(c['cad_model_version_id']),stable_key=p['id'],
                evaluated_values={'width_mm':p['width'],'height_mm':p['height'],'depth_mm':p['depth']},generation_status='READY'))
    if manifest.get('enclosure_cad_model_version_id'):
        session.execute(insert(m.project_cad_instances).values(project_revision_id=rid,cad_model_version_id=identifier(manifest['enclosure_cad_model_version_id']),stable_key='ENCLOSURE',
            supplied_values=project.get('configuration',{}).get('enclosure_parameters',{}),evaluated_values={
                'width_mm':pdm['enclosure_width'],'height_mm':pdm['enclosure_height'],'depth_mm':pdm['enclosure_depth']},generation_status='READY'))
    for route in pdm['routes']:
        session.execute(insert(m.pdm_routes).values(project_revision_id=rid,stable_key=route['id'],net_id=nets[route['net_id']],
            conductor_id=conductors[route['id'].removeprefix('ROUTE-')],waypoints_mm=route['waypoints'],length_mm=route['length_mm'],
            routing_constraints={'engine_version':manifest['engine_version'],'wire_class':route['wire_class']}))
    for i,clearance in enumerate(pdm.get('clearances',[])):
        session.execute(insert(m.pdm_clearance_regions).values(project_revision_id=rid,stable_key=f'CLEARANCE-{i}',
            owner_component_instance_id=physical.get(clearance['component_id']),region_kind='CLEARANCE',geometry_ref=clearance))
    run=uuid4()
    session.execute(insert(m.validation_runs).values(id=run,project_revision_id=rid,rule_set_version_id=identifier(manifest.get('rule_set_version_id')),
        engine_name='existing-pdm-validator',engine_version=manifest['engine_version'],status='COMPLETED_WITH_WARNINGS' if result['validation_errors'] else 'PASSED',
        input_sha256=pdm_hash,completed_at=datetime.now(timezone.utc)))
    rule_versions=manifest.get('validation_rule_versions',{})
    for kind,rv in rule_versions.items():
        violations=[v for v in result['validation_errors'] if v['type']==kind]
        for v in violations or [None]:
            session.execute(insert(m.validation_results).values(validation_run_id=run,rule_version_id=identifier(rv),rule_code='VALIDATION_'+kind,
                result_status='WARNING' if v else 'PASS',affected_entities=[v[k] for k in ('object_a','object_b') if v.get(k)] if v else [],
                measured_values={k:v[k] for k in ('required_value','actual_value','unit')} if v else {},
                message=v['message'] if v else f'{kind}: no violations reported by the existing prototype validator.',
                evidence={'engine_version':manifest['engine_version'],'snapshot_sha256':pdm_hash}))
    for file in files:
        session.execute(insert(m.generated_artifacts).values(id=uuid4(),project_revision_id=rid,**file,source_model_kind='PDM',source_model_sha256=pdm_hash,
            generation_status='READY',completed_at=datetime.now(timezone.utc)))
    for source_kind,source_key,target_kind,target_key,input_hash,output_hash in [
        ('REQUIREMENTS','project','CEM','design',content_hash(answers),cem_hash),('CEM','design','PDM','layout',cem_hash,pdm_hash),
        ('PDM','layout','ROUTING','routes',pdm_hash,content_hash(pdm['routes'])),('ROUTING','routes','CAD','assembly',content_hash(pdm['routes']),pdm_hash)]:
        session.execute(insert(m.revision_dependencies).values(project_revision_id=rid,source_kind=source_kind,source_key=source_key,
            target_kind=target_kind,target_key=target_key,dependency_kind='DERIVES',input_sha256=input_hash,output_sha256=output_hash))
    for parameter,value in project.get('configuration',{}).get('enclosure_parameters',{}).items():
        session.execute(insert(m.revision_dependencies).values(project_revision_id=rid,source_kind='PARAMETER',source_key='ENCLOSURE.'+parameter,
            target_kind='PDM',target_key='layout',dependency_kind='GEOMETRY_INPUT',input_sha256=content_hash(value),output_sha256=pdm_hash))
    for c in cem['components']:
        session.execute(insert(m.revision_dependencies).values(project_revision_id=rid,source_kind='COMPONENT_VERSION',source_key=c['component_version_id'],
            target_kind='CEM',target_key=c['id'],dependency_kind='SELECTED_SPECIFICATION',input_sha256=content_hash(c['component_version_id']),output_sha256=cem_hash))
    session.execute(insert(m.provenance).values(project_id=row['id'],project_revision_id=rid,subject_kind='DESIGN',subject_key=str(rid),
        source_kind='OPTIMIZER',source_ref=manifest['engine_version'],details={'manifest':manifest,'cem_sha256':cem_hash,'pdm_sha256':pdm_hash}))
    repo.touch(row,current_revision_id=rid,configuration=project.get('configuration',{}))
    return {'revision_id':str(rid),'revision_no':number,'lock_version':row['lock_version']+1,'snapshot_sha256':revision_hash}
