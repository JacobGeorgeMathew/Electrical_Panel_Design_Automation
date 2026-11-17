"""Async transport and durable result fencing on isolated PostgreSQL."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.jobs.runner import JobRunner
from app.persistence import models as m
from app.persistence.jobs import JobRepository
from app.persistence.repositories import identifier
from app.services.document_service import DocumentService
from tests.test_postgres import create, checked
from tests.test_recompute_api import request_for


def enqueue(api, db):
    api.app.state.cad_executor.shutdown()
    project = create(api)
    key = project['id']
    base = DocumentService(db).load(key)
    path = f'/api/projects/{key}/design/recompute/jobs'
    headers = {'Idempotency-Key': str(uuid4())}
    response = checked(api.post(path, json=request_for(base), headers=headers), 202)
    return key, base, path, headers, response


def test_submit_poll_retry_cancel_scope_and_cors(api, postgres_database):
    key, base, path, headers, job = enqueue(api, postgres_database)
    assert job['state'] == 'QUEUED' and job['attempts'] == 0
    assert DocumentService(postgres_database).load(key) == base
    assert checked(api.post(path, json=request_for(base), headers=headers), 202)['id'] == job['id']
    assert checked(api.get(path))[0]['id'] == job['id']
    assert checked(api.get(path+'/'+job['id'])) == job
    assert {'inputs', 'lease_token', 'lease_owner', 'execution_key'}.isdisjoint(job)
    changed = dict(request_for(base), expected_document_sequence=999)
    assert api.post(path, json=changed, headers=headers).status_code == 409
    assert api.post(path, json=changed, headers={'Idempotency-Key': 'stale'}).status_code == 409
    other = create(api)['id']
    foreign = f'/api/projects/{other}/design/recompute/jobs/{job["id"]}'
    assert api.get(foreign).status_code == 404
    assert api.post(foreign+'/cancel').status_code == 404
    cancelled = checked(api.post(path+'/'+job['id']+'/cancel'))
    assert cancelled['state'] == 'CANCELLED'
    assert checked(api.post(path+'/'+job['id']+'/cancel')) == cancelled
    assert checked(api.post(path, json=request_for(base), headers=headers), 202)['state'] == 'CANCELLED'
    retry = checked(api.post(path, json=request_for(base), headers={'Idempotency-Key': 'fresh-retry'}), 202)
    assert retry['id'] != job['id'] and retry['state'] == 'QUEUED'
    checked(api.post(path+'/'+retry['id']+'/cancel'))
    preflight = api.options(path, headers={'Origin': 'http://localhost:3000',
        'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Content-Type,Idempotency-Key'})
    assert preflight.status_code == 200


def test_worker_completion_is_review_only_and_reopens_after_runner_restart(api, postgres_database):
    db = postgres_database
    key, base, path, headers, job = enqueue(api, db)
    # New runner sees the persisted queue; HTTP submit performed no computation.
    runner = JobRunner(db)
    runner.run_once()
    status = checked(api.get(path+'/'+job['id']))
    assert status['state'] == 'SUCCEEDED', status
    response = status['result']['response']
    assert response['status'] == 'REVIEW_REQUIRED'
    assert {r['stage_id'] for r in status['result']['stage_executions']} == set(response['scheduled_stages'])
    assert DocumentService(db).load(key) == base
    assert checked(api.get(path))[0] == status
    receipt = checked(api.post(f'/api/projects/{key}/design/generation-proposal/accept',
        json=response['batch'], headers={'Idempotency-Key': 'reviewed-job'}))
    assert receipt['document_sequence'] == base.document.document_sequence + 1
    # Lost acknowledgement still resolves to the original completed job after edits.
    assert checked(api.post(path, json=request_for(base), headers=headers), 202)['id'] == job['id']
    assert api.post(path, json=request_for(base), headers={'Idempotency-Key': 'old-base'}).status_code == 409
    assert checked(api.get(f'/api/projects/{key}/revisions')) == []


@pytest.mark.parametrize('change', ['cancel', 'sequence', 'lease'])
def test_recompute_completion_does_not_attach_after_base_or_lease_changes(api, postgres_database, monkeypatch, change):
    db = postgres_database
    key, base, path, _, job = enqueue(api, db)
    # Fault injection returns a valid transport result only after revoking the
    # parent lease or document base. No engineering stage or snapshot is forged.
    def supersede(*args, **kwargs):
        with db.sessions.begin() as session:
            if change == 'cancel':
                JobRepository(session).cancel(job['id'])
            elif change == 'lease':
                session.execute(update(m.jobs).where(m.jobs.c.id == identifier(job['id'])).values(
                    lease_expires_at=func.clock_timestamp()-timedelta(seconds=1)))
            else:
                project = session.execute(select(m.projects).where(m.projects.c.id == identifier(key))).mappings().one()
                from app.persistence.documents import DocumentRepository
                source = DocumentRepository(session).load(project)
                source.document.document_sequence += 1
                DocumentRepository(session).store(source)
        return dict(status='CONFLICT', persisted=False, conflicts=[], batch=None, preview=None,
                    scheduled_stages=[], stage_executions=[])
    monkeypatch.setattr('app.services.recompute.recompute', supersede)
    JobRunner(db).run_once()
    status = checked(api.get(path+'/'+job['id']))
    assert status['state'] != 'SUCCEEDED'
    assert not status['result'].get('response')
    current = DocumentService(db).load(key)
    assert current.snapshots == base.snapshots
    assert checked(api.get(f'/api/projects/{key}/revisions')) == []


def test_live_stage_progress_and_failure_are_scoped_to_the_parent_attempt(api, postgres_database, monkeypatch):
    from app.jobs.worker import WorkerFailure
    db = postgres_database
    key, base, path, _, job = enqueue(api, db)
    def fail_stage(call, name, value, **kwargs):
        status = checked(api.get(path+'/'+job['id']))
        assert status['state'] == 'RUNNING'
        assert status['result']['current_stage'] == name
        raise WorkerFailure('WORKER_TIMEOUT')
    monkeypatch.setattr('app.jobs.runner.run_bounded', fail_stage)
    JobRunner(db).run_once()
    status = checked(api.get(path+'/'+job['id']))
    assert status['state'] == 'FAILED'
    assert status['error']['code'] == 'WORKER_TIMEOUT'
    assert status['result']['stage_executions'][0]['failure_code'] == 'WORKER_TIMEOUT'
    assert DocumentService(db).load(key) == base


def test_cancel_running_parent_revokes_its_stage_lease(api, postgres_database, monkeypatch):
    from app.jobs.worker import WorkerFailure
    db = postgres_database
    key, base, path, _, job = enqueue(api, db)
    def cancel_during_stage(call, name, value, **kwargs):
        status = checked(api.post(path+'/'+job['id']+'/cancel'))
        assert status['state'] == 'CANCELLED'
        with db.sessions() as session:
            stage = session.execute(select(m.jobs).where(m.jobs.c.document_id == base.document.document_id,
                m.jobs.c.kind == 'STAGE')).mappings().one()
            assert stage['state'] == 'CANCELLED' and stage['lease_token'] is None
        raise WorkerFailure('JOB_CANCELLED')
    monkeypatch.setattr('app.jobs.runner.run_bounded', cancel_during_stage)
    JobRunner(db).run_once()
    assert checked(api.get(path+'/'+job['id']))['state'] == 'CANCELLED'
    assert DocumentService(db).load(key) == base
