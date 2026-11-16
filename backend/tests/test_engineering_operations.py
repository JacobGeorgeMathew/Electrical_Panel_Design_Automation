"""Bounded catalog edits, provenance, invalidation and atomic persistence."""
from copy import deepcopy
from uuid import uuid4

import pytest

from app.models.document import SnapshotReference, snapshot_sha256
from app.models.operations import OperationPreviewRequest
from pydantic import ValidationError
from app.persistence.assets import AssetStore
from app.persistence.operations import OperationBatchRepository, _prepare
from app.persistence.repositories import CatalogRepository
from app.services.design_errors import DesignError
from app.services.operations.engineering import EngineeringChoices
from app.services.operations.registry import REGISTRY, preview_operations
from tests.test_document_contract import document_fixture
from tests.test_operations import fixture_choices, request_for
from tests.test_operation_persistence import persisted_base, load, history


def choices_for(base):
    row = base.snapshots.cem.components[0].model_dump()
    row.update(code='MCB-40', current_rating=40, component_version_id='version-40',
               product_version_id=None, width=20, heat_loss=3)
    enclosure = dict(code='ENC-2', category='ENCLOSURE', component_version_id='version-enc',
        name='Larger enclosure', width=800, height=1000, depth=300,
        specification=dict(ip_rating='IP54', mounting_plate_width=750, mounting_plate_height=950,
            mounting_plate_offset_x=25, mounting_plate_offset_y=25, mounting_plate_offset_z=20,
            max_thermal_dissipation=300))
    return EngineeringChoices(fixture_choices(base).questions,
                              {'version-40': row, 'version-enc': enclosure})


def engineering_request(base, kind):
    body = request_for(base)
    op = body['operations'][0]
    op['type'] = kind
    model = 'cem' if kind == 'ChangeComponentRating' else 'pdm'
    op['affected_models'] = [model]
    op['preconditions']['snapshot_sha256'] = getattr(base.document.models, model).sha256
    if kind == 'ChangeComponentRating':
        op['target'] = dict(cem_component_id='QF001')
        op['parameters'] = dict(catalog_id='MCB-40', component_version_id='version-40', current_rating=40)
    else:
        op['target'] = dict(enclosure_id='ENC-1')
        op['parameters'] = dict(catalog_id='ENC-2', component_version_id='version-enc', width=800, height=1000, depth=300)
    return body


@pytest.mark.parametrize('kind', ['ChangeComponentRating', 'ResizeEnclosure'])
def test_only_declared_fields_and_downstream_invalidation(kind):
    base = document_fixture()
    original = deepcopy(base)
    request = OperationPreviewRequest.model_validate(engineering_request(base, kind))
    choices = choices_for(base)
    result = preview_operations(base, request, choices)
    candidate = result.candidate
    assert base == original
    assert preview_operations(base, request, choices) == result
    assert candidate.document.pins == base.document.pins
    assert candidate.snapshots.requirements == base.snapshots.requirements
    assert candidate.snapshots.schematic == base.snapshots.schematic
    assert set(REGISTRY[kind].dirty_stages) <= set(result.dirty_stages)
    if kind == 'ChangeComponentRating':
        assert candidate.snapshots.pdm == base.snapshots.pdm
        edited = candidate.snapshots.cem.components[0]
        assert edited.id == 'QF001' and edited.current_rating == 40
        assert edited.component_version_id == 'version-40'
        copy = candidate.snapshots.cem.model_copy(deep=True)
        copy.components = base.snapshots.cem.components
        assert copy == base.snapshots.cem
    else:
        assert candidate.snapshots.cem == base.snapshots.cem
        assert candidate.snapshots.pdm.enclosure_width == 800
        changed = {'enclosure_id', 'enclosure_width', 'enclosure_height', 'enclosure_depth',
                   'ip_rating', 'mounting_plate_x', 'mounting_plate_y', 'mounting_plate_z'}
        assert candidate.snapshots.pdm.model_dump(exclude=changed) == base.snapshots.pdm.model_dump(exclude=changed)
    prepared = _prepare(base, request, choices)
    assert prepared.after.document.document_sequence == base.document.document_sequence + 1
    assert prepared.after.document.lock_version == base.document.lock_version + 1
    assert all(check['status'] == 'UNRESOLVED' for check in prepared.required_checks)


