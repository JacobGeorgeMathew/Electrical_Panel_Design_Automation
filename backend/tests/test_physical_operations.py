"""Server-owned placement constraints, bounded rotation and durable dirty drafts."""
from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.models.document import ResolvedDocument, SnapshotReference, snapshot_sha256
from app.models.document_api import DocumentSave
from app.models.operations import OperationPreviewRequest
from app.persistence import models as m
from app.persistence.operations import OperationBatchRepository, _prepare
from app.services.design_errors import DesignError
from app.services.document_service import DocumentService
from app.services.operations.registry import preview_operations
from tests.test_document_contract import document_fixture
from tests.test_operation_persistence import history, load, persisted_base
from tests.test_operations import request_for


def rehash(base):
    for kind in ('requirements', 'cem', 'pdm', 'schematic'):
        setattr(base.document.models, kind, SnapshotReference(
            sha256=snapshot_sha256(getattr(base.snapshots, kind))))
    return ResolvedDocument.model_validate(base.model_dump(mode='json'))


def physical_request(base, position=None, rotation=None):
    body = request_for(base)
    body['batch_id'] = str(uuid4())
    op = body['operations'][0]
    op['operation_id'] = str(uuid4())
    if rotation is not None:
        op.update(type='RotateComponent', parameters=dict(rotation_deg=rotation))
    elif position is not None:
        op['parameters']['position_mm'] = position
    return OperationPreviewRequest.model_validate(body)


def with_neighbor():
    base = document_fixture()
    cem = base.snapshots.cem.components[0].model_copy(deep=True)
    cem.id = 'QF002'
    base.snapshots.cem.components.append(cem)
    component = base.snapshots.pdm.components[0].model_copy(deep=True)
    component.id, component.cem_component_id = 'PDM-QF002', 'QF002'
    component.position.x = 180
    component.terminals[0]['x'] = 189
    base.snapshots.pdm.components.append(component)
    return rehash(base)


def forbid_computation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Physical Apply/Save must not compute routes, optimize or publish.')

    from app.algorithms.cp_sat_placement import CPSATPlacementOptimizer
    from app.algorithms.duct_routing import DuctRouter
    from app.services.cad_engine import CADEngine
    from app.services import physical_routing
    from app.persistence import revisions
    monkeypatch.setattr(CPSATPlacementOptimizer, 'solve', forbidden)
    monkeypatch.setattr(DuctRouter, 'route_layout', forbidden)
    monkeypatch.setattr(physical_routing, 'reroute_placement', forbidden)
    monkeypatch.setattr(CADEngine, 'generate_parametric_geometry', forbidden)
    monkeypatch.setattr(revisions, 'write_revision', forbidden)


def test_move_preserves_identity_and_server_geometry_without_computation(monkeypatch):
    forbid_computation(monkeypatch)
    base = document_fixture()
    base.document.dirty_stages = []
    before = deepcopy(base)
    request = physical_request(base, dict(x=140.125, y=210.5, z=45.25))
    prepared = _prepare(base, request)
    candidate = prepared.after
    old, moved = before.snapshots.pdm.components[0], candidate.snapshots.pdm.components[0]
    assert base == before
    assert moved.position.model_dump() == dict(x=140.125, y=210.5, z=45.25)
    assert moved.terminals == old.terminals
    assert moved.model_dump(exclude={'position', 'terminals'}) == old.model_dump(exclude={'position', 'terminals'})
    assert candidate.snapshots.cem == before.snapshots.cem
    assert candidate.snapshots.schematic == before.snapshots.schematic
    assert candidate.snapshots.requirements == before.snapshots.requirements
    assert candidate.document.pins == before.document.pins
    assert candidate.snapshots.pdm.model_dump(exclude={'components'}) == before.snapshots.pdm.model_dump(exclude={'components'})
    assert candidate.document.dirty_stages == ['routes', 'physical_validation', 'cad']
    assert {check['code'] for check in prepared.required_checks} == {'physical_constraints', 'routing', 'physical_validation'}
    assert all(check['status'] == 'UNRESOLVED' for check in prepared.required_checks)
    assert candidate.document.models.pdm.sha256 == snapshot_sha256(candidate.snapshots.pdm)


@pytest.mark.parametrize('position', [dict(x=25, y=30, z=20), dict(x=557, y=690, z=175)])
def test_exact_backplate_and_cavity_boundaries(position):
    result = preview_operations(document_fixture(), physical_request(document_fixture(), position))
    assert result.candidate.snapshots.pdm.components[0].position.model_dump() == position


