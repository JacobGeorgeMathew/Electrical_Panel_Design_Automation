"""Physical adapter extraction equivalence and strict CAD eligibility contracts."""
import builtins
import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.algorithms.cp_sat_placement import LayoutResult
from app.algorithms.duct_routing import DuctRouter
from app.algorithms.jps_theta_star import JPSThetaStarRouter
from app.algorithms.layout_config import LayoutConfig
from app.models.cem import CanonicalEngineeringModel, ComponentRef
from app.models.document import GenerationIntent
from app.models.pdm import EnclosureSpec, PhysicalDesignModel, ValidationViolation
from app.persistence.assets import content_hash, primitive_glb
from app.services.cad_engine import CADEngine
from app.services.design_errors import DesignError
from app.services.stages.artifacts import BOMInput, CADInput, bom_stage, cad_stage
from app.services.stages.contracts import STAGE_REGISTRY
from app.services.stages.electrical import DocumentIdentities, ElectricalContext, IdentityBinding, Snapshot
from app.services.stages.physical import (
    DuctsInput, EnclosureInput, GeometryInput, LayoutSnapshot, PhysicalSnapshot, PhysicalValidationInput,
    PinnedEnclosures, PinnedHardware, PlacementInput, RoutesInput, ZoningInput,
    ducts_stage, enclosure_stage, local_geometry_stage, physical_validation_stage,
    placement_stage, routes_stage, zoning_stage,
)
from tests.design_baseline_support import CASES, FIXTURES, engine, routing_inputs


def supplied(case, full):
    oracle = engine(case)
    return EnclosureInput(
        context=ElectricalContext(project_id=case['project_id'], panel_id='DB-'+case['project_id'],
                                  engine_version='fixture-engine-1'),
        cem=Snapshot[CanonicalEngineeringModel].capture(full['cem']),
        catalog=PinnedEnclosures(catalog_version='fixture-enclosures-1',
            rows=Snapshot[list[EnclosureSpec]].capture(oracle.enclosure_repo.get_all())),
        layout=LayoutSnapshot.capture(oracle.layout_config), ip_rating='IP54',
    ), PinnedHardware(catalog_version='fixture-hardware-1',
                      rows=Snapshot[list[dict]].capture(list(oracle.panel_assembly.catalog.values())))


def execute(inputs, hardware):
    candidates = enclosure_stage(inputs)
    attempts = []
    for enclosure in candidates.candidates.read():
        zoning = zoning_stage(ZoningInput(enclosure=Snapshot[EnclosureSpec].capture(enclosure),
                                          layout=inputs.layout, hardware=hardware))
        placement_input = PlacementInput(context=inputs.context, cem=inputs.cem, zoning=zoning)
        try:
            placed = placement_stage(placement_input)
            ducts = ducts_stage(DuctsInput(placement=placed))
            routed = routes_stage(RoutesInput(context=inputs.context, cem=inputs.cem,
                                              pdm=ducts.pdm, layout=zoning.layout))
            validated = physical_validation_stage(PhysicalValidationInput(
                context=inputs.context, cem=inputs.cem, pdm=routed.pdm))
        except DesignError as exc:
            if exc.code not in {'PLACEMENT_INFEASIBLE', 'PLACEMENT_INVALID', 'ROUTING_INFEASIBLE',
                                'PHYSICAL_VALIDATION_FAILED', 'DUCT_SPACE_INFEASIBLE'}:
                raise
            attempts.append(exc.code)
            continue
        return placement_input, (candidates, zoning, placed, ducts, routed, validated), attempts
    raise AssertionError('No feasible adapter candidate: '+repr(attempts))


def cad_input(inputs, pdm, **kwargs):
    return CADInput(context=inputs.context, cem=inputs.cem, pdm=pdm,
        schematic=Snapshot[dict].capture({}), generator_version='panelstudio-primitives/3',
        model_versions=Snapshot[dict[str, str]].capture({}), **kwargs)


@pytest.fixture(scope='module', params=CASES['feasible'], ids=lambda c: c['id'])
def board(request):
    case = request.param
    full = engine(case).generate_design(case['project_id'], persist_requirements=False)
    inputs, hardware = supplied(case, full)
    placement_input, outputs, attempts = execute(inputs, hardware)
    return case, full, inputs, hardware, placement_input, outputs, attempts


