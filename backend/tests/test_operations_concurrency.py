"""Independent multi-client commit races and transport-loss reconciliation."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier

import pytest

from app.models.operations import OperationPreviewRequest
from app.persistence import operations as storage
from app.persistence.operations import OperationBatchRepository
from app.persistence.repositories import PersistenceError
from app.services.operations.registry import preview_operations
from tests.test_design_document_storage import row_images
from tests.test_operation_persistence import batch_for, history, load, persisted_base
from tests.test_operations import fixture_choices


@pytest.mark.parametrize('race', ['independent', 'exact_retry', 'key_collision'])
def test_parallel_clients_have_one_durable_winner(postgres_database, monkeypatch, race):
    db = postgres_database
    key, base = persisted_base(db)
    first = batch_for(base)
    second = deepcopy(first) if race == 'exact_retry' else batch_for(base, kind='UpdateRequirement')
    requests = [first, second]
    local_edits = [r.model_dump(mode='json') for r in requests]
    preserved = row_images(db.engine, {'project_revisions', 'generated_artifacts'})
    barrier = Barrier(2, timeout=15)
    prepare = storage._prepare

    def both_candidates_ready(*args):
        candidate = prepare(*args)
        barrier.wait()
        return candidate

    monkeypatch.setattr(storage, '_prepare', both_candidates_ready)

    def submit(index):
        try:
            return OperationBatchRepository(db).commit(key, requests[index],
                'same' if race != 'independent' else f'client-{index}')
        except PersistenceError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit, index) for index in range(2)]
        outcomes = [f.result(timeout=30) for f in futures]
    receipts = [value for value in outcomes if isinstance(value, dict)]
    if race == 'exact_retry':
        assert len(receipts) == 2 and receipts[0] == receipts[1]
    else:
        assert len(receipts) == 1
        assert ('DOCUMENT_CONFLICT' if race == 'independent' else 'IDEMPOTENCY_CONFLICT') in outcomes
    reopened = load(db, key)
    assert reopened.model_dump(mode='json') == receipts[0]['result']
    assert (reopened.document.document_sequence, reopened.document.lock_version) == (1, 2)
    batches, operations = history(db, key)
    assert len(batches) == len(operations) == 1
    assert [r.model_dump(mode='json') for r in requests] == local_edits
    assert row_images(db.engine, preserved.keys()) == preserved
    # Recovery has its own clock and must retain a losing client's checkpoint.
    from app.persistence.repositories import ProjectRepository
    with db.sessions() as session:
        project = ProjectRepository(session).row(key)
        assert project['recovery'] == {'keep': 'checkpoint'} and project['recovery_version'] == 4
        assert project['workspace'] == {'keep': 'display'}


def test_response_lost_after_commit_reconciles_after_newer_edit_and_restart(postgres_database, monkeypatch):
    db = postgres_database
    key, base = persisted_base(db)
    request = batch_for(base)
    local = request.model_dump(mode='json')
    saved_receipts = []

    def broken_transport():
        saved_receipts.append(OperationBatchRepository(db).commit(key, request, 'lost-ack'))
        raise ConnectionError('Injected response loss after durable commit')

    with pytest.raises(ConnectionError, match='response loss'):
        broken_transport()
    OperationBatchRepository(db).commit(key, batch_for(load(db, key), kind='UpdateRequirement'), 'newer')
    before = row_images(db.engine, {'projects', 'design_documents', 'design_document_snapshots',
                                   'operation_batches', 'document_operations', 'project_revisions'})

    def forbidden(*args):
        pytest.fail('A lost acknowledgement must resolve without reevaluating the old base')

    monkeypatch.setattr(storage, '_prepare', forbidden)
    from app.main import create_app
    from tests.local_client import LocalClient
    with LocalClient(create_app(db)) as restarted:
        response = restarted.post(f'/api/v1/projects/{key}/document/operations/commit',
            json=local, headers={'Idempotency-Key': 'lost-ack'})
        assert response.status_code == 200, response.text
        assert response.json() == saved_receipts[0]
    assert load(db, key).document.document_sequence == 2
    assert request.model_dump(mode='json') == local
    assert row_images(db.engine, before.keys()) == before


@pytest.mark.parametrize('drift', ['operation', 'metadata', 'snapshot'])
def test_stale_preview_never_overwrites_intervening_state(postgres_database, drift):
    db = postgres_database
    key, base = persisted_base(db)
    request = batch_for(base)
    preview = preview_operations(base, request, fixture_choices(base))
    assert preview.persisted is False
    local = request.model_dump(mode='json')
    if drift == 'operation':
        OperationBatchRepository(db).commit(key, batch_for(base, kind='UpdateRequirement'), 'winner')
    elif drift == 'metadata':
        from app.persistence.repositories import ProjectRepository
        with db.sessions.begin() as session:
            repo = ProjectRepository(session)
            repo.touch(repo.row(key, lock=True), name='Intervening metadata')
    else:
        # Same document clock, wrong snapshot precondition: no client can use a
        # valid preview to authorize another body with altered consumed inputs.
        local['operations'][0]['preconditions']['snapshot_sha256'] = '0' * 64
        request = OperationPreviewRequest.model_validate(local)
    before = row_images(db.engine, {'projects', 'design_documents', 'design_document_snapshots',
        'operation_batches', 'document_operations', 'project_revisions', 'generated_artifacts'})
    with pytest.raises(PersistenceError) as caught:
        OperationBatchRepository(db).commit(key, request, 'stale-preview')
    assert caught.value.code == ('OPERATION_PRECONDITION' if drift == 'snapshot' else 'DOCUMENT_CONFLICT')
    assert request.model_dump(mode='json') == local
    assert row_images(db.engine, before.keys()) == before
