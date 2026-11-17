"""Real PostgreSQL queue races and restart/expiry evidence; no development data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.main import create_app
from app.persistence import models as m
from app.persistence.jobs import JobRepository
from app.persistence.repositories import PersistenceError, identifier


@pytest.fixture
def intent(api, postgres_database):
    response = api.post('/api/projects', json={'name': 'Durable queue tests'})
    assert response.status_code == 201, response.text
    project_id = identifier(response.json()['id'])
    with postgres_database.sessions() as session:
        document_id = session.scalar(select(m.design_documents.c.id).where(
            m.design_documents.c.project_id == project_id))
    return dict(execution_key=uuid4().hex, project_id=project_id,
        document_id=document_id, base_sequence=0, kind=uuid4().hex,
        input_signature='a' * 64, inputs={'stage_signatures': {'cad': 'b' * 64}},
        artifact_intent={'format': 'GLB', 'generator_version': '3'})


def enqueue(db, intent, **overrides):
    with db.sessions.begin() as session:
        return JobRepository(session).enqueue(**(intent | overrides))


def claim(db, intent, owner='worker', **kwargs):
    with db.sessions.begin() as session:
        return JobRepository(session).claim(owner, kinds=[intent['kind']], **kwargs)


def expire(db, job):
    with db.sessions.begin() as session:
        session.execute(update(m.jobs).where(m.jobs.c.id == job['id']).values(
            lease_expires_at=func.clock_timestamp() - timedelta(seconds=1)))


def recover(db):
    with db.sessions.begin() as session:
        return JobRepository(session).recover_expired()


def test_enqueue_preserves_intent_and_reuses_execution_key(postgres_database, intent):
    db = postgres_database
    first = enqueue(db, intent, base_sequence=17)
    second = enqueue(db, intent, base_sequence=17)
    assert first == second
    assert first['state'] == 'QUEUED' and first['attempts'] == 0
    assert first['inputs'] == intent['inputs']
    assert first['artifact_intent'] == intent['artifact_intent']
    assert first['input_signature'] == intent['input_signature']
    for change in ({'base_sequence': 18}, {'input_signature': 'c' * 64},
                   {'inputs': {}}, {'artifact_intent': {}}, {'max_attempts': 2}):
        with pytest.raises(PersistenceError, match='different job intent') as error:
            enqueue(db, intent, **({'base_sequence': 17} | change))
        assert error.value.code == 'JOB_EXECUTION_CONFLICT'


def test_concurrent_enqueue_has_one_record(postgres_database, intent):
    barrier = Barrier(2)

    def submit():
        barrier.wait(timeout=10)
        return enqueue(postgres_database, intent)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(submit) for _ in range(2)]
        rows = [f.result(timeout=15) for f in futures]
    assert rows[0]['id'] == rows[1]['id']
    with postgres_database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(m.jobs).where(
            m.jobs.c.execution_key == intent['execution_key'])) == 1


def test_two_workers_cannot_claim_same_active_lease(postgres_database, intent):
    db = postgres_database
    job = enqueue(db, intent)
    barrier = Barrier(2)

    def worker(owner):
        barrier.wait(timeout=10)
        return claim(db, intent, owner)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, owner) for owner in ['one', 'two']]
        rows = [f.result(timeout=15) for f in futures]
    winners = [row for row in rows if row is not None]
    assert len(winners) == 1
    assert winners[0]['id'] == job['id'] and winners[0]['attempts'] == 1
    assert winners[0]['lease_token'] and winners[0]['lease_expires_at']
    assert claim(db, intent, 'three') is None


def test_claim_skips_locked_job_and_rollback_preserves_attempts(postgres_database, intent):
    db = postgres_database
    first = enqueue(db, intent)
    second = enqueue(db, intent, execution_key=uuid4().hex)
    with db.sessions() as session:
        transaction = session.begin()
        locked = JobRepository(session).claim('one', kinds=[intent['kind']])
        assert locked['id'] == first['id']
        other = claim(db, intent, 'two')
        assert other['id'] == second['id']
        transaction.rollback()
    reclaimed = claim(db, intent, 'three')
    assert reclaimed['id'] == first['id'] and reclaimed['attempts'] == 1
    assert reclaimed['lease_token'] != locked['lease_token']


def test_restart_preserves_queue_and_healthy_leases(postgres_database, intent):
    db = postgres_database
    enqueue(db, intent)
    running = claim(db, intent, lease_seconds=3600)
    queued = enqueue(db, intent, execution_key=uuid4().hex)
    with TestClient(create_app(db)) as restarted:
        assert restarted.get('/ready').status_code == 200
        with db.sessions.begin() as session:
            repository = JobRepository(session)
            assert repository.get(running['id']) == running
            assert repository.get(queued['id']) == queued
            recovered = repository.recover_expired()
            assert running['id'] not in [row['id'] for row in recovered]
            assert repository.get(running['id']) == running
            assert repository.get(queued['id']) == queued


def test_expiry_recovery_is_bounded_and_fences_same_owner_retry(postgres_database, intent):
    db = postgres_database
    job = enqueue(db, intent, max_attempts=2)
    first = claim(db, intent, 'same-owner')
    expire(db, first)
    for method in ('heartbeat', 'succeed', 'fail'):
        with db.sessions.begin() as session, pytest.raises(PersistenceError) as error:
            kwargs = {'result': {}} if method == 'succeed' else {}
            getattr(JobRepository(session), method)(job['id'], 'same-owner', first['lease_token'], **kwargs)
        assert error.value.code == 'JOB_LEASE_LOST'
    with TestClient(create_app(db)):
        # Startup does not pretend to execute or recover durable work.
        with db.sessions() as session:
            assert JobRepository(session).get(job['id'])['state'] == 'RUNNING'
        rows = recover(db)
        assert next(r for r in rows if r['id'] == job['id'])['state'] == 'QUEUED'
    second = claim(db, intent, 'same-owner')
    assert second['attempts'] == 2 and second['lease_token'] != first['lease_token']
    with db.sessions.begin() as session, pytest.raises(PersistenceError):
        JobRepository(session).succeed(job['id'], 'same-owner', first['lease_token'], result={})
    expire(db, second)
    exhausted = next(row for row in recover(db) if row['id'] == job['id'])
    assert exhausted['state'] == 'FAILED' and exhausted['attempts'] == 2
    assert exhausted['error']['code'] == 'JOB_ATTEMPTS_EXHAUSTED'
    assert exhausted['completed_at'] and exhausted['lease_token'] is None
    assert claim(db, intent) is None
    assert enqueue(db, intent, max_attempts=2) == exhausted
    assert job['id'] not in [row['id'] for row in recover(db)]


def test_concurrent_expiry_recovery_is_exclusive(postgres_database, intent):
    db = postgres_database
    enqueue(db, intent)
    running = claim(db, intent)
    expire(db, running)
    barrier = Barrier(2)

    def recoverer():
        barrier.wait(timeout=10)
        return recover(db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(recoverer) for _ in range(2)]
        rows = [f.result(timeout=15) for f in futures]
    assert sum(row['id'] == running['id'] for batch in rows for row in batch) == 1


def test_heartbeat_checks_deadline_after_waiting_for_row_lock(postgres_database, intent):
    db = postgres_database
    enqueue(db, intent)
    running = claim(db, intent, lease_seconds=1)
    barrier = Barrier(2)

    def heartbeat():
        with db.sessions.begin() as session:
            barrier.wait(timeout=10)
            return JobRepository(session).heartbeat(running['id'], 'worker', running['lease_token'])

    with ThreadPoolExecutor(max_workers=1) as pool:
        with db.sessions.begin() as session:
            session.execute(select(m.jobs.c.id).where(m.jobs.c.id == running['id']).with_for_update())
            pending = pool.submit(heartbeat)
            barrier.wait(timeout=10)
            session.execute(select(func.pg_sleep(1.1)))
        with pytest.raises(PersistenceError) as error:
            pending.result(timeout=10)
        assert error.value.code == 'JOB_LEASE_LOST'


def test_heartbeat_and_terminal_outcomes(postgres_database, intent):
    db = postgres_database
    enqueue(db, intent)
    running = claim(db, intent)
    with db.sessions.begin() as session:
        repository = JobRepository(session)
        for owner, token in [('other', running['lease_token']), ('worker', uuid4())]:
            with pytest.raises(PersistenceError):
                repository.heartbeat(running['id'], owner, token)
        renewed = repository.heartbeat(running['id'], 'worker', running['lease_token'], lease_seconds=120)
        shorter = repository.heartbeat(running['id'], 'worker', running['lease_token'], lease_seconds=1)
        assert shorter['lease_expires_at'] == renewed['lease_expires_at'] > running['lease_expires_at']
        done = repository.succeed(running['id'], 'worker', running['lease_token'], result={'sha256': 'd' * 64})
        assert done['state'] == 'SUCCEEDED' and done['lease_owner'] is None
        assert repository.cancel(running['id']) == done
        with pytest.raises(PersistenceError):
            repository.heartbeat(running['id'], 'worker', running['lease_token'])
    failed = enqueue(db, intent, execution_key=uuid4().hex)
    active = claim(db, intent)
    with db.sessions.begin() as session:
        failed = JobRepository(session).fail(failed['id'], 'worker', active['lease_token'], code='CAD_UNAVAILABLE')
        assert failed['state'] == 'FAILED' and failed['error']['code'] == 'CAD_UNAVAILABLE'
    with TestClient(create_app(db)):
        with db.sessions() as session:
            assert JobRepository(session).get(done['id']) == done
            assert JobRepository(session).get(failed['id']) == failed


@pytest.mark.parametrize('running', [False, True])
def test_cancellation_revokes_claim_and_is_idempotent(postgres_database, intent, running):
    db = postgres_database
    job = enqueue(db, intent)
    lease = claim(db, intent) if running else None
    with db.sessions.begin() as session:
        repository = JobRepository(session)
        cancelled = repository.cancel(job['id'])
        assert cancelled['state'] == 'CANCELLED'
        assert cancelled['lease_token'] is None and cancelled['completed_at']
        assert repository.cancel(job['id']) == cancelled
        if lease:
            with pytest.raises(PersistenceError):
                repository.succeed(job['id'], 'worker', lease['lease_token'], result={})
    assert claim(db, intent) is None
    assert job['id'] not in [row['id'] for row in recover(db)]


def test_job_intent_and_record_deletion_are_guarded(postgres_database, intent):
    db = postgres_database
    job = enqueue(db, intent)
    for statement in [update(m.jobs).where(m.jobs.c.id == job['id']).values(base_sequence=1),
                      delete(m.jobs).where(m.jobs.c.id == job['id'])]:
        with db.sessions.begin() as session, pytest.raises(PersistenceError) as error:
            session.execute(statement)
        assert error.value.code == 'IMMUTABLE_PUBLICATION'


@pytest.mark.parametrize('change', [
    {'state': 'RUNNING'}, {'state': 'UNKNOWN'}, {'attempts': 4},
    {'state': 'SUCCEEDED'}, {'state': 'FAILED'}, {'state': 'CANCELLED'},
    {'state': 'QUEUED', 'attempts': 3, 'started_at': func.clock_timestamp()},
    {'lease_owner': 'orphan'}, {'result': {}}, {'error': {}},
])
def test_database_rejects_inconsistent_job_state(postgres_database, intent, change):
    job = enqueue(postgres_database, intent)
    with postgres_database.sessions.begin() as session, pytest.raises(IntegrityError):
        session.execute(update(m.jobs).where(m.jobs.c.id == job['id']).values(**change))


def test_job_ownership_foreign_keys(postgres_database, intent):
    for change in [{'project_id': uuid4()}, {'revision_id': uuid4()}]:
        with pytest.raises(IntegrityError):
            enqueue(postgres_database, intent, **change)


@pytest.mark.parametrize('change', [
    {'max_attempts': 0}, {'max_attempts': 101}, {'max_attempts': True},
    {'base_sequence': -1}, {'execution_key': ''}, {'input_signature': 'invalid'},
    {'artifact_intent': []}, {'inputs': []},
])
def test_invalid_job_intent_is_structured(postgres_database, intent, change):
    with pytest.raises(PersistenceError) as error:
        enqueue(postgres_database, intent, **change)
    assert error.value.code == 'INVALID_JOB'