def test_exact_baseline_pdm_cad_bom_and_export(board):
    case, full, inputs, _, _, outputs, _ = board
    pdm = outputs[-1].pdm
    assert outputs[-2].pdm == pdm  # Routes already owns checked wire geometry.
    assert all(c.geometry for c in outputs[3].pdm.read().components)
    result = cad_stage(cad_input(inputs, pdm, include_freecad_script=True))
    bom = bom_stage(BOMInput(context=inputs.context, cem=inputs.cem, pdm=pdm))
    assert pdm.read().model_dump() == full['pdm']
    assert result.cad.read() == full['cad']
    assert bom.bom.read() == full['bom']
    assert result.freecad_script == CADEngine().export_freecad_script(pdm.read())
    compile(result.freecad_script, 'adapter-assembly.py', 'exec')
    baseline = json.loads((FIXTURES / (case['id']+'.observed.json')).read_text())['hashes']
    for field, payload in (('pdm', pdm.read().model_dump()), ('cad', result.cad.read()), ('bom', bom.bom.read())):
        assert content_hash(payload) == baseline[field]['sha256']
    assert hashlib.sha256(result.freecad_script.encode()).hexdigest() == baseline['assembly.py']['sha256']
    assert hashlib.sha256(primitive_glb(result.cad.read()['primitives'], generator_version='3')).hexdigest() == baseline['preview.glb']['sha256']
    assert content_hash(json.loads(pdm.data_json)) == baseline['pdm']['sha256']
    connections = {c.id: c for c in inputs.cem.read().connections}
    components = {c.cem_component_id: c for c in pdm.read().components}
    for route in pdm.read().routes:
        connection = connections[route.conductor_id]
        assert route.id == 'ROUTE-'+connection.id
        for field in ('net_id', 'from_component', 'from_terminal', 'to_component', 'to_terminal'):
            assert getattr(route, field) == getattr(connection, field)
        for component_id, terminal_id, point in (
            (route.from_component, route.from_terminal, route.waypoints[0]),
            (route.to_component, route.to_terminal, route.waypoints[-1]),
        ):
            if component_id != 'PANEL_ROOT':
                expected = JPSThetaStarRouter()._component_terminal(components[component_id], terminal_id)
                assert (point.x, point.y, point.z) == pytest.approx(expected, abs=.11)


def test_registry_declares_routed_duct_accounting():
    routed = STAGE_REGISTRY.by_id['routes'].outputs[0]
    assert set(routed.paths) == {'pdm.routes', 'pdm.ducts.*.route_ids',
                                 'pdm.ducts.*.wire_area_mm2', 'pdm.ducts.*.capacity_pct'}
    validation = STAGE_REGISTRY.by_id['physical_validation']
    consumed = next(i for i in validation.inputs if i.source_stage == 'routes')
    assert set(consumed.paths) == set(routed.paths)


def test_input_output_schema_serialization_and_deep_immutability(board):
    _, _, inputs, hardware, placement_input, outputs, _ = board
    for value in (inputs, hardware, placement_input, *outputs,
                  cad_input(inputs, outputs[-1].pdm), cad_stage(cad_input(inputs, outputs[-1].pdm)),
                  bom_stage(BOMInput(context=inputs.context, cem=inputs.cem, pdm=outputs[-1].pdm))):
        assert type(value).model_validate_json(value.model_dump_json()) == value
        assert type(value).model_json_schema()['properties']
    before = inputs.model_dump_json(), outputs[-1].model_dump_json()
    inputs.cem.read().components.clear()
    outputs[-1].pdm.read().routes[0].waypoints.clear()
    assert before == (inputs.model_dump_json(), outputs[-1].model_dump_json())
    with pytest.raises(ValidationError):
        outputs[-1].pdm.data_json = '{}'
    with pytest.raises(ValidationError):
        EnclosureInput.model_validate({**inputs.model_dump(), 'algorithm_version': 'future'})
    for cls, stage in ((EnclosureInput, 'placement'), (ZoningInput, 'placement'),
        (PlacementInput, 'placement'), (DuctsInput, 'placement'), (RoutesInput, 'routes'),
        (PhysicalValidationInput, 'physical_validation'), (CADInput, 'cad'), (BOMInput, 'bom')):
        assert cls.model_fields['algorithm_version'].default == STAGE_REGISTRY.by_id[stage].algorithm_version
    invalid = outputs[-1].pdm.read()
    invalid.components[0].width = float('nan')
    with pytest.raises((ValueError, ValidationError)):
        PhysicalSnapshot.capture(invalid)


