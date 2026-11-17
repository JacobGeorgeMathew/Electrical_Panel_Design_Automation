"""Bounded process failures and PostgreSQL publication races."""
from datetime import timedelta
import os
import time

import pytest
from sqlalchemy import func, select, update

from app.jobs.runner import JobRunner
from app.jobs.worker import Budget, WorkerFailure, run_bounded
from app.persistence import models as m
from app.persistence.jobs import JobRepository
from app.persistence.repositories import PersistenceError, identifier
from app.services.project_service import ProjectService
from tests.test_postgres import checked, create


def slow():
    time.sleep(20)


def crash():
    os._exit(5)


def secret_error():
    raise RuntimeError('postgres://secret:password@private /private/path')


def too_large():
    return b'x' * 10000


def limits():
    import resource
    return {name: resource.getrlimit(getattr(resource, name)) for name in (
        'RLIMIT_CPU', 'RLIMIT_AS', 'RLIMIT_FSIZE', 'RLIMIT_NOFILE', 'RLIMIT_CORE')}


def test_resource_limits_are_applied_and_inputs_are_bounded():
    budget = Budget()
    observed = run_bounded(limits, budget=budget)
    for name, value in [('RLIMIT_CPU', budget.cpu_seconds), ('RLIMIT_AS', budget.memory_bytes),
                        ('RLIMIT_FSIZE', budget.output_bytes), ('RLIMIT_NOFILE', 64), ('RLIMIT_CORE', 0)]:
        assert observed[name] == (value, value)
    with pytest.raises(WorkerFailure) as error:
        run_bounded(len, b'x' * 1000, budget=Budget(output_bytes=100))
    assert error.value.code == 'WORKER_INPUT_LIMIT'


@pytest.mark.parametrize('call,code,budget', [
    (slow, 'WORKER_TIMEOUT', Budget(wall_seconds=.2)),
    (crash, 'WORKER_CRASHED', Budget()),
    (secret_error, 'WORKER_FAILED', Budget()),
    (too_large, 'WORKER_CRASHED', Budget(output_bytes=100)),
])
def test_bounded_failure_records(call, code, budget):
    started = time.monotonic()
    with pytest.raises(WorkerFailure) as error:
        run_bounded(call, budget=budget)
    assert error.value.code == code
    assert 'password' not in str(error.value.as_dict())
    assert time.monotonic() - started < 10


def test_cancellation_kills_work_and_slot_is_reusable():
    started = time.monotonic()
    with pytest.raises(WorkerFailure, match='Bounded') as error:
        run_bounded(slow, cancelled=lambda: time.monotonic() - started > .2)
    assert error.value.code == 'JOB_CANCELLED'
    assert run_bounded(abs, -2) == 2


def queued(db, api):
    project = create(api)
    revision = checked(api.post(f'/api/projects/{project["id"]}/design/generate', json={}))
    service = ProjectService(db, executor=object())
    artifact = service.queue_artifact(project['id'], 'GLB', revision['lock_version'])
    runner = JobRunner(db)
    job = runner.claim()
    assert str(job['id']) == artifact['id']
    file = service.assets.put(b'controlled worker result', 'glb')
    return service, runner, job, file, revision


@pytest.mark.parametrize('change', ['cancel', 'expire', 'sequence', 'signature', 'revision'])
def test_late_worker_cannot_attach(postgres_database, api, change):
    db = postgres_database
    # Prevent the app's independent consumer from racing this controlled worker.
    api.app.state.cad_executor.shutdown()
    service, runner, job, file, revision = queued(db, api)
    with db.sessions.begin() as session:
        if change == 'cancel':
            JobRepository(session).cancel(job['id'])
        elif change == 'expire':
            session.execute(update(m.jobs).where(m.jobs.c.id == job['id']).values(
                lease_expires_at=func.clock_timestamp() - timedelta(seconds=1)))
        elif change == 'sequence':
            row = session.execute(select(m.design_documents).where(
                m.design_documents.c.id == job['document_id'])).mappings().one()
            payload = dict(row['document'])
            payload['document_sequence'] += 1
            session.execute(update(m.design_documents).where(m.design_documents.c.id == job['document_id']).values(
                document_sequence=payload['document_sequence'], document=payload))
        elif change == 'signature':
            # Frozen intent is immutable in storage; simulate a stale/altered
            # worker presenting a different completion signature instead.
            job = dict(job, input_signature='a' * 64)
        else:
            session.execute(update(m.projects).where(m.projects.c.id == job['project_id']).values(current_revision_id=None))
    if change in {'cancel', 'expire'}:
        with pytest.raises(PersistenceError) as error:
            runner.complete(job, file)
        assert error.value.code == 'JOB_LEASE_LOST'
    else:
        assert runner.complete(job, file) is False
    with db.sessions() as session:
        row = session.execute(select(m.generated_artifacts).where(m.generated_artifacts.c.id == job['id'])).mappings().one()
        assert row['generation_status'] != 'READY'
        assert row['storage_key'] is None
    assert service.load_revision(str(job['project_id']), revision['revision_id'])['cem'] == revision['cem']