@pytest.mark.parametrize('kind', ['ChangeComponentRating', 'ResizeEnclosure'])
@pytest.mark.parametrize('failure', ['missing_version', 'wrong_code', 'unsupported_value', 'unknown_target'])
def test_catalog_rejection_preserves_original(kind, failure):
    base = document_fixture()
    before = deepcopy(base)
    body = engineering_request(base, kind)
    op = body['operations'][0]
    if failure == 'missing_version': op['parameters']['component_version_id'] = 'missing'
    elif failure == 'wrong_code': op['parameters']['catalog_id'] = 'other'
    elif failure == 'unsupported_value': op['parameters']['current_rating' if kind == 'ChangeComponentRating' else 'width'] = 999
    else: op['target'][next(iter(op['target']))] = 'missing'
    with pytest.raises(DesignError):
        _prepare(base, OperationPreviewRequest.model_validate(body), choices_for(base))
    assert base == before


@pytest.mark.parametrize('field,value', [('poles', 3), ('category', 'MCCB'), ('breaking_capacity', 1),
                                       ('mounting', 'PLATE'), ('terminals', [])])
def test_incompatible_substitution(field, value):
    base = document_fixture()
    choices = choices_for(base)
    choices.components['version-40'][field] = value
    with pytest.raises(DesignError):
        preview_operations(base, OperationPreviewRequest.model_validate(engineering_request(base, 'ChangeComponentRating')), choices)


def test_requirement_provenance_unknown_key_and_noop():
    base = document_fixture()
    before = deepcopy(base)
    choices = choices_for(base)
    body = request_for(base, 'UpdateRequirement')
    body['operations'][0]['origin'] = dict(kind='AUTOMATIC', actor_id='rules-job')
    request = OperationPreviewRequest.model_validate(body)
    prepared = _prepare(base, request, choices)
    item = prepared.after.snapshots.requirements.items[0]
    assert (item.id, item.label, item.unit) == (before.snapshots.requirements.items[0].id,
        before.snapshots.requirements.items[0].label, before.snapshots.requirements.items[0].unit)
    assert item.source == 'AUTOMATIC' and item.state == 'PROPOSED'
    assert prepared.after.document.provenance.actor_id == 'rules-job'
    assert base == before
    body['operations'][0]['parameters']['value'] = 415
    assert not _prepare(base, OperationPreviewRequest.model_validate(body), choices).changed
    for value in [999, '230', True, None]:
        body['operations'][0]['parameters']['value'] = value
        with pytest.raises(DesignError):
            _prepare(base, OperationPreviewRequest.model_validate(body), choices)
    # An existing but unrecognized saved key is also forbidden.
    with pytest.raises(DesignError):
        _prepare(base, request, EngineeringChoices())
    assert base == before


def test_ordered_engineering_batch_failure_retains_base():
    base = document_fixture()
    before = deepcopy(base)
    body = engineering_request(base, 'ChangeComponentRating')
    second = engineering_request(base, 'ResizeEnclosure')['operations'][0]
    second['operation_id'] = str(uuid4())
    second['parameters']['width'] = 123
    body['operations'].append(second)
    with pytest.raises(DesignError):
        _prepare(base, OperationPreviewRequest.model_validate(body), choices_for(base))
    assert base == before