def test_locks_retain_accepted_placement_and_reject_missing_intent(board, monkeypatch):
    _, _, inputs, _, placement_input, outputs, _ = board
    pdm = outputs[-1].pdm
    intent = Snapshot[GenerationIntent].capture(GenerationIntent(
        manual_models=['pdm'], locked_placements=[pdm.read().components[0].cem_component_id]))
    def forbidden(*args, **kwargs):
        raise AssertionError('Locked accepted layout must not invoke the solver')
    from app.algorithms.cp_sat_placement import CPSATPlacementOptimizer
    monkeypatch.setattr(CPSATPlacementOptimizer, 'solve', forbidden)
    with pytest.raises(DesignError) as error:
        placement_stage(placement_input.model_copy(update={'intent': intent}))
    assert error.value.code == 'STAGE_LOCK_CONFLICT'
    retained = placement_stage(placement_input.model_copy(update={'intent': intent, 'accepted_layout': pdm}))
    assert retained.pdm.read().components == pdm.read().components
    assert retained.pdm.read().rails == pdm.read().rails
    assert retained.pdm.read().routes == []
    assert ducts_stage(DuctsInput(placement=retained)).pdm.read().ducts == pdm.read().ducts
    with pytest.raises(DesignError) as error:
        routes_stage(RoutesInput(context=inputs.context, cem=inputs.cem, pdm=pdm,
            layout=placement_input.zoning.layout, locked_route_ids=(pdm.read().routes[0].id,)))
    assert error.value.code == 'STAGE_LOCK_CONFLICT'
    moved_frame = pdm.read()
    moved_frame.mounting_plate_x += 1
    with pytest.raises(DesignError, match='different enclosure frame'):
        placement_stage(placement_input.model_copy(update={
            'intent': intent, 'accepted_layout': PhysicalSnapshot.capture(moved_frame)}))


def test_local_geometry_never_reroutes_and_preserves_all_endpoints(board, monkeypatch):
    _, _, inputs, _, _, outputs, _ = board
    original = outputs[-1].pdm
    stale = original.read()
    for c in stale.components:
        c.geometry = []
    for route in stale.routes:
        route.geometry = None
        route.validation_checks = []
    def forbidden(*args, **kwargs):
        raise AssertionError('Local geometry must not reroute the duct network')
    monkeypatch.setattr(DuctRouter, 'route_layout', forbidden)
    geometry_input = GeometryInput(context=inputs.context, cem=inputs.cem,
                                   pdm=PhysicalSnapshot.capture(stale))
    assert local_geometry_stage(geometry_input).pdm == original
    # A move with old endpoints is stale connectivity, not a local mesh update.
    stale.components[0].position.x += 1
    with pytest.raises(DesignError) as error:
        local_geometry_stage(geometry_input.model_copy(update={'pdm': PhysicalSnapshot.capture(stale)}))
    assert error.value.code == 'PHYSICAL_VALIDATION_FAILED'