def test_crash_after_blob_retry_accepts_exactly_once(postgres_database, api):
    db = postgres_database
    api.app.state.cad_executor.shutdown()
    service, runner, old, file, revision = queued(db, api)
    # Simulate a crash after content creation: no metadata was attached.
    assert service.load_revision(str(old['project_id']), revision['revision_id'])['pdm'] == revision['pdm']
    with db.sessions.begin() as session:
        session.execute(update(m.jobs).where(m.jobs.c.id == old['id']).values(
            lease_expires_at=func.clock_timestamp() - timedelta(seconds=1)))
    new = runner.claim()
    assert new['id'] == old['id'] and new['lease_token'] != old['lease_token']
    with pytest.raises(PersistenceError):
        runner.complete(old, file)
    assert runner.complete(new, file) is True
    with pytest.raises(PersistenceError):
        runner.complete(new, file)
    retry = service.queue_artifact(str(old['project_id']), 'GLB', revision['lock_version'])
    assert retry['id'] == str(old['id']) and retry['status'] == 'READY'
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(m.generated_artifacts).where(
            m.generated_artifacts.c.id == old['id'], m.generated_artifacts.c.generation_status == 'READY')) == 1
        assert JobRepository(session).get(old['id'])['state'] == 'SUCCEEDED'


@pytest.mark.parametrize('change', ['cancel', 'reclaim', 'sequence'])
def test_stage_result_is_fenced_before_success(postgres_database, api, monkeypatch, change):
    from app.jobs.runner import StageExecutor
    from app.jobs.worker import execute_stage
    from app.persistence.documents import DocumentRepository
    from app.persistence.repositories import ProjectRepository
    from app.services.document_service import DocumentService
    from app.services.recompute import materialize
    from app.services.stages.cache import make_signature
    db = postgres_database
    key = create(api)['id']
    source = DocumentService(db).load(key)
    base, inputs = materialize(ProjectService(db), source)
    stage_signature = make_signature('requirements', inputs.requirements, base.document.pins,
                                     context=inputs.requirements.context)

    def finish_after_change(call, name, value, **kwargs):
        output = execute_stage(name, value)
        with db.sessions.begin() as session:
            repo = JobRepository(session)
            job = session.execute(select(m.jobs).where(
                m.jobs.c.document_id == source.document.document_id)).mappings().one()
            if change == 'cancel':
                repo.cancel(job['id'])
            elif change == 'reclaim':
                session.execute(update(m.jobs).where(m.jobs.c.id == job['id']).values(
                    lease_expires_at=func.clock_timestamp() - timedelta(seconds=1)))
                repo.recover_expired(kinds=['STAGE'])
                assert repo.claim('replacement', job_id=job['id'])['lease_token'] != job['lease_token']
            else:
                current = DocumentRepository(session).load(ProjectRepository(session).row(key))
                current.document.document_sequence += 1
                DocumentRepository(session).store(current)
        return output

    monkeypatch.setattr('app.jobs.runner.run_bounded', finish_after_change)
    with pytest.raises((PersistenceError, WorkerFailure)):
        StageExecutor(db, source)('requirements', inputs.requirements, stage_signature)
    with db.sessions() as session:
        assert session.scalar(select(func.count()).select_from(m.jobs).where(
            m.jobs.c.document_id == source.document.document_id, m.jobs.c.state == 'SUCCEEDED')) == 0
        assert session.scalar(select(func.count()).select_from(m.project_revisions).where(
            m.project_revisions.c.project_id == identifier(key))) == 0
