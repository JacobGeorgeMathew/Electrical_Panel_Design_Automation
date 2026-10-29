import math
import pytest
from pydantic import ValidationError
from shapely.geometry import LineString,box
from app.algorithms.schematic_routing import orthogonal_route
from app.services.wire_geometry import circular_centerline,segment_hits_box
from app.models.pdm import Waypoint3D

@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_coordinates_rejected(value):
    with pytest.raises(ValidationError):Waypoint3D(x=value,y=0,z=0)

@pytest.mark.parametrize('points',[
 [(0,0,0),(30,0,0)],[(0,0,0),(30,0,0),(30,30,0)],
 [(0,0,0),(30,0,0),(30,30,0),(30,30,30)],
 [(0,0,0),(0,0,0),(30,0,0),(30,30,0)]])
def test_centerline_preserves_endpoints_and_is_finite(points):
    result,radii=circular_centerline(points,minimum_radius=4)
    assert result[0]==points[0] and result[-1]==points[-1]
    assert all(math.isfinite(v) for p in result for v in p)
    assert all(r==4 for r in radii)
    assert all(math.dist(a,b)>1e-8 for a,b in zip(result,result[1:]))

@pytest.mark.parametrize('points', [[(0,0,0)],[(0,0,0),(1,0,0),(1,1,0)],[(0,0,0),(1,0,0),(0,0,0)]])
def test_impossible_geometry_rejected(points):
    with pytest.raises(ValueError):circular_centerline(points,minimum_radius=10)


def test_three_dimensional_collision_is_not_projected_intersection():
    assert not segment_hits_box((-1,5,20),(11,5,20),(0,0,0),(10,10,10))
    assert segment_hits_box((-1,5,5),(11,5,5),(0,0,0),(10,10,10))

@pytest.mark.parametrize('obstacles', [[],[(40,-10,60,10)],[(40,-10,60,10),(70,-40,80,5)]])
def test_orthogonal_search_avoids_symbol_and_text_obstacles(obstacles):
    path=orthogonal_route((0,0),(100,0),obstacles,tracks=[-60,60])
    assert path[0]==(0,0) and path[-1]==(100,0)
    assert all(a[0]==b[0] or a[1]==b[1] for a,b in zip(path,path[1:]))
    assert not any(LineString(path).crosses(box(*r)) for r in obstacles)


def test_blocked_drawing_has_explicit_failure():
    with pytest.raises(ValueError):orthogonal_route((50,0),(100,0),[(40,-10,60,10)])
from app.services.orchestrator import DesignOrchestrator
from app.models.pdm import PhysicalDesignModel
from app.models.cem import CanonicalEngineeringModel
from app.services.physical_routing import reroute_placement

@pytest.fixture(scope='module')
def generated():
    return DesignOrchestrator().generate_design('WIRE-INTEGRATION',persist_requirements=False)


def test_schematic_ports_routes_and_identity_match_netlist(generated):
    cem=generated['cem'];drawing=generated['schematic']
    expected={c['id'] for n in cem['nets'] for c in n['connections']}
    assert {w['id'] for w in drawing['wires']}==expected
    ports={(s['id'],t['id']):(t['x'],t['y']) for s in drawing['symbols'] for t in s['terminals']}
    for w in drawing['wires']:
        pts=[(p['x'],p['y']) for p in w['waypoints']]
        assert pts[0]==ports[w['from'],w['from_terminal']]
        assert pts[-1]==ports[w['to'],w['to_terminal']]
        assert all(a[0]==b[0] or a[1]==b[1] for a,b in zip(pts,pts[1:]))
        assert all(not p['connected'] for p in w['crossings'])
    assert {w['wire_class'] for w in drawing['wires']}=={'POWER','NEUTRAL','PE'}


def test_geometry_contract_round_trip_and_cad_share_centerline(generated):
    from app.services.cad_engine import CADEngine
    pdm=PhysicalDesignModel(**generated['pdm'])
    assert pdm==PhysicalDesignModel.model_validate_json(pdm.model_dump_json())
    primitives={p['route_id']:p for p in CADEngine().generate_parametric_geometry(pdm)['primitives'] if p['type']=='TUBE'}
    for r in pdm.routes:
        assert r.geometry.status=='PASS'
        assert r.geometry.centerline[0]==r.waypoints[0]
        assert r.geometry.centerline[-1]==r.waypoints[-1]
        assert primitives[r.id]['points']==[p.model_dump() for p in r.geometry.centerline]
        assert any(c['type']=='MANUFACTURER_BEND_RADIUS' and c['status']=='UNRESOLVED' for c in r.geometry.checks)
    compile(CADEngine().export_freecad_script(pdm),'<freecad-script>','exec')


def test_component_movement_reroutes_endpoints_and_preserves_ids(generated):
    pdm=PhysicalDesignModel(**generated['pdm']);cem=CanonicalEngineeringModel(**generated['cem'])
    old_ids=[r.id for r in pdm.routes]
    target=next(c for c in pdm.components if c.category=='MCB');target.position.y+=5
    old={r.id:r.waypoints for r in pdm.routes}
    result=reroute_placement(pdm,cem)
    assert result.validation_results==[]
    assert [r.id for r in result.routes]==old_ids
    assert any(r.waypoints!=old[r.id] for r in result.routes if r.to_component==target.cem_component_id)