@pytest.mark.parametrize('damage', ['overlap', 'endpoint', 'missing_route', 'conductor', 'extra_route', 'no_ducts', 'trunk'])
def test_invalid_geometry_and_references_block_cad_before_engine(board, monkeypatch, damage):
    _, _, inputs, _, _, outputs, _ = board
    pdm = outputs[-1].pdm.read()
    if damage == 'overlap':
        pdm.components[0].position = pdm.components[1].position.model_copy()
    elif damage == 'endpoint':
        pdm.routes[0].waypoints[0].x += 1
    elif damage == 'missing_route':
        pdm.routes.pop()
    elif damage == 'conductor':
        pdm.routes[0].conductor_id = 'wrong'
    elif damage == 'extra_route':
        pdm.routes.append(pdm.routes[0].model_copy(update={'id': 'EXTRA'}))
    elif damage == 'no_ducts':
        pdm.ducts = []
    else:
        route = next(r for r in pdm.routes if r.duct_exit_index > r.duct_entry_index+1)
        route.waypoints[route.duct_entry_index+1].x = pdm.enclosure_width/2
        route.waypoints[route.duct_entry_index+1].y = pdm.enclosure_height-50
    pdm.validation_results = []  # Spoofed saved PASS cannot authorize artifacts.
    def forbidden(*args, **kwargs):
        raise AssertionError('Invalid physical data reached CAD serialization')
    monkeypatch.setattr(CADEngine, 'generate_parametric_geometry', forbidden)
    with pytest.raises(DesignError):
        cad_stage(cad_input(inputs, PhysicalSnapshot.capture(pdm)))


def test_warnings_block_cad(board, monkeypatch):
    _, _, inputs, _, _, outputs, _ = board
    from app.services.validation_engine import ValidationEngine
    monkeypatch.setattr(ValidationEngine, 'validate_pdm', lambda *args: [ValidationViolation(
        type='TEST', severity='WARNING', object_a='ENCLOSURE', required_value=1,
        actual_value=0, unit='prototype', message='Retained physical warning')])
    with pytest.raises(DesignError) as error:
        cad_stage(cad_input(inputs, outputs[-1].pdm))
    assert error.value.code == 'PHYSICAL_VALIDATION_FAILED'


@pytest.mark.parametrize('case', [c for c in CASES['failures'] if c['stage'] == 'routing'], ids=lambda c: c['id'])
def test_disconnected_and_obstructed_networks_fail_without_fallback(case):
    placement, nets, ducts = routing_inputs(case)
    cem = CanonicalEngineeringModel(project_id='ROUTING', panel_id='DB-ROUTING',
        components=[ComponentRef(id=c.cem_component_id, catalog_id=c.cem_component_id,
            name=c.name, category=c.category, width=c.width, height=c.height, depth=c.depth,
            heat_loss=0, terminals=c.terminals, current_rating=0, breaking_capacity=0,
            poles=1, mounting='PLATE', cad_model='') for c in placement.components],
        nets=nets, connections=[c for n in nets for c in n.connections])
    pdm = PhysicalDesignModel(id='PDM-ROUTING', project_id=cem.project_id, panel_id=cem.panel_id,
        enclosure_id='TEST', enclosure_width=300, enclosure_height=200, enclosure_depth=120,
        ip_rating='IP54', components=placement.components, ducts=ducts)
    inputs = RoutesInput(context=ElectricalContext(project_id=cem.project_id, panel_id=cem.panel_id,
        engine_version='fixture-engine-1'), cem=Snapshot[CanonicalEngineeringModel].capture(cem),
        pdm=PhysicalSnapshot.capture(pdm), layout=LayoutSnapshot.capture(LayoutConfig()))
    with pytest.raises(DesignError) as error:
        routes_stage(inputs)
    assert error.value.code in {'ROUTING_INFEASIBLE', 'PHYSICAL_VALIDATION_FAILED'}
    if case['id'] == 'disconnected-ducts':
        assert error.value.details['reason'] == case['expected_reason']
    with pytest.raises(DesignError):
        cad_stage(cad_input(inputs, inputs.pdm))
    assert inputs.pdm.read().routes == []


def test_fixed_enclosure_and_invalid_solver_output_are_not_waived(board, monkeypatch):
    _, _, inputs, _, placement_input, _, _ = board
    with pytest.raises(DesignError) as error:
        enclosure_stage(inputs.model_copy(update={'enclosure_id': 'ENC_800_1000_300'}))
    assert error.value.code == 'NO_FEASIBLE_ENCLOSURE'
    from app.algorithms.cp_sat_placement import CPSATPlacementOptimizer
    placed = placement_stage(placement_input).pdm.read()
    placed.components[0].position = placed.components[1].position.model_copy()
    monkeypatch.setattr(CPSATPlacementOptimizer, 'solve', lambda *args: LayoutResult(
        True, 'FEASIBLE', components=placed.components, rails=placed.rails))
    with pytest.raises(DesignError) as error:
        placement_stage(placement_input)
    assert error.value.code == 'PLACEMENT_INVALID'


