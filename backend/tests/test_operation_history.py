"""Durable batch inverses, branch fencing, retries and gesture grouping."""
from copy import deepcopy
from uuid import uuid4

import pytest

from app.models.document_api import DocumentSave
from app.models.operations import HistoryRequest, OperationPreviewRequest
from app.persistence import operations as storage
from app.persistence.assets import AssetStore
from app.persistence.documents import DocumentRepository, document_hash
from app.persistence.operations import OperationBatchRepository
from app.persistence.repositories import CatalogRepository, PersistenceError
from app.services.document_service import DocumentService, DIRTY_STAGES
from app.services.operations.history import semantic_hash
from app.services.operations.registry import preview_operations
from tests.test_component_operations import add_request, removal
from tests.test_design_document_storage import row_images
from tests.test_document_contract import document_fixture
from tests.test_operation_persistence import persisted_base, load, history, batch_for
from tests.test_schematic_operations import with_evidence, connection_request, schematic_command
from tests.test_operations import fixture_choices


def history_request(base, target, action='UNDO'):
    return HistoryRequest(batch_id=uuid4(), operation_id=uuid4(), document_id=base.document.document_id,
        base_sequence=base.document.document_sequence, expected_version=base.document.lock_version,
        base_revision_id=base.document.base_revision_id, before_content_sha256=document_hash(base.document),
        target_batch_id=target, action=action, origin=dict(kind='MANUAL', actor_id='user'))


def assert_semantics(actual, expected):
    assert semantic_hash(actual.document) == semantic_hash(expected.document)
    assert actual.snapshots == expected.snapshots
    assert actual.document.dirty_stages == expected.document.dirty_stages


def test_semantic_preconditions_include_dependency_status_pins_and_configuration():
    base = document_fixture()
    changed = deepcopy(base)
    changed.document.lock_version += 1
    changed.document.document_sequence += 1
    changed.document.provenance.actor_id = 'another'
    assert semantic_hash(changed.document) == semantic_hash(base.document)
    for field, value in [('dirty_stages', []), ('configuration', {'different': True})]:
        changed = deepcopy(base)
        setattr(changed.document, field, value)
        assert semantic_hash(changed.document) != semantic_hash(base.document)


def test_history_request_does_not_accept_client_inverse_or_proposal():
    from pydantic import ValidationError
    body = history_request(document_fixture(), uuid4()).model_dump(mode='json')
    with pytest.raises(ValidationError):
        HistoryRequest.model_validate({**body, 'inverse': {}})
    body['origin'].update(kind='AI_PROPOSAL', proposal_id='proposal')
    with pytest.raises(ValidationError):
        HistoryRequest.model_validate(body)


def operation_for(database, base, kind):
    if kind in ('move', 'requirement', 'gesture'):
        return batch_for(base, count=3 if kind == 'gesture' else 1,
                         kind='UpdateRequirement' if kind == 'requirement' else 'MoveComponent')
    if kind == 'connection':
        return connection_request(base)
    if kind == 'remove':
        return removal(base, True)
    if kind == 'symbol':
        return schematic_command(base, 'MoveSymbol', dict(symbol_id='symbol-1'), dict(position_mm=dict(x=280, y=120)))
    with database.sessions() as session:
        row = CatalogRepository(session, AssetStore(database.settings.asset_root)).get_component('MCB_16A_1P_10KA')
    add, choices = add_request(base, row)
    if kind == 'add':
        return add
    # A mixed transaction, with member preconditions at their execution point.
    body = batch_for(base).model_dump(mode='json')
    candidate = preview_operations(base, OperationPreviewRequest.model_validate(body)).candidate
    update = batch_for(candidate, kind='UpdateRequirement').operations[0]
    body['operations'].append(update.model_dump(mode='json'))
    candidate = preview_operations(base, OperationPreviewRequest.model_validate(body), fixture_choices(base)).candidate
    add, _ = add_request(candidate, row)
    body['operations'].append(add.operations[0].model_dump(mode='json'))
    return OperationPreviewRequest.model_validate(body)


