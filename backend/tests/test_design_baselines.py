"""Independent relational/geometric assertions plus exact observed regression pins."""
import copy
import json
import math

import pytest
from shapely.geometry import LineString, box
from shapely.ops import unary_union

from app.algorithms.jps_theta_star import RoutePlanningError
from app.models.cem import CanonicalEngineeringModel
from app.models.pdm import PhysicalDesignModel
from app.persistence.assets import content_hash
from app.services.design_errors import DesignError
from app.services.validation_engine import ValidationEngine
from tests.design_baseline_support import (
    CASES, FIXTURES, artifacts, engine, generate, observation, pins,
    placement_failure, route_failure, routing_inputs,
)


@pytest.fixture(scope='module', params=CASES['feasible'], ids=lambda c: c['id'])
def board(request):
    return request.param, generate(request.param)


def test_input_and_version_pins():
    assert pins() == json.loads((FIXTURES / 'pins.json').read_text())


def test_exact_observed_output_and_artifact_hashes(board):
    case, package = board
    expected = json.loads((FIXTURES / (case['id']+'.observed.json')).read_text())
    assert observation(package) == expected
    # A second independent solve must match without deleting IDs, coordinates,
    # solver details or float precision. There are no timestamps to normalize.
    assert observation(generate(case)) == expected
    compile(artifacts(package)['assembly.py'], 'assembly.py', 'exec')


def test_semantic_identity_and_physical_acceptance(board):
    case, package = board
    cem, pdm = package['cem'], package['pdm']
    components = {c['id']: c for c in cem['components']}
    placed = {c['cem_component_id']: c for c in pdm['components']}
    connections = {c['id']: c for c in cem['connections']}
    routes = {r['conductor_id']: r for r in pdm['routes']}
    assert len(components) == len(cem['components']) == 2*case['num_feeders']+5
    assert len(placed) == len(pdm['components']) == len(components)
    assert set(components) == set(placed)
    assert len(connections) == len(cem['connections']) == len(routes) == len(pdm['routes'])
    assert set(connections) == set(routes)
    assert {w['id'] for w in package['schematic']['wires']} == set(connections)
    flattened = [c for n in cem['nets'] for c in n['connections']]
    assert flattened == cem['connections']
    assert len({n['id'] for n in cem['nets']}) == len(cem['nets'])
    for net in cem['nets']:
        assert all(c['net_id'] == net['id'] for c in net['connections'])
    assert cem['state'] == 'FINAL_VALIDATED'
    assert cem['physical_design_id'] == pdm['id']
    assert cem['project_id'] == pdm['project_id'] == cem['electrical_graph']['project_id'] == case['project_id']
    assert pdm['enclosure_id'] == case['observed_enclosure']
    assert package['validation_errors'] == pdm['validation_results'] == []
    assert ValidationEngine().validate_pdm(PhysicalDesignModel(**pdm), CanonicalEngineeringModel(**cem)) == []

    # Separate geometry calculation: containment and AABB separation, without
    # calling the production validator for the independent decision.
    plate = box(pdm['mounting_plate_x'], pdm['mounting_plate_y'],
                pdm['mounting_plate_x']+pdm['mounting_plate_width'],
                pdm['mounting_plate_y']+pdm['mounting_plate_height'])
    ducts = {d['id']: d for d in pdm['ducts']}
    network = unary_union([box(d['x'], d['y'], d['x']+d['width'], d['y']+d['height']) for d in ducts.values()])
    for c in pdm['components']:
        p = c['position']
        footprint = box(p['x'], p['y'], p['x']+c['width'], p['y']+c['height'])
        assert plate.covers(footprint)
        assert footprint.intersection(network).area < 1e-6
        assert {t['id'] for t in c['terminals']} == {t['id'] for t in components[c['cem_component_id']]['terminals']}
        assert len({t['id'] for t in c['terminals']}) == len(c['terminals'])
    for i, a in enumerate(pdm['components']):
        for b in pdm['components'][i+1:]:
            ax, ay, bx, by = a['position']['x'], a['position']['y'], b['position']['x'], b['position']['y']
            gap = max(bx-ax-a['width'], ax-bx-b['width'], by-ay-a['height'], ay-by-b['height'])
            policy = pdm['validation_policy']
            required = (policy['din_clearance_mm'] if a['rail_id'] and a['rail_id'] == b['rail_id']
                        else policy['plate_clearance_mm'] if not a['rail_id'] or not b['rail_id'] else 0)
            assert gap >= required-1e-6
    for key, conn in connections.items():
        route = routes[key]
        assert route['id'] == 'ROUTE-'+key
        for field in ('net_id', 'from_component', 'from_terminal', 'to_component', 'to_terminal'):
            assert route[field] == conn[field]
        for side, endpoint in (('from', route['waypoints'][0]), ('to', route['waypoints'][-1])):
            cid, tid = conn[side+'_component'], conn[side+'_terminal']
            if cid == 'PANEL_ROOT':
                assert tid == 'EARTH_STUD'
                continue
            terminal = next(t for t in components[cid]['terminals'] if t['id'] == tid)
            assert endpoint == {axis: round(placed[cid]['position'][axis]+terminal[axis], 1) for axis in ('x','y','z')}
        assert route['duct_ids'] and set(route['duct_ids']) <= set(ducts)
        trunk = route['waypoints'][route['duct_entry_index']:route['duct_exit_index']+1]
        assert len(trunk) >= 2
        assert network.covers(LineString([(p['x'],p['y']) for p in trunk]))
        assert route['geometry']['route_id'] == route['id']
        assert route['geometry']['centerline'][0] == route['waypoints'][0]
        assert route['geometry']['centerline'][-1] == route['waypoints'][-1]
    for duct in ducts.values():
        assert set(duct['route_ids']) == {r['id'] for r in routes.values() if duct['id'] in r['duct_ids']}
    cad_routes = {p['route_id']: p for p in package['cad']['primitives'] if p.get('route_id')}
    assert set(cad_routes) == {r['id'] for r in routes.values()}
    for route in routes.values():
        assert cad_routes[route['id']]['points'] == route['geometry']['centerline']
    assert {p['cem_component_id'] for p in package['cad']['primitives'] if p.get('cem_component_id')} == set(components)
    assert {item['component_id'] for item in package['bom']} == set(components) | {
        item['id'] for group in ('accessories','ducts','rails') for item in pdm[group]}


