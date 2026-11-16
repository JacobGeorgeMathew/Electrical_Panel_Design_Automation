"""Atomicity, exact retry receipts and optimistic concurrency on real PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from alembic import command
import pytest
from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError

from app.models.document_api import DocumentView
from app.models.operations import OperationPreviewRequest
from app.persistence import models as m
from app.persistence import operations as storage
from app.persistence.assets import content_hash
from app.persistence.documents import DocumentRepository
from app.persistence.manage import alembic_config, initialize
from app.persistence.operations import OperationBatchRepository, _prepare
from app.persistence.repositories import PersistenceError, ProjectRepository
from app.services.design_errors import DesignError
from tests.test_design_document_storage import isolated_database, row_images, stored_document
from tests.test_document_contract import document_fixture
from tests.test_operations import request_for


def batch_for(base, count=1, kind='MoveComponent'):
    body = request_for(base, kind)
    body['batch_id'] = str(uuid4())
    candidate = base
    body['operations'] = []
    for index in range(count):
        member = request_for(candidate, kind)['operations'][0]
        member['operation_id'] = str(uuid4())
        if kind == 'MoveComponent':
            member['parameters']['position_mm']['x'] += index * 10
        else:
            member['parameters']['value'] += index * 10
        body['operations'].append(member)
        from app.services.operations.registry import preview_operations
        candidate = preview_operations(base, OperationPreviewRequest.model_validate(body)).candidate
    return OperationPreviewRequest.model_validate(body)


def persisted_base(database):
    project_id = uuid4()
    _, base = stored_document(project_id)
    with database.sessions.begin() as session:
        session.execute(insert(m.projects).values(id=project_id, project_code='ops-' + project_id.hex,
            name='Operation storage', lock_version=1, workspace={'keep': 'display'},
            recovery={'keep': 'checkpoint'}, recovery_version=4))
        DocumentRepository(session).store(base, create=True)
    return str(project_id), base


def history(database, project_id):
    with database.sessions() as session:
        return [list(session.execute(select(table).where(table.c.project_id == project_id)
            .order_by(*table.primary_key.columns)).mappings())
            for table in (m.operation_batches, m.document_operations)]


def load(database, project_id):
    with database.sessions() as session:
        return DocumentRepository(session).load(ProjectRepository(session).row(project_id))


def test_preparation_is_detached_ordered_and_contract_validated():
    base = document_fixture()
    before = base.model_dump(mode='json')
    request = batch_for(base, count=2)
    prepared = _prepare(base, request)
    assert base.model_dump(mode='json') == before
    assert prepared.members[0]['after_sha256'] == prepared.members[1]['before_sha256']
    assert prepared.after.document.document_sequence == base.document.document_sequence + 1
    assert prepared.after.document.lock_version == base.document.lock_version + 1
    assert DocumentView.model_validate_json(prepared.after.model_dump_json()) == prepared.after
    assert prepared.after.document.pins == base.document.pins
    assert prepared.after.snapshots.cem == base.snapshots.cem
    assert all(check['status'] == 'UNRESOLVED' for check in prepared.required_checks)


@pytest.mark.parametrize('failure', ['unknown_target', 'stale_snapshot', 'proposal'])
def test_failed_validation_has_no_durable_changes(postgres_database, failure):
    key, base = persisted_base(postgres_database)
    body = batch_for(base, count=2).model_dump(mode='json')
    second = body['operations'][1]
    if failure == 'unknown_target':
        second['target']['cem_component_id'] = 'missing'
    elif failure == 'stale_snapshot':
        second['preconditions']['snapshot_sha256'] = base.document.models.pdm.sha256
    else:
        second.update(proposal_status='PROPOSED')
        second['origin'].update(kind='AI_PROPOSAL', proposal_id='proposal-1')
    before = row_images(postgres_database.engine,
        {'projects', 'design_documents', 'design_document_snapshots', 'operation_batches', 'document_operations'})
    with pytest.raises((DesignError, PersistenceError)):
        OperationBatchRepository(postgres_database).commit(key,
            OperationPreviewRequest.model_validate(body), 'failed-validation')
    assert row_images(postgres_database.engine, before.keys()) == before


def test_commit_retains_member_states_and_separate_lifecycle_data(postgres_database):
    key, base = persisted_base(postgres_database)
    request = batch_for(base, count=2)
    untouched = row_images(postgres_database.engine, {'project_revisions', 'generated_artifacts'})
    repo = OperationBatchRepository(postgres_database)
    receipt = repo.commit(key, request, 'move-two')
    batches, members = history(postgres_database, key)
    assert len(batches) == 1 and len(members) == 2
    assert [row['sequence'] for row in members] == [1, 2]
    assert [row['batch_index'] for row in members] == [0, 1]
    assert members[0]['after_sha256'] == members[1]['before_sha256']
    for row, operation in zip(members, request.operations):
        assert row['origin'] == operation.origin.model_dump(mode='json')
        assert row['payload_sha256'] == content_hash(row['payload'])
        for digest in (row['before_sha256'], row['after_sha256']):
            with postgres_database.sessions() as session:
                snapshot = session.scalar(select(m.design_document_snapshots.c.snapshot).where(
                    m.design_document_snapshots.c.document_id == base.document.document_id,
                    m.design_document_snapshots.c.model_kind == 'PDM',
                    m.design_document_snapshots.c.sha256 == digest))
            assert snapshot is not None and content_hash(snapshot) == digest
    assert batches[0]['payload_sha256'] == content_hash(request.model_dump(mode='json'))
    assert batches[0]['before_state'] == base.document.model_dump(mode='json')
    reopened = load(postgres_database, key)
    assert receipt['result'] == reopened.model_dump(mode='json')
    assert reopened.document.document_sequence == reopened.document.lock_version - 1 == 1
    assert reopened.document.provenance.last_operation_id == str(request.operations[-1].operation_id)
    assert reopened.snapshots.cem == base.snapshots.cem
    assert reopened.snapshots.schematic == base.snapshots.schematic
    assert reopened.snapshots.pdm.routes == base.snapshots.pdm.routes
    assert reopened.document.pins == base.document.pins
    with postgres_database.sessions() as session:
        project = ProjectRepository(session).row(key)
    assert project['workspace'] == {'keep': 'display'}
    assert project['recovery'] == {'keep': 'checkpoint'} and project['recovery_version'] == 4
    assert project['current_revision_id'] is None
    assert row_images(postgres_database.engine, untouched.keys()) == untouched


def test_late_member_database_failure_rolls_back_every_write(postgres_database):
    key, base = persisted_base(postgres_database)
    repo = OperationBatchRepository(postgres_database)
    first = batch_for(base)
    repo.commit(key, first, 'initial')
    current = load(postgres_database, key)
    request = batch_for(current, count=2)
    # Reuse a previously committed UUID in the second member. The unique
    # constraint fails after the batch, snapshots, document and first member write.
    request.operations[1].operation_id = first.operations[0].operation_id
    before = row_images(postgres_database.engine,
        {'projects', 'design_documents', 'design_document_snapshots', 'operation_batches', 'document_operations'})
    with pytest.raises(PersistenceError) as error:
        repo.commit(key, request, 'rolled-back')
    assert error.value.code == 'OPERATION_STORAGE_CONFLICT'
    assert row_images(postgres_database.engine, before.keys()) == before
    # A failed key was not consumed and the sequence has no partial tail/gap.
    request.operations[1].operation_id = uuid4()
    receipt = repo.commit(key, request, 'rolled-back')
    assert receipt['first_operation_sequence'] == 2
    assert receipt['last_operation_sequence'] == 3


def test_lost_response_retry_after_later_edit_returns_exact_receipt(postgres_database, monkeypatch):
    key, base = persisted_base(postgres_database)
    request = batch_for(base)
    repo = OperationBatchRepository(postgres_database)
    original = repo.commit(key, request, 'lost-response')
    # The old receipt must survive a later document version and a repository restart.
    repo.commit(key, batch_for(load(postgres_database, key), kind='UpdateRequirement'), 'later-edit')
    before = row_images(postgres_database.engine,
        {'projects', 'design_documents', 'design_document_snapshots', 'operation_batches', 'document_operations'})

    def forbidden(*args):
        raise AssertionError('Retry must not evaluate operations again')

    monkeypatch.setattr(storage, '_prepare', forbidden)
    with postgres_database.sessions() as session:
        alias = ProjectRepository(session).row(key)['project_code']
    assert OperationBatchRepository(postgres_database).commit(alias, request, 'lost-response') == original
    changed = request.model_copy(deep=True)
    changed.operations[0].origin.actor_id = 'another-actor'
    with pytest.raises(PersistenceError) as error:
        repo.commit(key, changed, 'lost-response')
    assert error.value.code == 'IDEMPOTENCY_CONFLICT'
    assert row_images(postgres_database.engine, before.keys()) == before


@pytest.mark.parametrize('same_key', [False, True])
def test_concurrent_batches_serialize_with_one_state_change(postgres_database, monkeypatch, same_key):
    key, base = persisted_base(postgres_database)
    first = batch_for(base)
    second = first if same_key else batch_for(base, kind='UpdateRequirement')
    barrier = Barrier(2, timeout=10)
    prepare = storage._prepare

    def synchronized(*args):
        result = prepare(*args)
        barrier.wait()  # Both candidates exist before either transaction begins.
        return result

    monkeypatch.setattr(storage, '_prepare', synchronized)

    def commit(request, idempotency_key):
        try:
            return OperationBatchRepository(postgres_database).commit(key, request, idempotency_key)
        except PersistenceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(commit, first, 'concurrent'),
                   executor.submit(commit, second, 'concurrent' if same_key else 'other-key')]
        results = [future.result(timeout=20) for future in futures]
    if same_key:
        assert results[0] == results[1] and isinstance(results[0], dict)
    else:
        assert sum(isinstance(value, dict) for value in results) == 1
        assert 'DOCUMENT_CONFLICT' in results
    batches, members = history(postgres_database, key)
    assert len(batches) == len(members) == 1
    assert load(postgres_database, key).document.document_sequence == 1


def test_recheck_after_validation_and_no_handlers_in_transaction(postgres_database, monkeypatch):
    key, base = persisted_base(postgres_database)
    prepare = storage._prepare

    def intervening_write(*args):
        # The read session has closed before the handler is invoked.
        assert postgres_database.engine.pool.checkedout() == 0
        prepared = prepare(*args)
        with postgres_database.sessions.begin() as session:
            projects = ProjectRepository(session)
            projects.touch(projects.row(key, lock=True), name='Concurrent metadata edit')
        return prepared

    monkeypatch.setattr(storage, '_prepare', intervening_write)
    with pytest.raises(PersistenceError) as error:
        OperationBatchRepository(postgres_database).commit(key, batch_for(base), 'stale')
    assert error.value.code == 'DOCUMENT_CONFLICT'
    assert history(postgres_database, key) == [[], []]
    assert load(postgres_database, key).document.document_sequence == 0


def test_noop_receipt_and_project_scoped_keys(postgres_database):
    repo = OperationBatchRepository(postgres_database)
    for _ in range(2):
        key, base = persisted_base(postgres_database)
        request = batch_for(base)
        position = base.snapshots.pdm.components[0].position
        request.operations[0].parameters.position_mm = type(request.operations[0].parameters.position_mm)(
            **position.model_dump())
        receipt = repo.commit(key, request, 'shared-key')
        assert receipt['document_sequence'] == 0 and receipt['lock_version'] == 1
        assert receipt['before_content_sha256'] == receipt['after_content_sha256']
        assert receipt['required_checks'] == []
        assert repo.commit(key, request, 'shared-key') == receipt
        assert len(history(postgres_database, key)[1]) == 1


def test_0005_upgrade_preserves_documents_and_generated_mapping(postgres_database):
    with isolated_database(postgres_database.settings) as database:
        cfg = alembic_config(database.settings.url)
        command.upgrade(cfg, '0005_design_documents')
        key, base = persisted_base(database)
        tables = {'projects', 'design_documents', 'design_document_snapshots'}
        before = row_images(database.engine, tables)
        assert not database.ready()
        initialize(database)
        assert row_images(database.engine, tables) == before
        assert database.ready()
        command.check(cfg)
        receipt = OperationBatchRepository(database).commit(key, batch_for(base), 'upgraded')
        assert receipt['document_sequence'] == 1


def test_history_is_immutable_and_snapshot_ownership_enforced(postgres_database):
    from tests.integrity_support import privileged_connection
    key, base = persisted_base(postgres_database)
    OperationBatchRepository(postgres_database).commit(key, batch_for(base), 'immutable')
    _, members = history(postgres_database, key)
    for table in (m.operation_batches, m.document_operations):
        with pytest.raises(PersistenceError) as error, postgres_database.sessions.begin() as session:
            session.execute(table.delete().where(table.c.project_id == key))
        assert error.value.code == 'IMMUTABLE_PUBLICATION'
    other, other_base = persisted_base(postgres_database)
    with privileged_connection(postgres_database) as conn:
        for changes in ({'before_sha256': 'a' * 64}, {'document_id': other_base.document.document_id},
                        {'project_id': other}, {'batch_index': 100}, {'sequence': 0}):
            row = {**dict(members[0]), 'sequence': 50, 'operation_id': uuid4(),
                   'batch_index': 1, **changes}
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(insert(m.document_operations).values(**row))