@pytest.mark.parametrize('kind', ['move', 'requirement', 'connection', 'add', 'remove', 'mixed', 'symbol', 'gesture'])
def test_round_trip_restores_full_semantics_and_dirty_stages(postgres_database, kind):
    key, base = persisted_base(postgres_database)
    if kind == 'connection':
        base = with_evidence(base)
    base.document.dirty_stages = []
    with postgres_database.sessions.begin() as session:
        DocumentRepository(session).store(base)
    untouched = row_images(postgres_database.engine, {'project_revisions', 'generated_artifacts'})
    repo = OperationBatchRepository(postgres_database)
    request = operation_for(postgres_database, base, kind)
    repo.commit(key, request, 'forward')
    forward = load(postgres_database, key)
    # Save/reopen and a repository restart do not reset the durable history.
    DocumentService(postgres_database).save(key, DocumentSave(document_id=forward.document.document_id,
        expected_version=forward.document.lock_version, expected_document_sequence=forward.document.document_sequence,
        requirements=forward.snapshots.requirements, configuration=forward.document.configuration))
    service = DocumentService(postgres_database)
    assert service.operation_history(key).undo_batch_ids == [request.batch_id]
    undo = history_request(service.load(key), request.batch_id)
    receipt = service.apply_history(key, undo, 'undo')
    undone = load(postgres_database, key)
    assert_semantics(undone, base)
    assert undone.document.document_sequence == base.document.document_sequence + 2
    assert service.operation_history(key).redo_batch_ids == [request.batch_id]
    repo = OperationBatchRepository(postgres_database)
    redo = history_request(undone, request.batch_id, 'REDO')
    repo.apply_history(key, redo, 'redo')
    assert_semantics(load(postgres_database, key), forward)
    # Lost undo response returns the original receipt after subsequent redo.
    assert repo.apply_history(key, undo, 'undo') == receipt
    assert len(history(postgres_database, key)[0]) == 3
    assert row_images(postgres_database.engine, untouched.keys()) == untouched


@pytest.mark.parametrize('field,value', [('base_sequence', 99), ('expected_version', 99),
                                      ('before_content_sha256', '0' * 64), ('base_revision_id', 'other')])
def test_stale_undo_is_conflict_and_does_not_write(postgres_database, field, value):
    key, base = persisted_base(postgres_database)
    repo = OperationBatchRepository(postgres_database)
    batch = batch_for(base)
    repo.commit(key, batch, 'move')
    request = history_request(load(postgres_database, key), batch.batch_id)
    setattr(request, field, value)
    before = row_images(postgres_database.engine,
        {'projects', 'design_documents', 'design_document_snapshots', 'operation_batches', 'document_operations'})
    with pytest.raises(PersistenceError) as error:
        repo.apply_history(key, request, 'stale')
    assert error.value.code == 'DOCUMENT_CONFLICT'
    assert row_images(postgres_database.engine, before.keys()) == before


def test_divergent_commit_clears_redo_without_mutating_retained_history(postgres_database):
    key, base = persisted_base(postgres_database)
    repo = OperationBatchRepository(postgres_database)
    first = batch_for(base)
    repo.commit(key, first, 'first')
    repo.apply_history(key, history_request(load(postgres_database, key), first.batch_id), 'undo')
    old_rows = history(postgres_database, key)
    next_batch = batch_for(load(postgres_database, key), kind='UpdateRequirement')
    repo.commit(key, next_batch, 'branch')
    current = load(postgres_database, key)
    view = DocumentService(postgres_database).operation_history(key)
    assert view.redo_batch_ids == [] and view.undo_batch_ids == [next_batch.batch_id]
    with pytest.raises(PersistenceError):
        repo.apply_history(key, history_request(current, first.batch_id, 'REDO'), 'invalid-redo')
    retained = {row['id']: row for row in history(postgres_database, key)[0]}
    assert all(retained[row['id']] == row for row in old_rows[0])


def test_inverse_rechecked_under_lock_after_detached_preparation(postgres_database, monkeypatch):
    from app.persistence.repositories import ProjectRepository
    key, base = persisted_base(postgres_database)
    repo = OperationBatchRepository(postgres_database)
    batch = batch_for(base)
    repo.commit(key, batch, 'first')
    request = history_request(load(postgres_database, key), batch.batch_id)
    prepare = storage._prepare_history

    def intervene(*args):
        assert postgres_database.engine.pool.checkedout() == 0
        result = prepare(*args)
        with postgres_database.sessions.begin() as session:
            projects = ProjectRepository(session)
            projects.touch(projects.row(key, lock=True), name='Concurrent edit')
        return result

    monkeypatch.setattr(storage, '_prepare_history', intervene)
    with pytest.raises(PersistenceError) as error:
        repo.apply_history(key, request, 'stale-during-validation')
    assert error.value.code == 'DOCUMENT_CONFLICT'
    assert len(history(postgres_database, key)[0]) == 1