@pytest.mark.parametrize('position', [dict(x=24.99, y=200, z=37.5), dict(x=557.01, y=200, z=37.5),
    dict(x=140, y=29.99, z=37.5), dict(x=140, y=690.01, z=37.5),
    dict(x=140, y=200, z=19.99), dict(x=140, y=200, z=175.01),
    dict(x=140, y=310, z=37.5)])
def test_boundary_depth_and_duct_collision_rejected_atomically(position):
    base = document_fixture()
    before = deepcopy(base)
    with pytest.raises(DesignError) as error:
        _prepare(base, physical_request(base, position))
    assert error.value.code == 'OPERATION_PHYSICAL_CONSTRAINT'
    assert {v['type'] for v in error.value.details['violations']} & {'BOUNDARY', 'DUCT_COLLISION'}
    assert base == before


def test_explicit_plate_dimensions_and_saved_clearance_policy():
    base = document_fixture()
    base.snapshots.pdm.mounting_plate_width = 300
    base.snapshots.pdm.mounting_plate_height = 400
    base.snapshots.pdm.ducts[0].width = 275
    base = rehash(base)
    preview_operations(base, physical_request(base, dict(x=307, y=350, z=37.5)))
    with pytest.raises(DesignError):
        preview_operations(base, physical_request(base, dict(x=307.01, y=350, z=37.5)))
    with pytest.raises(DesignError):
        preview_operations(base, physical_request(base, dict(x=307, y=350.01, z=37.5)))
    for rail, gap in [('rail-1', 10), (None, 20)]:
        base = with_neighbor()
        base.snapshots.pdm.components[1].rail_id = rail
        base.snapshots.pdm.validation_policy.din_clearance_mm = 10
        base = rehash(base)
        x = 180 - 18 - gap
        preview_operations(base, physical_request(base, dict(x=x, y=200.25, z=37.5)))
        with pytest.raises(DesignError) as error:
            preview_operations(base, physical_request(base, dict(x=x + .01, y=200.25, z=37.5)))
        assert 'CLEARANCE' in {v['type'] for v in error.value.details['violations']}


def test_overlap_and_thermal_cannot_be_accepted():
    base = with_neighbor()
    with pytest.raises(DesignError) as error:
        _prepare(base, physical_request(base, dict(x=170, y=200.25, z=37.5)))
    assert 'OVERLAP' in {v['type'] for v in error.value.details['violations']}
    base = document_fixture()
    base.snapshots.pdm.total_heat_loss_watts = 100
    base = rehash(base)
    with pytest.raises(DesignError) as error:
        _prepare(base, physical_request(base))
    assert 'THERMAL' in {v['type'] for v in error.value.details['violations']}


def test_stale_plate_extents_cannot_allow_move_outside_enclosure():
    base = document_fixture()
    base.snapshots.pdm.mounting_plate_width = 1000
    base = rehash(base)
    with pytest.raises(DesignError) as error:
        _prepare(base, physical_request(base, dict(x=600, y=200.25, z=37.5)))
    assert 'BOUNDARY' in {v['type'] for v in error.value.details['violations']}


@pytest.mark.parametrize('field,value', [('width', 0), ('height', -1), ('depth', 0)])
def test_nonpositive_saved_dimensions_are_rejected(field, value):
    base = document_fixture()
    setattr(base.snapshots.pdm.components[0], field, value)
    base = rehash(base)
    with pytest.raises(DesignError) as error:
        _prepare(base, physical_request(base))
    assert error.value.code == 'OPERATION_GEOMETRY'


def test_invalid_noop_does_not_claim_success():
    base = document_fixture()
    base.snapshots.pdm.components[0].position.x = 0
    base = rehash(base)
    for request in [physical_request(base, dict(x=0, y=200.25, z=37.5)),
                    physical_request(base, rotation=0)]:
        with pytest.raises(DesignError) as error:
            _prepare(base, request)
        assert error.value.code == 'OPERATION_PHYSICAL_CONSTRAINT'


@pytest.mark.parametrize('rotation', [90, -90, 180, 360, -360, 0.000000001])
def test_nonzero_rotations_rejected_without_normalization(rotation):
    base = document_fixture()
    before = deepcopy(base)
    with pytest.raises(DesignError) as error:
        _prepare(base, physical_request(base, rotation=rotation))
    assert error.value.code == 'UNSUPPORTED_ROTATION'
    assert base == before


