"""Independent full-generator oracle and working-intent recomputation matrix."""
from copy import deepcopy

import pytest

from app.models.document import GenerationIntent, SnapshotReference, snapshot_sha256
from app.persistence.assets import content_hash
from app.services.document_service import DocumentService
from app.services.generation_proposals import generated_document
from app.services.stages import electrical as e, physical as p
from app.services.stages.contracts import STAGE_REGISTRY
from app.services.stages.scheduler import IncrementalScheduler, SchedulerInputs, dirty_closure
from tests.design_baseline_support import CASES, engine
from tests.test_electrical_stages import supplied
from tests.test_physical_stages import supplied as physical_supplied


def rehash(base):
    for kind in ('requirements', 'cem', 'pdm', 'schematic'):
        setattr(base.document.models, kind, SnapshotReference(sha256=snapshot_sha256(getattr(base.snapshots, kind))))


def material(case):
    full = engine(case).generate_design(case['project_id'], persist_requirements=False)
    req, catalog = supplied(case)
    physical, hardware = physical_supplied(case, full)
    base = DocumentService.empty_document(dict(id=case['project_id'], lock_version=1),
        dict(archetype_version_id='fixture-db-1'))
    base.document.panel_id = req.context.panel_id
    requirements = e.requirements_stage(req).validated_requirements.read()
    manifest = dict(engine_version=req.context.engine_version, generator=dict(name='panelstudio-primitives', version='3'),
        validation_policy_version=full['pdm']['validation_policy']['version'],
        archetype_version_id=req.rules.archetype_version, rule_set_version_id=req.rules.rules_version,
        cad_model_versions={})
    base = generated_document(base, requirements, full, manifest)
    base.document.pins.catalog_versions.update(components=catalog.catalog_version,
        enclosures=physical.catalog.catalog_version, hardware=hardware.catalog_version)
    base.document.dirty_stages = []
    return base, SchedulerInputs(requirements=req, components=catalog, enclosures=physical.catalog,
                                 hardware=hardware, layout=physical.layout), full


@pytest.fixture(scope='module')
def board():
    return material(CASES['feasible'][0])


@pytest.mark.parametrize('case', CASES['feasible'], ids=lambda c: c['id'])
def test_full_scheduler_matches_independent_oracle(case):
    base, inputs, full = material(case)
    result = IncrementalScheduler().run(base, inputs, force_full=True)
    assert result.candidate.snapshots.cem.model_dump() == full['cem']
    assert result.candidate.snapshots.pdm.model_dump() == full['pdm']
    assert result.cad == full['cad']
    assert result.bom == full['bom']
    assert result.candidate.snapshots.schematic == base.snapshots.schematic
    assert {r.stage_id for r in result.records} == set(STAGE_REGISTRY.ordered_ids())
    assert not result.candidate.document.dirty_stages