def test_mapped_document_ids_retain_terminal_and_route_references(board):
    _, _, inputs, hardware, _, outputs, _ = board
    cem = inputs.cem.read()
    namespaces = {'component': [c.id for c in cem.components], 'net': [n.id for n in cem.nets],
                  'connection': [c.id for c in cem.connections]}
    identities = DocumentIdentities(bindings=tuple(IdentityBinding(namespace=namespace, role=role,
        document_id=f'opaque:{namespace}:{len(values)-index:03d}')
        for namespace, values in namespaces.items() for index, role in enumerate(values)))
    for component in cem.components:
        component.id = identities.resolve('component', component.id)
    for module in cem.modules:
        if module.assigned_component_id:
            module.assigned_component_id = identities.resolve('component', module.assigned_component_id)
    for node in cem.electrical_graph.nodes:
        node.id = identities.resolve('component', node.id)
    for edge in cem.electrical_graph.edges:
        edge.source = identities.resolve('component', edge.source)
        edge.target = identities.resolve('component', edge.target)
        edge.properties['net_ids'] = [identities.resolve('net', n) for n in edge.properties['net_ids']]
    for net in cem.nets:
        net.id = identities.resolve('net', net.id)
        for c in net.connections:
            c.id = identities.resolve('connection', c.id)
            c.net_id = net.id
            c.from_component = identities.resolve('component', c.from_component)
            c.to_component = identities.resolve('component', c.to_component)
    cem.connections = [c for n in cem.nets for c in n.connections]
    mapped_input = inputs.model_copy(update={
        'context': inputs.context.model_copy(update={'identities': identities}),
        'cem': Snapshot[CanonicalEngineeringModel].capture(cem)})
    mapped = execute(mapped_input, hardware)[1][-1].pdm.read()
    original = outputs[-1].pdm.read()
    for a, b in zip(original.components, mapped.components):
        assert b.cem_component_id == identities.resolve('component', a.cem_component_id)
        assert b.position == a.position and b.terminals == a.terminals
    for a, b in zip(original.routes, mapped.routes):
        assert b.id == 'ROUTE-'+identities.resolve('connection', a.conductor_id)
        assert b.conductor_id == identities.resolve('connection', a.conductor_id)
        assert b.net_id == identities.resolve('net', a.net_id)
        assert b.from_component == identities.resolve('component', a.from_component)
        assert b.to_component == identities.resolve('component', a.to_component)
        assert (b.from_terminal, b.to_terminal) == (a.from_terminal, a.to_terminal)
        assert b.waypoints == a.waypoints and b.geometry.centerline == a.geometry.centerline
        assert b.wire_diameter_mm == a.wire_diameter_mm and b.color_hex == a.color_hex


def test_execution_has_no_file_repository_or_database_io(board, monkeypatch):
    _, _, inputs, hardware, _, outputs, _ = board
    def forbidden(*args, **kwargs):
        raise AssertionError('Detached physical stage attempted I/O')
    from app.repositories.enclosure_repository import EnclosureRepository
    from app.services import panel_assembly
    from app.persistence import repositories
    from sqlalchemy.orm import Session
    for cls in (EnclosureRepository, repositories.MemoryEnclosures, repositories.CatalogRepository):
        monkeypatch.setattr(cls, '__init__', forbidden)
    monkeypatch.setattr(panel_assembly, 'fixture_hardware', forbidden)
    monkeypatch.setattr(Session, 'execute', forbidden)
    monkeypatch.setattr(Session, 'begin', forbidden)
    monkeypatch.setattr(builtins, 'open', forbidden)
    monkeypatch.setattr(Path, 'open', forbidden)
    assert execute(inputs, hardware)[1][-1] == outputs[-1]
    assert cad_stage(cad_input(inputs, outputs[-1].pdm)).cad.read()['validation_results'] == []
    assert bom_stage(BOMInput(context=inputs.context, cem=inputs.cem, pdm=outputs[-1].pdm)).bom.read()
