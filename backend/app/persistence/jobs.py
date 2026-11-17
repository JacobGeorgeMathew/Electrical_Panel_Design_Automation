"""Durable queue storage; callers own short transactions, never execute work here.

Commit a claim before executing outside the transaction. Every claim receives a
fresh token, even if the same owner reclaims the job. Renewal and completion
require that token and an unexpired lease, using PostgreSQL's clock. Completion
only records a job outcome; document/revision/artifact publication is a separate
runner responsibility and must share its own result fences and transaction.
"""
from copy import deepcopy
from datetime import timedelta
import re
from uuid import uuid4

from sqlalchemy import func, null, select, update
from sqlalchemy.dialects.postgresql import insert

from app.persistence import models as m
from app.persistence.repositories import PersistenceError, identifier


class JobRepository:
    def __init__(self, session):
        self.s = session

    def get(self, job_id):
        row = self.s.execute(select(m.jobs).where(m.jobs.c.id == identifier(job_id))).mappings().first()
        if row is None:
            raise PersistenceError('JOB_NOT_FOUND', 'Job was not found.', 404)
        return deepcopy(dict(row))

    def enqueue(self, *, execution_key, project_id, document_id, base_sequence,
                kind, input_signature, inputs, artifact_intent, revision_id=None,
                max_attempts=3):
        """Idempotent by execution key, including after completion or cancellation.

        A key cannot be reused for changed intent. No current-document mutation
        occurs; the base sequence and inputs are frozen evidence for the runner.
        """
        if (not isinstance(execution_key, str) or not execution_key.strip()
                or not isinstance(kind, str) or not kind.strip()
                or not isinstance(document_id, str) or not document_id.strip()
                or type(base_sequence) is not int or base_sequence < 0
                or type(max_attempts) is not int or not 1 <= max_attempts <= 100
                or not isinstance(input_signature, str)
                or not re.fullmatch(r'[0-9a-f]{64}', input_signature)
                or not isinstance(inputs, dict) or not isinstance(artifact_intent, dict)
                or identifier(project_id) is None
                or (revision_id is not None and identifier(revision_id) is None)):
            raise PersistenceError('INVALID_JOB', 'Job intent or retry limit is invalid.')
        intent = deepcopy(dict(execution_key=execution_key, project_id=identifier(project_id),
            document_id=document_id, base_sequence=base_sequence, kind=kind,
            input_signature=input_signature, inputs=inputs, artifact_intent=artifact_intent,
            revision_id=identifier(revision_id), max_attempts=max_attempts))
        self.s.execute(insert(m.jobs).values(id=uuid4(), **intent).on_conflict_do_nothing(
            index_elements=[m.jobs.c.execution_key]))
        row = dict(self.s.execute(select(m.jobs).where(
            m.jobs.c.execution_key == execution_key)).mappings().one())
        if any(row[key] != value for key, value in intent.items()):
            raise PersistenceError('JOB_EXECUTION_CONFLICT',
                'This execution key already identifies different job intent.', 409)
        return deepcopy(row)

    @staticmethod
    def _duration(lease_seconds):
        if type(lease_seconds) is not int or not 1 <= lease_seconds <= 86400:
            raise PersistenceError('INVALID_JOB_LEASE', 'Lease duration must be 1 to 86400 seconds.')
        return timedelta(seconds=lease_seconds)

    def claim(self, owner, *, lease_seconds=60, kinds=None):
        """Claim one queued job without waiting for another worker's row locks.

        Expired RUNNING jobs require explicit recover_expired(), which a runner
        can periodically call. Restart alone never invalidates a healthy lease.
        """
        duration = self._duration(lease_seconds)
        if not isinstance(owner, str) or not owner.strip():
            raise PersistenceError('INVALID_JOB_LEASE', 'A lease owner is required.')
        query = select(m.jobs.c.id).where(m.jobs.c.state == 'QUEUED',
            m.jobs.c.attempts < m.jobs.c.max_attempts)
        if kinds is not None:
            query = query.where(m.jobs.c.kind.in_(kinds))
        job_id = self.s.scalar(query.order_by(m.jobs.c.created_at, m.jobs.c.id)
            .limit(1).with_for_update(skip_locked=True))
        if job_id is None:
            return None
        row = self.s.execute(update(m.jobs).where(m.jobs.c.id == job_id).values(
            state='RUNNING', attempts=m.jobs.c.attempts + 1, lease_owner=owner,
            lease_token=uuid4(), lease_expires_at=func.clock_timestamp() + duration,
            started_at=func.coalesce(m.jobs.c.started_at, func.clock_timestamp()),
            updated_at=func.clock_timestamp()).returning(m.jobs)).mappings().one()
        return deepcopy(dict(row))

    @staticmethod
    def _lease(job_id, owner, token):
        return (m.jobs.c.id == identifier(job_id), m.jobs.c.state == 'RUNNING',
                m.jobs.c.lease_owner == owner, m.jobs.c.lease_token == identifier(token),
                m.jobs.c.lease_expires_at > func.clock_timestamp())

    def _leased_update(self, job_id, owner, token, **values):
        # Evaluate the deadline after acquiring the lock. An UPDATE that waits on
        # an unchanged, locked tuple can otherwise use its pre-wait predicate.
        self.s.execute(select(m.jobs.c.id).where(m.jobs.c.id == identifier(job_id)).with_for_update())
        row = self.s.execute(update(m.jobs).where(*self._lease(job_id, owner, token))
            .values(updated_at=func.clock_timestamp(), **values).returning(m.jobs)).mappings().first()
        if row is None:
            raise PersistenceError('JOB_LEASE_LOST', 'Job lease is no longer active for this execution.', 409)
        return deepcopy(dict(row))

    def heartbeat(self, job_id, owner, token, *, lease_seconds=60):
        duration = self._duration(lease_seconds)
        return self._leased_update(job_id, owner, token,
            lease_expires_at=func.greatest(m.jobs.c.lease_expires_at, func.clock_timestamp() + duration))

    def succeed(self, job_id, owner, token, *, result):
        if not isinstance(result, dict):
            raise PersistenceError('INVALID_JOB_RESULT', 'Job result must be an object.')
        return self._leased_update(job_id, owner, token, state='SUCCEEDED', result=deepcopy(result),
            lease_owner=None, lease_token=None, lease_expires_at=None, completed_at=func.clock_timestamp())

    def fail(self, job_id, owner, token, *, code='JOB_FAILED'):
        # Public records store controlled codes, never worker exception text/paths.
        if not isinstance(code, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', code):
            raise PersistenceError('INVALID_JOB_ERROR', 'Job failure requires a structured error code.')
        return self._leased_update(job_id, owner, token, state='FAILED',
            error={'code': code, 'message': 'Job execution failed.'}, lease_owner=None,
            lease_token=None, lease_expires_at=None, completed_at=func.clock_timestamp())

    def cancel(self, job_id):
        """Persist cancellation and revoke any running token; terminal jobs stay terminal."""
        row = self.s.execute(update(m.jobs).where(m.jobs.c.id == identifier(job_id),
            m.jobs.c.state.in_(['QUEUED', 'RUNNING'])).values(state='CANCELLED',
            lease_owner=None, lease_token=None, lease_expires_at=None,
            updated_at=func.clock_timestamp(), completed_at=func.clock_timestamp())
            .returning(m.jobs)).mappings().first()
        return deepcopy(dict(row)) if row else self.get(job_id)

    def recover_expired(self, *, limit=100):
        """Requeue expired attempts, or fail exhausted ones, in a bounded batch.

        Concurrent recoverers skip locked rows. The token is cleared before any
        retry can be claimed, so a late worker can never complete another attempt.
        Queued jobs, healthy leases and all terminal states are untouched.
        """
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise PersistenceError('INVALID_JOB_RECOVERY', 'Recovery limit must be 1 to 1000 jobs.')
        expired = self.s.execute(select(m.jobs).where(m.jobs.c.state == 'RUNNING',
            m.jobs.c.lease_expires_at <= func.clock_timestamp())
            .order_by(m.jobs.c.lease_expires_at, m.jobs.c.id).limit(limit)
            .with_for_update(skip_locked=True)).mappings().all()
        recovered = []
        for row in expired:
            exhausted = row['attempts'] >= row['max_attempts']
            result = self.s.execute(update(m.jobs).where(m.jobs.c.id == row['id']).values(
                state='FAILED' if exhausted else 'QUEUED', lease_owner=None, lease_token=None,
                lease_expires_at=None, updated_at=func.clock_timestamp(),
                completed_at=func.clock_timestamp() if exhausted else None,
                error={'code': 'JOB_ATTEMPTS_EXHAUSTED', 'message': 'Job lease expired at the retry limit.'}
                    if exhausted else null()).returning(m.jobs)).mappings().one()
            recovered.append(deepcopy(dict(result)))
        return recovered