@pytest.mark.parametrize('kind', ['ChangeComponentRating', 'ResizeEnclosure'])
@pytest.mark.parametrize('value', [0, -1, '40', True, float('nan'), float('inf')])
def test_invalid_catalog_parameter_contract(kind, value):
    body = engineering_request(document_fixture(), kind)
    body['operations'][0]['parameters']['current_rating' if kind == 'ChangeComponentRating' else 'width'] = value
    with pytest.raises(ValidationError):
        OperationPreviewRequest.model_validate(body)


def test_published_choices_commit_and_rejections_are_atomic(postgres_database):
    key, base = persisted_base(postgres_database)
    with postgres_database.sessions() as session:
        catalog = CatalogRepository(session, AssetStore(postgres_database.settings.asset_root))
        source = catalog.get_component('MCB_16A_1P_10KA')
        target = catalog.get_component('MCB_32A_1P_10KA')
        enclosure = catalog.enclosures()[-1]
    component = base.snapshots.cem.components[0]
    # Retain the fixture's connected terminal identity while using the real
    # published terminal topology for this isolated catalog qualification.
    component.terminals = source['terminals']
    terminal = component.terminals[0]['id']
    connection = base.snapshots.cem.connections[0]
    connection.from_terminal = terminal
    base.snapshots.cem.nets[0].connections[0].from_terminal = terminal
    base.snapshots.schematic.symbols[0].pins[0].terminal_id = terminal
    base.snapshots.pdm.components[0].terminals = []
    base.snapshots.pdm.routes[0].from_terminal = terminal
    component.mounting = source['mounting']
    component.breaking_capacity = source['breaking_capacity']
    from app.persistence.documents import DocumentRepository
    from app.models.document_api import DocumentView
    from app.persistence.documents import document_hash
    for model in ('cem', 'pdm', 'schematic'):
        setattr(base.document.models, model, SnapshotReference(sha256=snapshot_sha256(getattr(base.snapshots, model))))
    with postgres_database.sessions.begin() as session:
        DocumentRepository(session).store(DocumentView(**base.model_dump(), content_sha256=document_hash(base.document)))
    base = load(postgres_database, key)
    body = engineering_request(base, 'ChangeComponentRating')
    body['operations'][0]['parameters'] = dict(catalog_id=target['code'],
        component_version_id=target['component_version_id'], current_rating=target['current_rating'])
    second = engineering_request(base, 'ResizeEnclosure')['operations'][0]
    second['operation_id'] = str(uuid4())
    second['parameters'] = dict(catalog_id=enclosure['code'], component_version_id=enclosure['component_version_id'],
        **{axis: enclosure[axis] for axis in ('width', 'height', 'depth')})
    body['operations'].append(second)
    repo = OperationBatchRepository(postgres_database)
    bad = deepcopy(body)
    bad['operations'][1]['parameters']['width'] = 123
    with pytest.raises(DesignError):
        repo.commit(key, OperationPreviewRequest.model_validate(bad), 'rejected')
    assert load(postgres_database, key) == base
    assert history(postgres_database, key) == [[], []]
    result = repo.commit(key, OperationPreviewRequest.model_validate(body), 'engineering')
    assert result['document_sequence'] == base.document.document_sequence + 1
    assert result == repo.commit(key, OperationPreviewRequest.model_validate(body), 'engineering')
    assert len(history(postgres_database, key)[1]) == 2
    saved = load(postgres_database, key)
    assert saved.snapshots.cem.components[0].component_version_id == target['component_version_id']
    assert saved.snapshots.pdm.enclosure_width == enclosure['width']
    before_history = history(postgres_database, key)
    invalid = request_for(saved, 'UpdateRequirement')
    invalid['batch_id'] = str(uuid4())
    invalid['operations'][0]['operation_id'] = str(uuid4())
    invalid['operations'][0]['target']['requirement_id'] = 'unknown_requirement'
    with pytest.raises(DesignError):
        repo.commit(key, OperationPreviewRequest.model_validate(invalid), 'unknown-requirement')
    assert load(postgres_database, key) == saved
    assert history(postgres_database, key) == before_history
