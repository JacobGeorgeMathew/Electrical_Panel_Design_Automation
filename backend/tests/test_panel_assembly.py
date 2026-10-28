import json
import struct
import pytest
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from app.services.orchestrator import DesignOrchestrator
from app.services.validation_engine import ValidationEngine
from app.services.cad_engine import CADEngine
from app.models.pdm import PhysicalDesignModel
from app.models.cem import CanonicalEngineeringModel
from app.persistence.assets import primitive_glb


@pytest.fixture(scope='module')
def assembly():
    return DesignOrchestrator().generate_design('TEST-CABINET',persist_requirements=False)


def test_real_troughs_reserve_space_and_every_trunk_stays_inside(assembly):
    pdm=PhysicalDesignModel(**assembly['pdm'])
    assert len(pdm.ducts)>=5
    network=unary_union([box(d.x,d.y,d.x+d.width,d.y+d.height) for d in pdm.ducts])
    for component in pdm.components:
        assert network.intersection(box(component.position.x,component.position.y,
            component.position.x+component.width,component.position.y+component.height)).area<.01
    for route in pdm.routes:
        assert route.duct_ids and route.duct_entry_index is not None and route.duct_exit_index is not None
        trunk=route.waypoints[route.duct_entry_index:route.duct_exit_index+1]
        if len(trunk)>1:
            assert network.covers(LineString([(p.x,p.y) for p in trunk]))
    assert not any(v.severity=='CRITICAL' for v in ValidationEngine().validate_pdm(pdm,CanonicalEngineeringModel(**assembly['cem'])))


def test_duct_validation_rejects_missing_reference_and_overfill(assembly):
    pdm=PhysicalDesignModel(**assembly['pdm'])
    route=pdm.routes[0];route.duct_ids=['DOES-NOT-EXIST']
    assert any(v.type=='DUCT_ROUTING' and v.object_a==route.id for v in ValidationEngine().validate_pdm(pdm))
    pdm=PhysicalDesignModel(**assembly['pdm'])
    for route in pdm.routes: route.wire_diameter_mm=30
    # Recomputed from conductor sizes, even when stored capacity_pct is spoofed.
    for duct in pdm.ducts: duct.capacity_pct=0
    assert any(v.type=='DUCT_CAPACITY' and v.severity=='CRITICAL' for v in ValidationEngine().validate_pdm(pdm))


def test_duct_validation_rejects_a_trunk_detour_outside_network(assembly):
    pdm=PhysicalDesignModel(**assembly['pdm'])
    route=next(r for r in pdm.routes if r.duct_exit_index>r.duct_entry_index+1)
    route.waypoints[route.duct_entry_index+1].x=pdm.enclosure_width/2
    route.waypoints[route.duct_entry_index+1].y=pdm.enclosure_height-50
    assert any(v.type=='DUCT_ROUTING' and v.object_a==route.id for v in ValidationEngine().validate_pdm(pdm))


def test_enclosure_is_hollow_with_door_hardware_and_detailed_terminal_meshes(assembly):
    pdm=assembly['pdm'];cad=assembly['cad']['primitives']
    categories={a['category'] for a in pdm['accessories']}
    assert {'ENCLOSURE_BODY','DOOR','HINGE','HANDLE','GASKET','GLAND_PLATE','END_STOP','END_PLATE'}<=categories
    shell=[p for p in cad if p['id'].startswith('CABINET-')]
    assert len(shell)>=5
    assert all(min(p['dimensions'].values())<=2 for p in shell)
    assert any(p.get('assembly_group')=='DUCT_COVER' for p in cad)
    terminal=next(c for c in pdm['components'] if c['category']=='TERMINAL')
    assert any(p['type']=='CYLINDER' for p in terminal['geometry'])
    assert any(p['id'].endswith('-CASE') for p in cad)


def test_three_phase_terminal_outputs_and_breaker_sides_are_isolated(assembly):
    cem=assembly['cem']; terminals={c['id']:c for c in cem['components'] if c['category']=='TERMINAL'}
    for breaker in [c for c in cem['components'] if c['category']=='MCB' and c['poles']==3]:
        outgoing=[c for c in cem['connections'] if c['from_component']==breaker['id']]
        assert len(outgoing)==3
        assert {c['to_terminal'] for c in outgoing}=={'L1_LEFT','L2_LEFT','L3_LEFT'}
        assert len({c['net_id'] for c in outgoing})==3
        terminal=terminals[outgoing[0]['to_component']]
        assert terminal['poles']==3 and len(terminal['terminals'])==6
        incoming={c['net_id'] for c in cem['connections'] if c['to_component']==breaker['id']}
        assert incoming.isdisjoint({c['net_id'] for c in outgoing})