def test_independent_arithmetic_is_separate_from_observations(board):
    case, package = board
    expected = CASES['independent_expectations']
    calc = {c['type']: c['value'] for c in package['cem']['calculations']}
    assert round(math.sqrt(3)*415*250/1000, 2) == expected['apparent_capacity_kva']['rounded_value'] == calc['total_capacity']
    assert 250*0.75*1.20 == expected['design_current_a']['value'] == calc['design_current']
    assert 250*1.25 == expected['busbar_minimum_a']['unrounded_value']
    assert round(250*1.25) == expected['busbar_minimum_a']['observed_rounded_value'] == calc['busbar_rating']
    assert min(c['current_rating'] for c in package['cem']['components'] if c['category'] == 'BUSBAR') >= 312.5
    pdm = package['pdm']
    heat = sum(c['heat_loss'] for c in package['cem']['components'])
    litres = pdm['enclosure_width']*pdm['enclosure_height']*pdm['enclosure_depth']/1e6
    assert pdm['total_heat_loss_watts'] == heat
    assert heat/litres <= pdm['validation_policy']['thermal_density_limit_w_per_l']
    # Do not equate zero physical violations with fully resolved engineering.
    assert any(check['status'] == 'UNRESOLVED' for r in pdm['routes'] for check in r['validation_checks'])


@pytest.mark.parametrize('case', CASES['failures'], ids=lambda c: c['id'])
def test_real_failure_cases(case):
    if case['stage'] == 'placement':
        assert case['component_mm'][0] > case['enclosure_mm'][0]-120
        result = placement_failure(case)
        assert result.feasible is False
        assert result.status == case['expected_status']
        assert result.message == case['expected_message']
        assert result.components == []
    elif case['stage'] == 'generation':
        subject = engine(case, case['enclosure_id'])
        before = copy.deepcopy(subject.project_repo.get_by_id(case['project_id']))
        with pytest.raises(DesignError) as failure:
            subject.generate_design(case['project_id'], persist_requirements=False)
        assert failure.value.code == case['expected_code']
        assert failure.value.details['minimum_volume_litres'] > 240
        assert subject.project_repo.get_by_id(case['project_id']) == before
    else:
        layout, nets, ducts = routing_inputs(case)
        shapes = [box(d.x,d.y,d.x+d.width,d.y+d.height) for d in ducts]
        if case['wall'] is None:
            assert shapes[0].distance(shapes[1]) == 140
        else:
            wall = layout.components[-1]
            assert wall.position.y == 0 and wall.height == case['enclosure_mm'][1]
            assert unary_union(shapes).geom_type == 'Polygon'
        with pytest.raises(RoutePlanningError) as failure:
            route_failure(case)
        assert failure.value.connection_id == nets[0].connections[0].id == 'C'
        assert failure.value.net_id == 'N'
        assert failure.value.reason == case['expected_reason']


def test_comparison_does_not_mask_identity_geometry_or_engineering_changes(board):
    _, package = board
    original = content_hash(package)
    for section, mutate in (
        ('cem', lambda d: d['components'][0].update(id='changed')),
        ('pdm', lambda d: d['components'][0]['position'].update(x=0.001)),
        ('pdm', lambda d: d['routes'][0].update(to_terminal='changed')),
        ('cem', lambda d: d['calculations'][0].update(value=0)),
    ):
        altered = copy.deepcopy(package)
        mutate(altered[section])
        assert content_hash(altered) != original