@pytest.mark.parametrize('path', [
    'requirements.items.num_feeders.value', 'cem.components.*.current_rating',
    'cem.connections', 'schematic.symbols.*.position', 'pdm.enclosure_width',
    'pdm.components.*.position', 'pdm.validation_policy', 'pins.generator',
    'display.camera',
])
def test_dirty_matrix_matches_full_recompute_with_authoritative_intent(board, path):
    base, inputs, _ = board
    changed = deepcopy(base)
    # Retain accepted electrical, physical and schematic intent while comparing
    # all derived outputs. Requirement changes have separate oracle cases below.
    changed.document.generation_intent = GenerationIntent(manual_models=['cem', 'pdm', 'schematic'])
    if path == 'cem.components.*.current_rating':
        changed.snapshots.cem.components[0].current_rating += 1
    elif path == 'cem.connections':
        connection = changed.snapshots.cem.connections[0]
        connection.cross_section_mm2 = 35
        for net in changed.snapshots.cem.nets:
            for member in net.connections:
                if member.id == connection.id:
                    member.cross_section_mm2 = 35
    elif path == 'schematic.symbols.*.position':
        symbol = changed.snapshots.schematic.symbols[0]
        symbol.position.x += 5
        for pin in symbol.pins:
            pin.position.x += 5
    elif path == 'pdm.components.*.position':
        part = max((c for c in changed.snapshots.pdm.components if c.rail_id), key=lambda c: c.position.x+c.width)
        part.position.x += 1
    elif path == 'pdm.validation_policy':
        changed.snapshots.pdm.validation_policy.thermal_density_limit_w_per_l += .01
    elif path == 'pins.generator':
        changed.document.pins.generator.version = 'fixture-generator-next'
    rehash(changed)
    changed.document.dirty_stages = list(STAGE_REGISTRY.invalidate([path]).stages)
    incremental = IncrementalScheduler().run(changed, inputs)
    oracle = IncrementalScheduler().run(changed, inputs, force_full=True)
    assert incremental.candidate.snapshots == oracle.candidate.snapshots
    if incremental.cad is not None:
        assert incremental.cad == oracle.cad
    if incremental.bom is not None:
        assert incremental.bom == oracle.bom
    assert base.document.dirty_stages == []


def test_real_movement_skips_calculation_and_netlist_and_retains_intent(board, monkeypatch):
    base, inputs, _ = board
    changed = deepcopy(base)
    # Move the rightmost DIN component into the spare rail space.
    parts = [c for c in changed.snapshots.pdm.components if c.rail_id]
    part = max(parts, key=lambda c: c.position.x + c.width)
    part.position.x += 1
    changed.document.generation_intent = GenerationIntent(manual_models=['pdm'], locked_placements=[part.cem_component_id])
    changed.document.dirty_stages = list(STAGE_REGISTRY.invalidate(['pdm.components.*.position']).stages)
    rehash(changed)
    from app.services.calculation_engine import CalculationEngine
    from app.services.netlist_engine import NetlistEngine
    def forbidden(*args, **kwargs):
        raise AssertionError('Unrelated electrical execution')
    monkeypatch.setattr(CalculationEngine, 'calculate_db_parameters', forbidden)
    monkeypatch.setattr(NetlistEngine, 'generate_netlist', forbidden)
    result = IncrementalScheduler().run(changed, inputs)
    assert [r.stage_id for r in result.records] == ['routes', 'physical_validation', 'cad']
    assert result.candidate.snapshots.cem == changed.snapshots.cem
    assert result.candidate.snapshots.pdm.components == changed.snapshots.pdm.components
    assert result.cad
    assert result.candidate.snapshots.pdm.routes != base.snapshots.pdm.routes


def test_clean_document_schedules_nothing(board):
    base, inputs, _ = board
    assert dirty_closure(base) == ()
    result = IncrementalScheduler().run(base, inputs)
    assert result.records == ()
    assert result.candidate == base


def test_requirement_change_matches_full_generation(board):
    from dataclasses import replace
    base, inputs, _ = board
    changed = deepcopy(base)
    for item in changed.snapshots.requirements.items:
        if item.id == 'num_feeders':
            item.value = 16
    changed.document.dirty_stages = list(STAGE_REGISTRY.invalidate(['requirements.items.num_feeders.value']).stages)
    rehash(changed)
    answers = inputs.requirements.answers.read()
    answers['num_feeders'] = 16
    updated = replace(inputs, requirements=inputs.requirements.model_copy(update={'answers': e.Snapshot[dict].capture(answers)}))
    result = IncrementalScheduler().run(changed, updated)
    full = engine(CASES['feasible'][0]).generate_design(base.document.project_id, {'num_feeders': 16}, persist_requirements=False)
    assert result.candidate.snapshots.cem.model_dump() == full['cem']
    assert result.candidate.snapshots.pdm.model_dump() == full['pdm']
    assert result.cad == full['cad']
    assert result.bom == full['bom']