def test_export_has_triangle_wires_hardware_and_executable_script_syntax(assembly):
    data=primitive_glb(assembly['cad']['primitives'])
    length=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+length])
    assert doc['asset']['generator']=='panelstudio-primitives/2'
    wires=[n for n in doc['nodes'] if n.get('extras',{}).get('route_id')]
    assert len(wires)==len(assembly['pdm']['routes'])
    assert all(doc['meshes'][n['mesh']]['primitives'][0]['mode']==4 for n in wires)
    assert any(n.get('extras',{}).get('assembly_group')=='DOOR' for n in doc['nodes'])
    script=CADEngine().export_freecad_script(PhysicalDesignModel(**assembly['pdm']))
    compile(script,'generated-panel.py','exec')
    assert 'Part.makeCylinder' in script


def test_disconnected_ducts_fail_instead_of_routing_through_free_air():
    from app.algorithms.duct_routing import DuctRouter
    from app.algorithms.cp_sat_placement import LayoutResult
    from app.algorithms.jps_theta_star import RoutePlanningError
    from app.models.pdm import PhysicalComponent,Position3D,CableDuct
    from app.models.cem import NetRef,ConnectionRef
    def device(key,x,tx):
        return PhysicalComponent(id='PDM-'+key,cem_component_id=key,name=key,category='TERMINAL',
            position=Position3D(x=x,y=80,z=20),width=20,height=20,depth=20,zone_name='TERMINAL',
            heat_loss_watts=0,cad_model='',terminals=[{'id':'T','x':tx,'y':10,'z':10}])
    parts=[device('A',95,0),device('B',185,20)]
    ducts=[CableDuct(id=key,label=key,x=x,y=20,z=10,width=40,height=160,depth=60,orientation='VERTICAL') for key,x in [('LEFT',40),('RIGHT',220)]]
    net=NetRef(id='N',name='Test',voltage_level=230,wire_class='POWER',connections=[ConnectionRef(
        id='C',net_id='N',from_component='A',from_terminal='T',to_component='B',to_terminal='T')])
    with pytest.raises(RoutePlanningError,match='disconnected'):
        DuctRouter().route_layout(LayoutResult(True,'FEASIBLE',components=parts),[net],300,200,120,ducts=ducts)


def test_hardware_catalog_and_revision_projections_are_persisted(api,postgres_database):
    from sqlalchemy import select,func
    from app.persistence import models as m
    from app.persistence.repositories import identifier
    from app.persistence.import_panel_hardware import import_panel_hardware
    p=api.post('/api/projects',json={'name':'Mechanical assembly'}).json()
    response=api.post('/api/projects/'+p['id']+'/revisions',json={'expected_version':p['lock_version']})
    assert response.status_code==201,response.text
    design=response.json();rid=identifier(design['revision_id'])
    assert len(design['pdm']['accessories'])>=10
    assert all(a['component_version_id'] for a in design['pdm']['accessories'])
    with postgres_database.sessions() as s:
        records=s.execute(select(m.pdm_mounting_structures).where(m.pdm_mounting_structures.c.project_revision_id==rid)).mappings().all()
        assert len([r for r in records if r['structure_kind']=='WIRE_DUCT'])==len(design['pdm']['ducts'])
        assert len([r for r in records if r['structure_kind']=='OTHER'])==len(design['pdm']['accessories'])
        count=s.scalar(select(func.count()).select_from(m.component_versions))
    import_panel_hardware(postgres_database)
    with postgres_database.sessions() as s:
        assert s.scalar(select(func.count()).select_from(m.component_versions))==count
    reopened=api.get('/api/projects/'+p['id']+'/design').json()
    assert reopened['pdm']==design['pdm'] and reopened['snapshot_sha256']==design['snapshot_sha256']
    terminal=api.get('/api/components/TERMINAL_BLOCK_3P_6MM').json()
    assert len(terminal['terminals'])==6 and terminal['cad_models'][0]['version_no']==2
    accessories=api.get('/api/components/ENC_800_1000_300/accessories').json()
    assert any(a['category']=='DOOR' for a in accessories)
