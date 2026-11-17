"""Pure registry/invalidation contracts and integration with document operations."""
import json
from pathlib import Path
import re
from typing import get_args

import pytest
from pydantic import ValidationError

from app.models.document import DirtyStage
from app.models.cem import CanonicalEngineeringModel
from app.models.operations import OperationPreviewRequest
from app.models.pdm import PhysicalDesignModel
from app.models.requirements import RequirementSet
from app.models.schematic import SchematicPresentation
from app.services.change_propagation import ChangePropagationEngine
from app.services.operations.registry import REGISTRY, preview_operations
from app.services.stages.contracts import STAGE_REGISTRY, StageRegistry, paths_overlap
from tests.test_document_contract import document_fixture
from tests.test_operations import request_for
from tests.test_schematic_operations import schematic_command


ALL = STAGE_REGISTRY.ordered_ids()
ELECTRICAL = ('calculations', 'selection', 'connectivity')
PHYSICAL = ('placement', 'routes', 'physical_validation', 'bom', 'cad')


def registry_payload():
    return STAGE_REGISTRY.model_dump(mode='json')


@pytest.mark.parametrize('failure', ['cycle', 'self_cycle', 'disconnected_cycle', 'undefined',
    'unknown_id', 'duplicate', 'input_reference', 'input_output', 'input_paths',
    'unknown_field', 'unpaired_input'])
def test_registry_rejects_invalid_graphs_and_references(failure):
    data = registry_payload()
    stages = data['stages']
    if failure == 'cycle':
        stages[0]['prerequisites'] = ['cad']
    elif failure == 'self_cycle':
        stages[0]['prerequisites'] = ['requirements']
    elif failure == 'disconnected_cycle':
        stages = [s for s in stages if s['id'] in ('requirements', 'calculations')]
        stages[0]['prerequisites'] = ['calculations']
        data['stages'] = stages
    elif failure == 'undefined':
        data['stages'] = [s for s in stages if s['id'] != 'selection']
    elif failure == 'unknown_id':
        stages[0]['prerequisites'] = ['imaginary_stage']
    elif failure == 'duplicate':
        stages.append(stages[0])
    elif failure == 'input_reference':
        stages[1]['inputs'][0]['source_stage'] = 'cad'
    elif failure == 'input_output':
        stages[1]['inputs'][0]['source_output'] = 'missing_output'
    elif failure == 'input_paths':
        stages[1]['inputs'][0]['paths'] = ['pdm.components']
    elif failure == 'unknown_field':
        stages[0]['inputs'][0]['paths'] = ['pdm.components.*.unregistered_geometry']
    else:
        stages[1]['inputs'][0]['source_output'] = None
    with pytest.raises(ValidationError):
        StageRegistry.model_validate(data)


def test_registry_is_immutable_serializable_topological_and_schema_compatible():
    restored = StageRegistry.model_validate_json(STAGE_REGISTRY.model_dump_json())
    assert restored == STAGE_REGISTRY
    assert set(ALL) == set(get_args(DirtyStage))
    ts = (Path(__file__).resolve().parents[2] / 'frontend/src/types/document.ts').read_text()
    literal = ts.split('export type DirtyStage =', 1)[1].split(';', 1)[0]
    assert set(re.findall(r"'([^']+)'", literal)) == set(ALL)
    for contract in restored.stages:
        assert contract.inputs and contract.outputs and contract.validation_obligations
        assert contract.algorithm_version
        assert all(ALL.index(p) < ALL.index(contract.id) for p in contract.prerequisites)
    assert StageRegistry.model_json_schema()['additionalProperties'] is False
    with pytest.raises(ValidationError):
        restored.stages[0].algorithm_version = 'changed'
    with pytest.raises(TypeError):
        restored.by_id['new'] = restored.stages[0]
    # Registration order is only a tie breaker; dependencies always precede consumers.
    reversed_registry = StageRegistry(stages=tuple(reversed(restored.stages)))
    order = reversed_registry.ordered_ids()
    assert all(order.index(p) < order.index(s.id) for s in restored.stages for p in s.prerequisites)


def test_registered_snapshot_fields_exist_in_current_models():
    models = {'requirements': RequirementSet, 'cem': CanonicalEngineeringModel,
              'pdm': PhysicalDesignModel, 'schematic': SchematicPresentation}
    for contract in STAGE_REGISTRY.stages:
        for item in (*contract.inputs, *contract.outputs):
            for path in item.paths:
                parts = path.split('.')
                if parts[0] in models and len(parts) > 1:
                    assert parts[1] in models[parts[0]].model_fields, path