def test_zero_rotation_is_noop_and_existing_rotations_are_blocked():
    base = document_fixture()
    base.document.dirty_stages = []
    result = preview_operations(base, physical_request(base, rotation=0))
    assert result.candidate == base
    assert result.changes == result.required_checks == result.dirty_stages == []
    assert not _prepare(base, physical_request(base, rotation=0)).changed
    base = with_neighbor()
    base.snapshots.pdm.components[1].rotation_deg = 90
    base = rehash(base)
    for request in [physical_request(base), physical_request(base, rotation=0)]:
        with pytest.raises(DesignError) as error:
            _prepare(base, request)
        assert error.value.code == 'UNSUPPORTED_ROTATION'


@pytest.mark.parametrize('rotation', [True, '90', float('nan'), float('inf')])
def test_rotation_requires_finite_numeric_degrees(rotation):
    with pytest.raises(ValidationError):
        physical_request(document_fixture(), rotation=rotation)


@pytest.mark.parametrize('field', ['width', 'validation_policy', 'rotation_deg'])
def test_move_cannot_override_server_geometry_or_policy(field):
    body = request_for(document_fixture())
    body['operations'][0]['parameters'][field] = 0
    with pytest.raises(ValidationError):
        OperationPreviewRequest.model_validate(body)


def test_late_constraint_failure_retains_original_and_terminal_ids():
    base = document_fixture()
    before = deepcopy(base)
    first = physical_request(base)
    result = preview_operations(base, first)
    second = physical_request(result.candidate, dict(x=-1, y=200.25, z=37.5)).operations[0]
    request = first.model_copy(update={'operations': [first.operations[0], second]})
    with pytest.raises(DesignError):
        _prepare(base, request)
    assert base == before


@pytest.mark.parametrize('value', [None, '120', True])
def test_invalid_terminal_geometry_is_not_translated(value):
    base = document_fixture()
    base.snapshots.pdm.components[0].terminals[0]['x'] = value
    base = rehash(base)
    with pytest.raises(DesignError) as error:
        preview_operations(base, physical_request(base))
    assert error.value.code == 'OPERATION_GEOMETRY'


def test_physical_commit_rejection_and_save_preserve_revision_and_routes(postgres_database, monkeypatch):
    forbid_computation(monkeypatch)
    key, _ = persisted_base(postgres_database)
    base = load(postgres_database, key)
    repository = OperationBatchRepository(postgres_database)

    def publication_rows():
        with postgres_database.sessions() as session:
            return [list(session.execute(select(table).order_by(*table.primary_key.columns)))
                    for table in (m.project_revisions, m.generated_artifacts)]

    original = publication_rows()
    before_history = history(postgres_database, key)
    request = physical_request(base)
    result = preview_operations(base, request)
    bad = physical_request(result.candidate, dict(x=-1, y=200.25, z=37.5)).operations[0]
    batch = request.model_copy(update={'operations': [request.operations[0], bad]})
    for invalid in [batch, physical_request(base, rotation=90)]:
        with pytest.raises(DesignError):
            repository.commit(key, invalid, 'rejected-' + str(uuid4()))
        assert load(postgres_database, key) == base
        assert history(postgres_database, key) == before_history

    receipt = repository.commit(key, request, 'physical-move')
    assert repository.commit(key, request, 'physical-move') == receipt
    saved = load(postgres_database, key)
    assert saved.snapshots.cem == base.snapshots.cem
    assert saved.snapshots.pdm.components[0].position.x == 140
    assert saved.snapshots.pdm.routes == base.snapshots.pdm.routes
    assert {'routes', 'physical_validation', 'cad'} <= set(saved.document.dirty_stages)
    assert all(check['status'] == 'UNRESOLVED' for check in receipt['required_checks'])
    assert len(history(postgres_database, key)[1]) == 1
    data = DocumentSave(document_id=saved.document.document_id,
        expected_version=saved.document.lock_version,
        expected_document_sequence=saved.document.document_sequence,
        requirements=saved.snapshots.requirements, configuration={'enclosure_id': 'ENC-1'})
    after_save = DocumentService(postgres_database).save(key, data)
    assert after_save.snapshots.pdm == saved.snapshots.pdm
    assert after_save.document.dirty_stages
    assert publication_rows() == original