def test_multi_step_undo_redo_and_noop_receipts(postgres_database):
    key, base = persisted_base(postgres_database)
    repo = OperationBatchRepository(postgres_database)
    batches = []
    for kind in ('MoveComponent', 'UpdateRequirement'):
        batch = batch_for(load(postgres_database, key), kind=kind)
        batches.append(batch)
        repo.commit(key, batch, 'forward-' + kind)
    final = load(postgres_database, key)
    for batch in reversed(batches):
        repo.apply_history(key, history_request(load(postgres_database, key), batch.batch_id), 'undo-' + str(batch.batch_id))
    assert_semantics(load(postgres_database, key), base)
    noop = batch_for(load(postgres_database, key))
    noop.operations[0].parameters.position_mm = type(noop.operations[0].parameters.position_mm)(
        **base.snapshots.pdm.components[0].position.model_dump())
    repo.commit(key, noop, 'noop')
    assert DocumentService(postgres_database).operation_history(key).redo_batch_ids == [b.batch_id for b in reversed(batches)]
    for batch in batches:
        repo.apply_history(key, history_request(load(postgres_database, key), batch.batch_id, 'REDO'), 'redo-' + str(batch.batch_id))
    assert_semantics(load(postgres_database, key), final)


def test_save_changed_inputs_fences_old_history(postgres_database):
    key, base = persisted_base(postgres_database)
    repo = OperationBatchRepository(postgres_database)
    batch = batch_for(base)
    repo.commit(key, batch, 'first')
    current = load(postgres_database, key)
    DocumentService(postgres_database).save(key, DocumentSave(document_id=current.document.document_id,
        expected_version=current.document.lock_version, expected_document_sequence=current.document.document_sequence,
        requirements=current.snapshots.requirements, configuration={'enclosure_id': 'explicit-other'}))
    assert DocumentService(postgres_database).operation_history(key).undo_batch_ids == []
    with pytest.raises(PersistenceError):
        repo.apply_history(key, history_request(load(postgres_database, key), batch.batch_id), 'outdated-history')


def test_changed_save_then_revert_does_not_resurrect_redo(postgres_database):
    key, base = persisted_base(postgres_database)
    base.document.dirty_stages = list(DIRTY_STAGES)
    with postgres_database.sessions.begin() as session:
        DocumentRepository(session).store(base)
    repo = OperationBatchRepository(postgres_database)
    batch = batch_for(base)
    repo.commit(key, batch, 'forward')
    repo.apply_history(key, history_request(load(postgres_database, key), batch.batch_id), 'undo')
    for config in ({'enclosure_id': 'temporary'}, {}):
        current = load(postgres_database, key)
        DocumentService(postgres_database).save(key, DocumentSave(document_id=current.document.document_id,
            expected_version=current.document.lock_version, expected_document_sequence=current.document.document_sequence,
            requirements=current.snapshots.requirements, configuration=config))
    assert_semantics(load(postgres_database, key), base)
    assert DocumentService(postgres_database).operation_history(key).redo_batch_ids == []


def test_concurrent_undo_serializes_and_failed_inverse_retains_history(postgres_database, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    key, base = persisted_base(postgres_database)
    repo = OperationBatchRepository(postgres_database)
    batch = batch_for(base)
    repo.commit(key, batch, 'first')
    current = load(postgres_database, key)
    invalid = history_request(current, batch.batch_id)
    invalid.operation_id = batch.operations[0].operation_id
    before = row_images(postgres_database.engine,
        {'projects', 'design_documents', 'design_document_snapshots', 'operation_batches', 'document_operations'})
    with pytest.raises(PersistenceError) as error:
        repo.apply_history(key, invalid, 'duplicate-member')
    assert error.value.code == 'OPERATION_STORAGE_CONFLICT'
    assert row_images(postgres_database.engine, before.keys()) == before
    barrier, prepare = Barrier(2, timeout=10), storage._prepare_history

    def synchronized(*args):
        result = prepare(*args)
        barrier.wait()
        return result

    monkeypatch.setattr(storage, '_prepare_history', synchronized)

    def commit(index):
        try:
            return repo.apply_history(key, history_request(current, batch.batch_id), 'concurrent-' + str(index))
        except PersistenceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(commit, (1, 2)))
    assert sum(isinstance(value, dict) for value in results) == 1
    assert 'DOCUMENT_CONFLICT' in results
    assert len(history(postgres_database, key)[0]) == 2