@pytest.mark.parametrize('change',['blocked','capacity','class','rotation'])
def test_invalid_reroute_discards_geometry_explicitly(generated,change):
    pdm=PhysicalDesignModel(**generated['pdm']);cem=CanonicalEngineeringModel(**generated['cem'])
    if change=='blocked':pdm.ducts=[]
    if change=='capacity':
        for d in pdm.ducts:d.max_fill_pct=.001
    if change=='class':
        for d in pdm.ducts:d.allowed_wire_classes=['CONTROL']
    if change=='rotation':pdm.components[0].rotation_deg=90
    result=reroute_placement(pdm,cem)
    assert not result.routes
    assert any(v.severity=='CRITICAL' for v in result.validation_results)


def test_duct_paths_are_orthogonal_and_metrics_match(generated):
    from app.algorithms.jps_theta_star import JPSThetaStarRouter
    pdm=PhysicalDesignModel(**generated['pdm'])
    for r in pdm.routes:
        assert r.conductor_id==r.id.removeprefix('ROUTE-')
        points=[(p.x,p.y,p.z) for p in r.waypoints]
        assert abs(r.length_mm-JPSThetaStarRouter()._path_length(points))<.11
        trunk=points[r.duct_entry_index:r.duct_exit_index+1]
        assert all(sum(abs(a[k]-b[k])>1e-6 for k in range(3))<=1 for a,b in zip(trunk,trunk[1:]))
@pytest.mark.parametrize('branches,wire_class',[(1,'POWER'),(3,'POWER'),(2,'NEUTRAL'),(2,'PE')])
def test_schematic_branch_topology_is_not_replaced_by_centroid(branches,wire_class):
    from app.models.cem import CanonicalEngineeringModel,ComponentRef,NetRef,ConnectionRef
    from app.services.schematic_engine import SchematicEngine
    def part(key,category,terminal):
        return ComponentRef(id=key,catalog_id=key,name=key,category=category,current_rating=10,breaking_capacity=6,poles=1,
            width=20,height=40,depth=20,mounting='DIN',heat_loss=1,cad_model='',terminals=[{'id':terminal,'x':10,'y':40,'z':10}])
    components=[part('SOURCE','BUSBAR','OUT')]+[part('LOAD'+str(i),'TERMINAL','IN') for i in range(branches)]
    connections=[ConnectionRef(id='C'+str(i),net_id='N',from_component='SOURCE',from_terminal='OUT',to_component='LOAD'+str(i),to_terminal='IN',wire_class=wire_class) for i in range(branches)]
    cem=CanonicalEngineeringModel(project_id='P',panel_id='P',components=components,nets=[NetRef(id='N',name='N',voltage_level=230,wire_class=wire_class,connections=connections)])
    data=SchematicEngine().generate_schematic_data(cem)
    assert {s['id'] for s in data['symbols']}=={c.id for c in components}|{'PANEL_ROOT'}
    assert [w['id'] for w in data['wires']]==[c.id for c in connections]
    assert all('C' not in w['svg_path'] and 'Q' not in w['svg_path'] for w in data['wires'])
    assert all(p['connected'] is False for w in data['wires'] for p in w['crossings'])
    if branches>1:assert any(p['connected'] and p.get('port_id')=='SOURCE:OUT' for w in data['wires'] for p in w['junctions'])

def test_smoothing_collision_is_rejected_and_recovery_is_possible():
    from app.models.pdm import PhysicalComponent,Position3D,WireRoute
    from app.services.wire_geometry import build_wire_geometry
    pdm=PhysicalDesignModel(id='P',project_id='P',panel_id='P',enclosure_id='E',enclosure_width=100,enclosure_height=100,enclosure_depth=100,ip_rating='IP54')
    route=WireRoute(id='R',net_id='N',net_name='N',from_component='A',from_terminal='OUT',to_component='B',to_terminal='IN',
        wire_class='POWER',waypoints=[Waypoint3D(x=20,y=20,z=20),Waypoint3D(x=50,y=20,z=20),Waypoint3D(x=50,y=50,z=20)],length_mm=60,bend_count=1)
    obstacle=PhysicalComponent(id='PDM-O',cem_component_id='O',name='O',category='RELAY',position=Position3D(x=47,y=22,z=19),
        width=1,height=1,depth=2,zone_name='CONTROL',heat_loss_watts=0,cad_model='')
    pdm.components=[obstacle]
    with pytest.raises(ValueError,match='intersects'):build_wire_geometry(route,pdm)
    pdm.components=[]
    assert build_wire_geometry(route,pdm).status=='PASS'

def test_unvalidated_wire_cannot_be_exported(generated):
    from app.services.cad_engine import CADEngine
    from app.services.design_errors import DesignError
    pdm=PhysicalDesignModel(**generated['pdm']);pdm.routes[0].geometry=None
    cad=CADEngine()
    assert cad.generate_parametric_geometry(pdm)['validation_results'][0]['status']=='UNRESOLVED'
    with pytest.raises(DesignError) as failure:cad.export_freecad_script(pdm)
    assert failure.value.code=='WIRE_GEOMETRY_UNVALIDATED'