@pytest.mark.parametrize('paths,expected', [
    (['pdm.components.*.position', 'pdm.components.*.terminals'], ('routes', 'physical_validation', 'cad')),
    (['pdm.components.0.rotation_deg'], ('routes', 'physical_validation', 'cad')),
    (['pdm.components.*.position.x'], ('routes', 'physical_validation', 'cad')),
    (['cem.components.*.current_rating'], ALL[1:]),
    (['cem.connections'], ('connectivity', 'schematic', *PHYSICAL)),
    (['schematic.symbols.*.position'], ('schematic', 'cad')),
    (['display.camera.position', 'display.selection', 'display.visibility'], ()),
    (['pdm.enclosure_width'], PHYSICAL),
    (['configuration.enclosure_id', 'configuration.enclosure_parameters.width_mm'], PHYSICAL),
    (['pins.catalog_versions.components'], ALL[2:]),
    (['pins.catalog_versions.enclosures'], PHYSICAL),
    (['pins.catalog_versions.hardware'], PHYSICAL),
    (['pins.catalog_versions.archetype'], ALL),
    (['pins.catalog_versions.rules'], ALL),
    (['pins.model_versions.component_1'], ('cad',)),
    (['pins.generator.version'], ('cad',)),
    (['pins.engine_version'], ALL),
    (['pins.catalog_manifest_sha256'], ALL),
    (['pdm.validation_policy.wire_clearance_mm'], PHYSICAL),
    (['algorithms.routes'], ('routes', 'physical_validation', 'cad')),
    (['pdm.enclosure_width', 'cem.components.*.current_rating'], ALL[1:]),
    ([], ()),
])
def test_change_matrix(paths, expected):
    plan = STAGE_REGISTRY.invalidate(paths)
    assert plan.stages == expected
    assert plan == STAGE_REGISTRY.invalidate(reversed(paths))
    assert set(plan.direct_stages) <= set(plan.stages)
    assert set(plan.validation_obligations) == {code for stage_id in expected
        for code in STAGE_REGISTRY.by_id[stage_id].validation_obligations}


@pytest.mark.parametrize('path,root,expected', [
    ('pdm.future_geometry', 'pdm', PHYSICAL),
    ('pdm.components.*.future_geometry', 'pdm', PHYSICAL),
    ('cem.future_electrical_field', 'cem', ALL[1:]),
    ('cem.components.*.future_rating', 'cem', ALL[1:]),
    ('schematic.future_presentation', 'schematic', ('schematic', 'cad')),
    ('schematic.symbols.*.future_presentation', 'schematic', ('schematic', 'cad')),
    ('requirements.future_answer', 'requirements', ALL),
    ('pins.catalog_versions.future_catalog', 'pins', ALL),
    ('configuration.future_setting', 'configuration', ALL),
    ('display.future_view_or_engineering_field', 'display', ALL),
    ('unknown.future_change', 'unknown', ALL),
    ('', '', ALL),
])
def test_unknown_changes_invalidate_conservative_model_closures(path, root, expected):
    plan = STAGE_REGISTRY.invalidate([path])
    assert plan.stages == expected
    assert plan.conservative_roots == (root,)


def test_invalidation_has_no_reverse_prerequisite_expansion():
    assert STAGE_REGISTRY.downstream(['routes']) == ('routes', 'physical_validation', 'cad')
    assert STAGE_REGISTRY.downstream(['cad']) == ('cad',)
    with pytest.raises(ValueError, match='Undefined stage'):
        STAGE_REGISTRY.downstream(['NETLIST'])
    with pytest.raises(TypeError):
        STAGE_REGISTRY.invalidate('display.camera')
    with pytest.raises(TypeError):
        STAGE_REGISTRY.downstream('routes')
    assert paths_overlap('pdm.components', 'pdm.components.*.position.x')
    assert paths_overlap('pdm.components.0.position', 'pdm.components.*.position')
    assert not paths_overlap('pdm.component', 'pdm.components')


def test_legacy_change_reporting_uses_registered_ids_and_keeps_diff_values():
    engine = ChangePropagationEngine()
    assert engine.identify_dirty_nodes('incomer_rating') == set(ALL)
    assert engine.identify_dirty_nodes('future_requirement') == set(ALL)
    assert engine.identify_dirty_nodes('pdm.components.*.position') == {'routes', 'physical_validation', 'cad'}
    report = engine.compute_diff({}, {}, {}, {}, 'num_feeders', {'num_feeders': 1}, {'num_feeders': 2})
    assert report['affected_stages'] == list(ALL)
    assert (report['diffs'][0]['before'], report['diffs'][0]['after']) == ('1', '2')
    assert engine.compute_diff({}, {}, {}, {})['affected_stages'] == []


def test_operation_registry_has_no_undefined_or_conservative_known_declarations():
    for definition in REGISTRY.values():
        plan = STAGE_REGISTRY.invalidate(definition.changed_paths)
        assert not plan.conservative_roots
        assert definition.dirty_stages == plan.stages
        assert set(definition.checks) <= set(plan.validation_obligations)
    assert not set(REGISTRY['MoveComponent'].dirty_stages).intersection(ELECTRICAL)
    assert 'connectivity' not in REGISTRY['MoveSymbol'].dirty_stages


def test_real_previews_use_registry_preserve_identity_and_only_mark_dirty():
    base = document_fixture()
    base.document.dirty_stages = []
    before = base.model_dump(mode='json')
    move = preview_operations(base, OperationPreviewRequest.model_validate(request_for(base)))
    assert move.dirty_stages == ['routes', 'physical_validation', 'cad']
    assert move.candidate.snapshots.cem == base.snapshots.cem
    assert move.candidate.snapshots.pdm.routes == base.snapshots.pdm.routes
    assert move.candidate.document.pins == base.document.pins
    symbol = schematic_command(base, 'MoveSymbol', {'symbol_id': 'symbol-1'},
        {'position_mm': {'x': 220, 'y': 160}})
    presentation = preview_operations(base, symbol)
    assert presentation.dirty_stages == ['schematic', 'cad']
    assert presentation.candidate.snapshots.cem == base.snapshots.cem
    assert presentation.candidate.snapshots.pdm == base.snapshots.pdm
    assert base.model_dump(mode='json') == before
    # Existing shared wire fixtures remain accepted without a version bump.
    fixture = Path(__file__).resolve().parents[2] / 'frontend/src/types/fixtures/operation-preview-v1.json'
    assert OperationPreviewRequest.model_validate(json.loads(fixture.read_text())).schema_version == '1.0.0'
