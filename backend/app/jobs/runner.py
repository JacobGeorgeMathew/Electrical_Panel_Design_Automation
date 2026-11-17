"""Durable CAD queue consumer; computation and blob writes precede attachment.

Claims/heartbeats/attachment each own a short transaction. Completion locks the
project and document, then validates the live token with the database clock.
Discarded or crash-orphaned blobs remain managed, unreferenced audit candidates;
neither retries nor failure paths delete potentially shared content.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import Event, Thread
import time
from uuid import uuid4

from sqlalchemy import select, text, update

from app.jobs.worker import Budget, WorkerFailure, export_cad, run_bounded
from app.persistence import models as m
from app.persistence.assets import AssetStore, content_hash
from app.persistence.documents import DocumentRepository, document_hash
from app.persistence.jobs import JobRepository
from app.persistence.repositories import PersistenceError, ProjectRepository

KIND = 'CAD_EXPORT'


@contextmanager
def transaction(database):
    """A held row lock must not indefinitely stall heartbeat/cancellation."""
    with database.sessions.begin() as session:
        session.execute(text("SET LOCAL lock_timeout = '1000ms'"))
        session.execute(text("SET LOCAL statement_timeout = '2000ms'"))
        yield session


def signature(inputs, intent):
    return content_hash({'inputs': inputs, 'artifact_intent': intent})


class StageExecutor:
    """Synchronous recompute adapter using durable, bounded stage attempts.

    Completion records a reusable result only. The scheduler's separate cache
    fence and explicit operation acceptance still control document validity.
    """
    def __init__(self, database, source, *, budget=None, cancelled=None, execution_scope=None):
        self.db, self.source = database, source
        self.budget = budget or Budget()
        self.owner = 'stage-' + uuid4().hex
        self.parent_cancelled = cancelled or (lambda: False)
        self.execution_scope = execution_scope or 'sync'

    def __call__(self, name, value, stage_signature):
        if self.parent_cancelled():
            raise WorkerFailure('JOB_CANCELLED')
        from app.jobs.worker import execute_stage
        from app.services.stages.cache import ADAPTERS
        doc = self.source.document
        inputs = dict(adapter=name, value=value.model_dump(mode='json'),
                      document_sha256=document_hash(doc), lock_version=doc.lock_version,
                      stage_signature=stage_signature.key)
        intent = {'stage_signature': stage_signature.key}
        digest = signature(inputs, intent)
        with transaction(self.db) as session:
            repo = JobRepository(session)
            repo.recover_expired(kinds=['STAGE'])
            job = repo.enqueue(execution_key=f'stage:{doc.document_id}:{doc.document_sequence}:{digest}:{self.execution_scope}',
                project_id=doc.project_id, document_id=doc.document_id,
                base_sequence=doc.document_sequence, kind='STAGE', input_signature=digest,
                inputs=inputs, artifact_intent=intent)
            if job['state'] == 'SUCCEEDED':
                if (job['result'].get('output_sha256') != content_hash(job['result'].get('output'))
                        or job['input_signature'] != digest):
                    raise WorkerFailure('JOB_RESULT_INTEGRITY')
                return ADAPTERS[name].outputs.model_validate(job['result']['output'])
            job = repo.claim(self.owner, job_id=job['id'], lease_seconds=30)
            if job is None:
                raise WorkerFailure('JOB_NOT_RUNNABLE')
        last_heartbeat = 0

        def cancelled():
            nonlocal last_heartbeat
            if self.parent_cancelled():
                return True
            if time.monotonic() - last_heartbeat >= .5:
                with transaction(self.db) as session:
                    repo = JobRepository(session)
                    repo.heartbeat(job['id'], self.owner, job['lease_token'], lease_seconds=30)
                    project = ProjectRepository(session).row(doc.project_id)
                    current = DocumentRepository(session).load(project)
                    if (current.document.document_sequence != doc.document_sequence
                            or document_hash(current.document) != inputs['document_sha256']
                            or project['lock_version'] != doc.lock_version):
                        return True
                last_heartbeat = time.monotonic()
            return False

        try:
            output = run_bounded(execute_stage, name, inputs['value'], budget=self.budget, cancelled=cancelled)
            typed = ADAPTERS[name].outputs.model_validate(output)
            with transaction(self.db) as session:
                project = ProjectRepository(session).row(doc.project_id, lock=True)
                session.execute(select(m.design_documents.c.id).where(
                    m.design_documents.c.id == doc.document_id).with_for_update()).one()
                current = DocumentRepository(session).load(project)
                repo = JobRepository(session)
                repo.heartbeat(job['id'], self.owner, job['lease_token'], lease_seconds=30)
                stored = repo.get(job['id'])
                if (current.document.document_sequence != doc.document_sequence
                        or project['lock_version'] != doc.lock_version
                        or document_hash(current.document) != inputs['document_sha256']
                        or stored['input_signature'] != digest
                        or signature(stored['inputs'], stored['artifact_intent']) != digest):
                    raise WorkerFailure('JOB_SUPERSEDED')
                repo.succeed(job['id'], self.owner, job['lease_token'],
                             result={'output': output, 'output_sha256': content_hash(output)})
            return typed
        except Exception as exc:
            try:
                with transaction(self.db) as session:
                    JobRepository(session).fail(job['id'], self.owner, job['lease_token'],
                        code=exc.code if isinstance(exc, WorkerFailure) else 'STAGE_FAILED')
            except PersistenceError as lost:
                if lost.code != 'JOB_LEASE_LOST':
                    raise
            raise


class JobRunner:
    def __init__(self, database, *, budget=None):
        self.db = database
        self.assets = AssetStore(database.settings.asset_root)
        self.budget = budget or Budget()
        self.owner = 'cad-' + uuid4().hex
        self.stopping = Event()
        self.thread = None

    def start(self):
        self.thread = Thread(target=self._loop, name='panel-jobs', daemon=True)
        self.thread.start()

    def shutdown(self, **kwargs):
        self.stopping.set()
        if self.thread:
            self.thread.join()

    def _loop(self):
        while not self.stopping.is_set():
            try:
                self.run_once()
            except Exception:
                # Database outages leave the durable lease recoverable. Do not
                # log driver messages, inputs, credentials or internal paths.
                pass
            self.stopping.wait(.1)

    def claim(self):
        with transaction(self.db) as session:
            repo = JobRepository(session)
            repo.recover_expired(kinds=[KIND, 'RECOMPUTE'])
            # Mirror terminal jobs for the existing ArtifactView contract.
            pending = list(session.scalars(select(m.generated_artifacts.c.id).join(
                m.jobs, m.jobs.c.id == m.generated_artifacts.c.id).where(
                    m.jobs.c.kind == KIND, m.jobs.c.state.in_(['FAILED', 'CANCELLED']),
                    m.generated_artifacts.c.generation_status == 'PENDING').limit(100)))
            if pending:
                session.execute(update(m.generated_artifacts).where(
                m.generated_artifacts.c.id.in_(pending),
                m.generated_artifacts.c.id == m.jobs.c.id,
                m.jobs.c.kind == KIND, m.jobs.c.state.in_(['FAILED', 'CANCELLED']),
                m.generated_artifacts.c.generation_status == 'PENDING').values(
                    generation_status='FAILED', error={'code': 'JOB_STOPPED',
                        'message': 'Export stopped before completion.'},
                    completed_at=datetime.now(timezone.utc)))
            return repo.claim(self.owner, lease_seconds=30, kinds=[KIND, 'RECOMPUTE'])

    def run_once(self):
        job = self.claim()
        if job is None:
            return None
        if job['kind'] == 'RECOMPUTE':
            return self.recompute(job)
        last_heartbeat = 0

        def cancelled():
            nonlocal last_heartbeat
            if self.stopping.is_set():
                return True
            if time.monotonic() - last_heartbeat >= .5:
                with transaction(self.db) as session:
                    JobRepository(session).heartbeat(job['id'], self.owner,
                        job['lease_token'], lease_seconds=30)
                last_heartbeat = time.monotonic()
            return False

        try:
            if signature(job['inputs'], job['artifact_intent']) != job['input_signature']:
                raise WorkerFailure('JOB_INPUT_MISMATCH')
            data = run_bounded(export_cad, job['inputs'], budget=self.budget, cancelled=cancelled)
            file = self.assets.put(data, job['inputs']['format'].lower())
            return self.complete(job, file)
        except Exception as exc:
            code = exc.code if isinstance(exc, WorkerFailure) else 'WORKER_FAILED'
            try:
                self.fail(job, code)
            except PersistenceError as lost:
                if lost.code != 'JOB_LEASE_LOST':
                    raise
            return None

    def recompute(self, job):
        """Retain a review candidate only; never apply/publish on completion."""
        from app.models.recompute import RecomputeRequest, RecomputeResponse
        from app.services.project_service import ProjectService
        from app.services.recompute import recompute, check_base
        stopped, lost = Event(), Event()

        def heartbeat():
            while not stopped.wait(.5):
                try:
                    with transaction(self.db) as session:
                        JobRepository(session).heartbeat(job['id'], self.owner, job['lease_token'], lease_seconds=30)
                except Exception:
                    lost.set()
                    return

        def cancelled():
            return lost.is_set() or self.stopping.is_set()

        def progress(stage, records):
            if cancelled():
                raise WorkerFailure('JOB_CANCELLED')

        thread = Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            if signature(job['inputs'], job['artifact_intent']) != job['input_signature']:
                raise WorkerFailure('JOB_INPUT_MISMATCH')
            request = RecomputeRequest.model_validate(job['inputs']['request'])
            with transaction(self.db) as session:
                source = DocumentRepository(session).load(ProjectRepository(session).row(str(job['project_id'])))
                check_base(source, request)
                if document_hash(source.document) != job['inputs']['document_sha256']:
                    raise WorkerFailure('JOB_SUPERSEDED')
            response = recompute(ProjectService(self.db), str(job['project_id']), request,
                progress=progress, cancelled=cancelled,
                execution_scope=f'{job["id"]}:{job["attempts"]}')
            response = RecomputeResponse.model_validate(response).model_dump(mode='json')
            if cancelled():
                raise WorkerFailure('JOB_CANCELLED')
            with transaction(self.db) as session:
                project = ProjectRepository(session).row(str(job['project_id']), lock=True)
                session.execute(select(m.design_documents.c.id).where(
                    m.design_documents.c.id == job['document_id']).with_for_update()).one()
                source = DocumentRepository(session).load(project)
                check_base(source, request)
                if document_hash(source.document) != job['inputs']['document_sha256']:
                    raise WorkerFailure('JOB_SUPERSEDED')
                return JobRepository(session).succeed(job['id'], self.owner, job['lease_token'],
                    result={'current_stage': None, 'stage_executions': response['stage_executions'],
                        'response': response})
        except Exception as exc:
            try:
                with transaction(self.db) as session:
                    JobRepository(session).fail(job['id'], self.owner, job['lease_token'],
                        code=getattr(exc, 'code', 'RECOMPUTE_FAILED'))
            except PersistenceError as error:
                if error.code != 'JOB_LEASE_LOST':
                    raise
            return None
        finally:
            stopped.set()
            thread.join()

    def fail(self, job, code):
        with transaction(self.db) as session:
            JobRepository(session).fail(job['id'], self.owner, job['lease_token'], code=code)
            session.execute(update(m.generated_artifacts).where(
                m.generated_artifacts.c.id == job['id'],
                m.generated_artifacts.c.generation_status == 'PENDING').values(
                    generation_status='FAILED', completed_at=datetime.now(timezone.utc),
                    error={'code': code, 'message': 'Export did not complete.'}))

    def complete(self, job, file):
        # File integrity is checked before opening the publication transaction.
        self.assets.verified_path(file['storage_key'], file['sha256'], file['byte_size'])
        with transaction(self.db) as session:
            project = session.execute(select(m.projects).where(
                m.projects.c.id == job['project_id']).with_for_update()).mappings().one()
            session.execute(select(m.design_documents.c.id).where(
                m.design_documents.c.id == job['document_id']).with_for_update()).one()
            repo = JobRepository(session)
            # Acquire the job lock and recheck the deadline after waiting.
            repo.heartbeat(job['id'], self.owner, job['lease_token'], lease_seconds=30)
            stored = repo.get(job['id'])
            current = DocumentRepository(session).load(project)
            valid = (project['deleted_at'] is None
                and project['current_revision_id'] == job['revision_id']
                and current.document.document_sequence == job['base_sequence']
                and document_hash(current.document) == job['inputs']['document_sha256']
                and project['lock_version'] == job['inputs']['lock_version']
                and signature(job['inputs'], job['artifact_intent']) == job['input_signature']
                and stored['input_signature'] == job['input_signature']
                and signature(stored['inputs'], stored['artifact_intent']) == job['input_signature'])
            if not valid:
                repo.fail(job['id'], self.owner, job['lease_token'], code='JOB_SUPERSEDED')
                session.execute(update(m.generated_artifacts).where(
                    m.generated_artifacts.c.id == job['id'],
                    m.generated_artifacts.c.generation_status == 'PENDING').values(
                        generation_status='FAILED', completed_at=datetime.now(timezone.utc),
                        error={'code': 'JOB_SUPERSEDED', 'message': 'Export base changed.'}))
                return False
            attached = session.execute(update(m.generated_artifacts).where(
                m.generated_artifacts.c.id == job['id'],
                m.generated_artifacts.c.project_revision_id == job['revision_id'],
                m.generated_artifacts.c.generation_status == 'PENDING').values(
                    **file, generation_status='READY', completed_at=datetime.now(timezone.utc)))
            if attached.rowcount != 1:
                raise PersistenceError('JOB_ATTACHMENT_CONFLICT', 'Export attachment changed.', 409)
            repo.succeed(job['id'], self.owner, job['lease_token'],
                         result={'artifact_id': str(job['id']), 'sha256': file['sha256']})
            return True
