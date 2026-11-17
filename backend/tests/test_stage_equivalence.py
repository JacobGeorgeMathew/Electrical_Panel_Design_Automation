"""Operation/dependency acceptance matrix with real adapter-call accounting.

The legacy generator is an independent oracle for automatic DB designs. Manual
intent has no legacy equivalent: compare a forced full stage pass, including
explicit reconciliation failures, and require retained projections to match.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
import re
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.models.document import GenerationIntent
from app.models.cem import CanonicalEngineeringModel
from app.models.operations import OperationPreviewRequest
from app.persistence import models as m
from app.services.design_errors import DesignError
from app.services.operations.engineering import EngineeringChoices
from app.services.operations.registry import REGISTRY, preview_operations
from app.services.stages import electrical as e
from app.services.stages.cache import ADAPTERS, StageCache
from app.services.stages.contracts import STAGE_REGISTRY
from app.services.stages.scheduler import IncrementalScheduler
from tests.design_baseline_support import CASES, engine
from tests.integrity_support import privileged_connection
from tests.test_incremental_scheduler import material, rehash


ALL = ('requirements', 'calculations', 'selection', 'connectivity', 'schematic',
       'placement', 'routes', 'physical_validation', 'bom', 'cad')
PHYSICAL = ('placement', 'routes', 'physical_validation', 'bom', 'cad')
ELECTRICAL = ALL[1:]
SCHEMATIC = ('schematic', 'cad')
ROUTES = ('routes', 'physical_validation', 'cad')
# Deliberately independent expectations: do not derive the expected closure or
# invocation count from the production invalidation implementation being tested.
OPERATION_STAGES = {
    'ApplyGeneration': (), 'MoveComponent': ROUTES, 'RotateComponent': (),
    'UpdateRequirement': ALL, 'ChangeComponentRating': ELECTRICAL,
    'ResizeEnclosure': PHYSICAL, 'AddComponent': ELECTRICAL, 'RemoveComponent': ELECTRICAL,
    'MoveSymbol': SCHEMATIC, 'UpdateSchematicLabel': SCHEMATIC,
    'UpdateJunctionPresentation': SCHEMATIC, 'ModifyElectricalConnection': ALL[3:],
    'RegenerateSchematic': SCHEMATIC,
}


@pytest.fixture(scope='module')
def board():
    return material(CASES['feasible'][0])


def operation(base, kind, target, parameters, **extra):
    definition = REGISTRY[kind]
    hashes = {name: getattr(base.document.models, name).sha256 for name in definition.models}
    origin = dict(kind='AUTOMATIC' if kind == 'ApplyGeneration' else 'MANUAL', actor_id='equivalence-client')
    if extra.get('proposal_status') == 'PROPOSED':
        origin['proposal_id'] = 'reviewed-equivalence-proposal'
    return OperationPreviewRequest.model_validate(dict(batch_id=str(uuid4()),
        document_id=base.document.document_id, base_sequence=base.document.document_sequence,
        expected_version=base.document.lock_version, base_revision_id=base.document.base_revision_id,
        operations=[dict(type=kind, operation_id=str(uuid4()),
            origin=origin, target=target, parameters=parameters,
            preconditions=dict(snapshot_sha256=hashes[definition.model],
                model_sha256=hashes if len(hashes) > 1 else {}), **extra)]))


def changed_board(board, kind):
    base, inputs, _ = deepcopy(board)
    choices = EngineeringChoices()
    pdm, cem, page = base.snapshots.pdm, base.snapshots.cem, base.snapshots.schematic
    part = max((c for c in pdm.components if c.rail_id), key=lambda c: c.position.x + c.width)
    if kind in ('MoveComponent', 'RotateComponent'):
        target = dict(cem_component_id=part.cem_component_id, pdm_component_id=part.id)
        position = part.position.model_dump()
        position['x'] += 1
        parameters = dict(position_mm=position) if kind == 'MoveComponent' else dict(rotation_deg=0)
    elif kind == 'UpdateRequirement':
        target, parameters = dict(requirement_id='spare_capacity_pct'), dict(value=21)
        from app.models.requirements import QuestionSchema
        choices = EngineeringChoices(questions=tuple(QuestionSchema.model_validate(q)
            for q in inputs.requirements.rules.template.read()['questions']))
        answers = inputs.requirements.answers.read()
        answers['spare_capacity_pct'] = 21
        inputs = replace(inputs, requirements=inputs.requirements.model_copy(update={'answers': e.Snapshot[dict].capture(answers)}))
    elif kind == 'ChangeComponentRating':
        component = next(c for c in cem.components if c.id == part.cem_component_id)
        row = component.model_dump(mode='json')
        row.update(code='fixture-rating-33', id='fixture-rating-33',
                   component_version_id='fixture-rating-version', current_rating=component.current_rating + 1)
        inputs = replace(inputs, components=inputs.components.model_copy(update={
            'rows': e.Snapshot[list[dict]].capture([*inputs.components.rows.read(), row])}))
        target = dict(cem_component_id=component.id)
        parameters = dict(catalog_id=row['code'], component_version_id=row['component_version_id'],
                          current_rating=row['current_rating'])
        choices = EngineeringChoices(components={row['component_version_id']: row})
    elif kind == 'ResizeEnclosure':
        row = next(c for c in inputs.enclosures.rows.read() if c.id != pdm.enclosure_id
                   and c.width >= pdm.enclosure_width and c.height >= pdm.enclosure_height)
        version = 'fixture-resize-version'
        choices = EngineeringChoices(components={version: dict(code=row.id, category='ENCLOSURE',
            component_version_id=version, specification=row.model_dump(), **row.model_dump(exclude={'id'}))})
        target = dict(enclosure_id=pdm.enclosure_id)
        parameters = dict(catalog_id=row.id, component_version_id=version, width=row.width, height=row.height, depth=row.depth)
    elif kind == 'RemoveComponent':
        target, parameters = dict(cem_component_id=part.cem_component_id), {}
    elif kind == 'AddComponent':
        part = max((c for c in pdm.components if c.category == 'TERMINAL'), key=lambda c: c.position.x + c.width)
        row = next(c for c in cem.components if c.id == part.cem_component_id).model_dump(mode='json')
        row['code'] = row['catalog_id']
        row['component_version_id'] = 'fixture-add-version'
        choices = EngineeringChoices(components={row['component_version_id']: row})
        position = part.position.model_dump()
        position['x'] += part.width + pdm.validation_policy.din_clearance_mm + 1
        target = dict(panel_id=base.document.panel_id)
        parameters = dict(catalog_id=row['code'], component_version_id=row['component_version_id'],
            product_version_id=None, terminal_intent='UNCONNECTED', terminal_ids=[t['id'] for t in row['terminals']],
            placement=dict(position_mm=position, zone_name=part.zone_name, rail_id=part.rail_id))
    elif kind in ('MoveSymbol', 'UpdateSchematicLabel'):
        symbol = next(s for s in page.symbols if s.component_id == part.cem_component_id)
        if kind == 'MoveSymbol':
            target = dict(symbol_id=symbol.id)
            parameters = dict(position_mm=dict(x=symbol.position.x + 1, y=symbol.position.y))
        else:
            target, parameters = dict(kind='symbol', id=symbol.id), dict(label='Reviewed DB label')
    elif kind == 'UpdateJunctionPresentation':
        counts = Counter(pin for wire in page.wires for pin in (wire.source_pin_id, wire.target_pin_id))
        pin = next(pin for pin, count in counts.items() if count >= 2)
        # Legacy generation uses one net per conductor. Build a synthetic shared
        # net for two conductors already meeting at the same actual terminal.
        # This is explicit test evidence, not an inferred electrical migration.
        members = {w.conductor_id for w in page.wires if pin in (w.source_pin_id, w.target_pin_id)}
        shared_net = next(c.net_id for c in cem.connections if c.id in members and 'SPD' in c.net_id)
        rebound_nets = {c.net_id: shared_net for c in cem.connections if c.id in members}
        for connection in cem.connections:
            if connection.id in members:
                connection.net_id = shared_net
        for edge in cem.electrical_graph.edges:
            edge.properties['net_ids'] = sorted({rebound_nets.get(key, key)
                for key in edge.properties.get('net_ids', [])})
        for net in cem.nets:
            net.connections = [c.model_copy(deep=True) for c in cem.connections if c.net_id == net.id]
        cem.nets = [n for n in cem.nets if n.connections]
        cem.connections = [c.model_copy(deep=True) for n in cem.nets for c in n.connections]
        for route in pdm.routes:
            if route.conductor_id in members:
                route.net_id = shared_net
        rehash(base)
        base.document.generation_intent = GenerationIntent(manual_models=['cem', 'pdm', 'schematic'])
        base = IncrementalScheduler().run(base, inputs, force_full=True).candidate
        cem, pdm, page = base.snapshots.cem, base.snapshots.pdm, base.snapshots.schematic
        nets = {c.id: c.net_id for c in cem.connections}
        pin = next(pin for pin, count in counts.items() if count >= 2 and len({nets[w.conductor_id]
            for w in page.wires if pin in (w.source_pin_id, w.target_pin_id)}) == 1)
        target, parameters = dict(pin_id=pin), dict(visible=False, label='Reviewed shared terminal')
    elif kind == 'ModifyElectricalConnection':
        # The baseline's virtual PE stud deliberately cannot authorize topology
        # edits. Supply a synthetic real SPD PE endpoint and explicit domains for
        # all participating terminals; the checker never infers them from labels.
        connection = next(c for c in cem.connections if c.wire_class == 'PE')
        assert connection.from_component == 'PANEL_ROOT'
        spd = next(c for c in cem.components if c.category == 'SPD')
        connection.from_component, connection.from_terminal = spd.id, 'PE'
        next(n for n in cem.nets if n.id == connection.net_id).connections = [connection.model_copy(deep=True)]
        source_pin = next(p for s in page.symbols if s.component_id == spd.id for p in s.pins if p.terminal_id == 'PE')
        wire = next(w for w in page.wires if w.conductor_id == connection.id)
        wire.source_pin_id, wire.waypoints[0] = source_pin.id, source_pin.position.model_copy(deep=True)
        route = next(r for r in pdm.routes if r.conductor_id == connection.id)
        route.from_component, route.from_terminal = spd.id, 'PE'
        domains = {}
        for conductor in cem.connections:
            phase = re.search(r'-L([123])(?:-|$)', conductor.net_id)
            role = ('PE' if conductor.wire_class == 'PE' else 'N' if conductor.wire_class == 'NEUTRAL'
                    else 'L' + phase[1])
            for endpoint in ((conductor.from_component, conductor.from_terminal),
                             (conductor.to_component, conductor.to_terminal)):
                assert domains.setdefault(endpoint, role) == role
        base.document.configuration['electrical_topology'] = dict(domains=[
            dict(component_id=component, terminal_id=terminal, supply_id='synthetic-DB-supply', role=role)
            for (component, terminal), role in sorted(domains.items())])
        rehash(base)
        target = dict(connection_id=connection.id)
        conductor = connection.model_dump(exclude={'id'})
        conductor.update(conductor_material='COPPER', cross_section_mm2=2.5, insulation_diameter_mm=4.0,
                         insulation_type='PVC', minimum_bend_radius_mm=12.0)
        parameters = dict(action='REPLACE', conductor=conductor,
            invalidated_route_ids=[r.id for r in pdm.routes if r.conductor_id == connection.id])
    elif kind == 'RegenerateSchematic':
        request = operation(base, kind, dict(schematic_id=page.id), dict(replace_manual_positions=True),
                            proposal_status='PROPOSED')
        request.operations[0].origin.proposal_id = 'reviewed-schematic-proposal'
        return base, preview_operations(base, request).candidate, inputs
    else:
        from app.services.generation_proposals import digest
        generated = deepcopy(base)
        generated.snapshots.schematic.symbols[0].label = 'Reviewed generation'
        generated.document.generation_intent = GenerationIntent(manual_models=['schematic'])
        rehash(generated)
        request = operation(base, kind, dict(panel_id=base.document.panel_id),
            dict(overrides={}, candidate_sha256=digest(generated)), proposal_status='PROPOSED')
        request.operations[0].origin.kind = 'AUTOMATIC'
        request.operations[0].origin.proposal_id = 'reviewed-generation'
        return base, preview_operations(base, request,
            EngineeringChoices(generation=generated, recompute=True)).candidate, inputs
    request = operation(base, kind, target, parameters)
    if kind == 'RemoveComponent':
        preview = preview_operations(base, request, choices)
        request.operations[0].parameters.confirmed_cascade = preview.consequences[str(request.operations[0].operation_id)]
    return base, preview_operations(base, request, choices).candidate, inputs


def run_counted(base, inputs, **kwargs):
    calls = []
    def execute(name, value, signature):
        calls.append(name)
        return ADAPTERS[name].execute(value)
    scheduler = IncrementalScheduler(execute_adapter=execute)
    try:
        return scheduler.run(base, inputs, **kwargs), None, scheduler.records, calls
    except DesignError as error:
        return None, error.code, scheduler.records, calls


def assert_accounting(records, calls):
    assert Counter(calls) == Counter(r.adapter for r in records if r.executions)
    assert all(r.executions == (0 if r.status in ('CACHED', 'RETAINED') else 1) for r in records)


def test_matrix_covers_every_registered_operation():
    assert set(OPERATION_STAGES) == set(REGISTRY)
    assert tuple(STAGE_REGISTRY.ordered_ids()) == ALL


@pytest.mark.parametrize('kind', OPERATION_STAGES)
def test_every_operation_matches_full_pass_or_explicit_reconciliation_conflict(board, kind):
    fixture_before = board[0].model_dump(mode='json')
    _, changed, inputs = changed_board(board, kind)
    before = changed.model_dump(mode='json')
    assert tuple(changed.document.dirty_stages) == OPERATION_STAGES[kind]
    incremental, error, records, calls = run_counted(changed, inputs)
    full, full_error, full_records, full_calls = run_counted(changed, inputs, force_full=True)
    assert_accounting(records, calls)
    assert_accounting(full_records, full_calls)
    assert error == full_error
    # These bounded drafts require reconciliation, or cannot meet the supplied
    # conductor's bend limit. Neither pass may discard intent to make them work.
    expected_errors = {'AddComponent': 'STAGE_COMPONENT_MISMATCH',
                       'RemoveComponent': 'INVALID_NETLIST', 'ResizeEnclosure': 'STAGE_LOCK_CONFLICT',
                       'ModifyElectricalConnection': 'ROUTING_INFEASIBLE'}
    assert error == expected_errors.get(kind)
    assert changed.model_dump(mode='json') == before
    assert board[0].model_dump(mode='json') == fixture_before
    if error:
        assert records[-1].status == full_records[-1].status == 'FAILED'
        assert records[-1].adapter == full_records[-1].adapter
        assert 'cad' not in calls and 'cad' not in full_calls
        return
    assert incremental.candidate.snapshots == full.candidate.snapshots
    assert incremental.candidate.document.pins == full.candidate.document.pins
    # Materialize retained projections explicitly. An unscheduled output is not
    # evidence of equivalence until it is compared to the full derived output.
    from app.services.stages import artifacts as a, physical as p
    context = inputs.requirements.context
    common = dict(context=context, cem=e.Snapshot[CanonicalEngineeringModel].capture(incremental.candidate.snapshots.cem),
                  pdm=p.PhysicalSnapshot.capture(incremental.candidate.snapshots.pdm))
    bom = incremental.bom if incremental.bom is not None else a.bom_stage(a.BOMInput(**common)).bom.read()
    cad = incremental.cad if incremental.cad is not None else a.cad_stage(a.CADInput(**common,
        schematic=e.Snapshot[dict].capture(incremental.candidate.snapshots.schematic.model_dump(mode='json')),
        generator_version=changed.document.pins.generator.version,
        model_versions=e.Snapshot[dict[str, str]].capture(changed.document.pins.model_versions))).cad.read()
    assert bom == full.bom and cad == full.cad
    assert tuple(dict.fromkeys(r.stage_id for r in records)) == OPERATION_STAGES[kind]
    expected_calls = [s for s in OPERATION_STAGES[kind] if s != 'schematic'
                      or 'schematic' not in changed.document.generation_intent.manual_models]
    if 'placement' in expected_calls:
        index = expected_calls.index('placement')
        expected_calls[index:index+1] = ['enclosure', 'zoning', 'placement', 'ducts']
    assert calls == expected_calls


@pytest.mark.parametrize('path', ['display.camera', 'pins.generator.version', 'pins.model_versions.device',
    'pdm.validation_policy.thermal_density_limit_w_per_l', 'configuration.future_setting'])
def test_metadata_policy_and_conservative_changes_match_full_pass(board, path):
    base, inputs, _ = deepcopy(board)
    base.document.generation_intent = GenerationIntent(manual_models=['cem', 'pdm', 'schematic'])
    if path.startswith('pdm.'):
        base.snapshots.pdm.validation_policy.thermal_density_limit_w_per_l += .01
    elif path == 'pins.generator.version':
        base.document.pins.generator.version = 'next-generator'
    elif path == 'pins.model_versions.device':
        base.document.pins.model_versions['fixture-device'] = 'next-model'
    elif path.startswith('configuration.'):
        base.document.configuration['future_setting'] = 'conservative-change'
    rehash(base)
    base.document.dirty_stages = list(STAGE_REGISTRY.invalidate([path]).stages)
    incremental, error, records, calls = run_counted(base, inputs)
    full, full_error, _, _ = run_counted(base, inputs, force_full=True)
    assert error == full_error is None
    assert incremental.candidate.snapshots == full.candidate.snapshots
    if incremental.cad is not None:
        assert incremental.cad == full.cad
    assert_accounting(records, calls)
    if path == 'display.camera':
        assert calls == []


@pytest.mark.parametrize('case', CASES['feasible'], ids=lambda case: case['id'])
def test_automatic_full_and_incremental_match_independent_generator(case):
    base, inputs, _ = material(case)
    answers = inputs.requirements.answers.read()
    answers['spare_capacity_pct'] += 1
    inputs = replace(inputs, requirements=inputs.requirements.model_copy(update={'answers': e.Snapshot[dict].capture(answers)}))
    next(r for r in base.snapshots.requirements.items if r.id == 'spare_capacity_pct').value = answers['spare_capacity_pct']
    rehash(base)
    base.document.dirty_stages = list(ALL)
    result, error, records, calls = run_counted(base, inputs)
    oracle = engine(case).generate_design(case['project_id'], {'spare_capacity_pct': answers['spare_capacity_pct']},
                                        persist_requirements=False)
    assert error is None
    assert result.candidate.snapshots.cem.model_dump() == oracle['cem']
    assert result.candidate.snapshots.pdm.model_dump() == oracle['pdm']
    assert result.cad == oracle['cad'] and result.bom == oracle['bom']
    assert_accounting(records, calls)


def test_stricter_saved_policy_same_version_rejects_previous_pass(board):
    base, inputs, _ = deepcopy(board)
    saved_version = base.snapshots.pdm.validation_policy.version
    assert base.snapshots.pdm.validation_results == []
    base.snapshots.pdm.validation_policy.thermal_density_limit_w_per_l = .000001
    base.document.generation_intent = GenerationIntent(manual_models=['cem', 'pdm', 'schematic'])
    base.document.dirty_stages = list(PHYSICAL)
    rehash(base)
    before = base.model_dump(mode='json')
    incremental, error, records, calls = run_counted(base, inputs)
    full, full_error, full_records, full_calls = run_counted(base, inputs, force_full=True)
    assert incremental is full is None
    assert error == full_error == 'PHYSICAL_VALIDATION_FAILED'
    assert_accounting(records, calls)
    assert_accounting(full_records, full_calls)
    assert base.snapshots.pdm.validation_policy.version == saved_version
    assert base.model_dump(mode='json') == before
    assert 'cad' not in calls and 'cad' not in full_calls


@pytest.mark.parametrize('damage', ['payload', 'digest', 'schema', 'policy'])
def test_scheduler_reexecutes_corrupt_cache_without_publishing(api, postgres_database, damage):
    from app.services.document_service import DocumentService
    from app.services.project_service import ProjectService
    from app.services.recompute import materialize
    from tests.test_design_document_storage import row_images
    from tests.test_postgres import create
    db = postgres_database
    api.app.state.cad_executor.shutdown()
    key = create(api)['id']
    source = DocumentService(db).load(key)
    base, inputs = materialize(ProjectService(db), source)
    cache = StageCache(db)
    preserved = row_images(db.engine, {'projects', 'design_documents', 'design_document_snapshots',
        'project_revisions', 'revision_output_snapshots', 'generated_artifacts'})
    first = IncrementalScheduler(cache=cache).run(base, inputs, force_full=True)
    with db.sessions() as session:
        row = dict(session.execute(select(m.stage_results).where(
            m.stage_results.c.stage_id == 'routes',
            m.stage_results.c.input_signature == next(r.input_signature for r in first.records if r.adapter == 'routes')
        )).mappings().one())
    if damage == 'payload':
        changes = dict(result={'invalid': 'typed-output'})
    elif damage == 'digest':
        changes = dict(result_sha256='0' * 64)
    else:
        manifest = deepcopy(row['signature'])
        manifest['output_schema' if damage == 'schema' else 'policy_sha256'] = '0' * 64
        changes = dict(signature=manifest)
    with privileged_connection(db) as connection:
        connection.execute(update(m.stage_results).where(m.stage_results.c.id == row['id']).values(**changes))
    calls = []
    def execute(name, value, signature):
        calls.append(name)
        return ADAPTERS[name].execute(value)
    second = IncrementalScheduler(cache=cache, execute_adapter=execute).run(base, inputs, force_full=True)
    assert calls == ['routes']
    assert second.candidate == first.candidate and second.cad == first.cad and second.bom == first.bom
    assert_accounting(second.records, calls)
    assert all(r.status == ('EXECUTED' if r.adapter == 'routes' else 'CACHED') for r in second.records)
    with db.sessions() as session:
        retained = dict(session.execute(select(m.stage_results).where(m.stage_results.c.id == row['id'])).mappings().one())
        assert all(retained[name] == value for name, value in changes.items())
    assert row_images(db.engine, preserved.keys()) == preserved
    assert DocumentService(db).load(key) == source
