"""Process death after committed claim, recovery isolation and late results."""
import multiprocessing
import os
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.jobs.runner import JobRunner
from app.persistence import models as m
from app.persistence.database import Database
from app.persistence.jobs import JobRepository
from app.persistence.repositories import PersistenceError
from tests.test_design_document_storage import row_images
from tests.test_job_worker import queued
from tests.test_jobs import expire


def claim_then_die(settings, job_id, channel):
    """A fresh process commits a claim and dies without runner cleanup."""
    db = Database(settings)
    with db.sessions.begin() as session:
        job = JobRepository(session).claim('crashed-process', job_id=job_id, lease_seconds=3600)
    channel.send(job)
    channel.close()
    os._exit(23)


def job_row(db, job_id):
    with db.sessions() as session:
        return JobRepository(session).get(job_id)


@pytest.fixture
def cleanup_jobs(postgres_database):
    owned = []
    yield owned
    with postgres_database.sessions.begin() as session:
        for job_id in owned:
            JobRepository(session).cancel(job_id)


def healthy_sibling(db, source):
    with db.sessions.begin() as session:
        repo = JobRepository(session)
        queued_job = repo.enqueue(execution_key=uuid4().hex, project_id=source['project_id'],
            document_id=source['document_id'], base_sequence=source['base_sequence'],
            revision_id=source['revision_id'], kind=source['kind'],
            inputs=source['inputs'], input_signature=source['input_signature'],
            artifact_intent=source['artifact_intent'])
        return repo.claim('healthy-worker', job_id=queued_job['id'], lease_seconds=3600)


def test_process_crash_after_claim_restarts_without_harming_live_jobs(api, postgres_database, cleanup_jobs):
    db = postgres_database
    api.app.state.cad_executor.shutdown()
    service, _, old, file, revision = queued(db, api)
    # Return the helper's controlled first lease to QUEUED before the real crash.
    expire(db, old)
    with db.sessions.begin() as session:
        JobRepository(session).recover_expired(kinds=[old['kind']])
    sibling = healthy_sibling(db, old)
    cleanup_jobs.extend([old['id'], sibling['id']])
    preserved = row_images(db.engine, {'project_revisions', 'revision_output_snapshots',
        'revision_output_manifests', 'cem_snapshots', 'pdm_snapshots'})
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=claim_then_die, args=(db.settings, old['id'], sender))
    process.start()
    sender.close()
    try:
        assert receiver.poll(20), 'Child failed to acknowledge committed claim'
        crashed = receiver.recv()
        process.join(20)
        assert process.exitcode == 23
    finally:
        if process.is_alive():
            process.kill()
            process.join(10)
        receiver.close()
    assert crashed['state'] == 'RUNNING' and crashed['attempts'] == 2
    # A replacement runner must leave unexpired work and healthy peers alone.
    replacement = JobRunner(db)
    assert replacement.claim() is None
    assert job_row(db, crashed['id']) == crashed
    assert job_row(db, sibling['id']) == sibling
    expire(db, crashed)
    retry = replacement.claim()
    assert retry['id'] == crashed['id'] and retry['attempts'] == 3
    assert retry['lease_token'] != crashed['lease_token']
    dead_runner = JobRunner(db)
    dead_runner.owner = 'crashed-process'
    with pytest.raises(PersistenceError) as caught:
        dead_runner.complete(crashed, file)
    assert caught.value.code == 'JOB_LEASE_LOST'
    assert replacement.complete(retry, file) is True
    with pytest.raises(PersistenceError):
        replacement.complete(retry, file)
    assert job_row(db, sibling['id']) == sibling
    assert row_images(db.engine, preserved.keys()) == preserved
    reopened = service.load_revision(str(old['project_id']), revision['revision_id'])
    assert reopened['cem'] == revision['cem'] and reopened['pdm'] == revision['pdm']


@pytest.mark.parametrize('failure', ['cancelled', 'expired', 'exhausted'])
def test_late_completion_preserves_published_revision_and_healthy_peer(api, postgres_database, cleanup_jobs, failure):
    db = postgres_database
    api.app.state.cad_executor.shutdown()
    service, runner, job, file, revision = queued(db, api)
    sibling = healthy_sibling(db, job)
    cleanup_jobs.extend([job['id'], sibling['id']])
    preserved = row_images(db.engine, {'project_revisions', 'revision_output_snapshots',
        'revision_output_manifests', 'cem_snapshots', 'pdm_snapshots'})
    if failure == 'cancelled':
        with db.sessions.begin() as session:
            terminal = JobRepository(session).cancel(job['id'])
    else:
        if failure == 'exhausted':
            for _ in range(job['max_attempts'] - 1):
                expire(db, job)
                job = runner.claim()
        expire(db, job)
        if failure == 'exhausted':
            assert runner.claim() is None
            terminal = job_row(db, job['id'])
            assert terminal['state'] == 'FAILED'
            assert terminal['error']['code'] == 'JOB_ATTEMPTS_EXHAUSTED'
    with pytest.raises(PersistenceError) as caught:
        runner.complete(job, file)
    assert caught.value.code == 'JOB_LEASE_LOST'
    if failure != 'expired':
        assert job_row(db, job['id']) == terminal
    with db.sessions() as session:
        artifact = session.execute(select(m.generated_artifacts).where(
            m.generated_artifacts.c.id == job['id'])).mappings().one()
        assert artifact['generation_status'] != 'READY' and artifact['storage_key'] is None
    assert job_row(db, sibling['id']) == sibling
    assert row_images(db.engine, preserved.keys()) == preserved
    reopened = service.load_revision(str(job['project_id']), revision['revision_id'])
    assert reopened['cem'] == revision['cem'] and reopened['pdm'] == revision['pdm']
