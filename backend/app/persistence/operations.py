"""Atomic draft-operation storage; no HTTP apply or engineering approval boundary.

The existing allowlist validates detached candidates before the write transaction.
Engineering checks remain unresolved and derived outputs dirty. Future operation
handlers must enforce their own engineering constraints before this writer runs.
"""
from dataclasses import dataclass

from pydantic import TypeAdapter
from sqlalchemy import func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.models.document import DocumentProvenance, ResolvedDocument
from app.models.document_api import DocumentView
from app.models.identity import StableID
from app.models.operations import OperationPreviewRequest
from app.persistence import models as m
from app.persistence.assets import content_hash
from app.persistence.documents import DocumentRepository, document_hash
from app.persistence.repositories import PersistenceError, ProjectRepository
from app.services.operations.registry import REGISTRY, preview_operations
from app.services.operations.engineering import load_choices
from app.persistence.assets import AssetStore


@dataclass(frozen=True)
class _PreparedBatch:
    before: dict
    after: DocumentView
    members: tuple[dict, ...]
    snapshots: tuple[dict, ...]
    required_checks: tuple[dict, ...]
    changed: bool


def _prepare(base, request, choices=None):
    """Materialize canonical values without a database transaction or file I/O."""
    candidate = ResolvedDocument.model_validate(base.model_dump(mode='json', include={'document', 'snapshots'}))
    before = candidate.document.model_dump(mode='json')
    members, snapshots, checks = [], [], []
    changed = False
    last_changed = None
    for index, operation in enumerate(request.operations):
        # A previewed proposal is never evidence of human acceptance. Acceptance
        # and authoritative physical/engineering handlers belong to later tasks.
        if operation.proposal_status == 'PROPOSED':
            raise PersistenceError('OPERATION_PROPOSAL_REQUIRES_ACCEPTANCE',
                'Proposed operations require a separate explicit acceptance workflow.', 409)
        model = REGISTRY[operation.type].model
        before_ref = getattr(candidate.document.models, model)
        single = request.model_copy(update={'operations': [operation]})
        preview = preview_operations(candidate, single, choices)
        candidate = preview.candidate
        after_ref = getattr(candidate.document.models, model)
        payload = operation.model_dump(mode='json')
        members.append(dict(operation_id=operation.operation_id, batch_index=index,
            operation_type=operation.type, origin=payload['origin'], payload=payload,
            payload_sha256=content_hash(payload), model_kind=model.upper(),
            schema_version=after_ref.schema_version,
            before_sha256=before_ref.sha256, after_sha256=after_ref.sha256))
        snapshots.append(dict(document_id=candidate.document.document_id, model_kind=model.upper(),
            schema_version=after_ref.schema_version, sha256=after_ref.sha256,
            snapshot=getattr(candidate.snapshots, model).model_dump(mode='json')))
        for check in preview.required_checks:
            value = check.model_dump(mode='json')
            if value not in checks:
                checks.append(value)
        if preview.changes:
            changed = True
            last_changed = operation
    if changed:
        doc = candidate.document
        doc.document_sequence += 1
        doc.lock_version += 1
        doc.provenance = DocumentProvenance(origin=last_changed.origin.kind,
            actor_id=last_changed.origin.actor_id, last_operation_id=str(last_changed.operation_id),
            job_id=last_changed.origin.job_id)
    after = DocumentView(**candidate.model_dump(mode='json'),
                         content_sha256=document_hash(candidate.document))
    return _PreparedBatch(before, after, tuple(members), tuple(snapshots), tuple(checks), changed)


class OperationBatchRepository:
    """Own transaction boundaries so failed members cannot leave partial history.

    Call with a server request, never a client-supplied candidate/preview. Replay
    is checked before base validation and again under the project row lock. The
    stored JSON receipt is returned verbatim, even after subsequent document edits.
    """
    def __init__(self, database):
        self.db = database

    @staticmethod
    def _replay(session, project_id, key, payload_hash):
        row = session.execute(select(m.operation_batches).where(
            m.operation_batches.c.project_id == project_id,
            m.operation_batches.c.idempotency_key == key)).mappings().first()
        if row is None:
            return None
        if row['payload_sha256'] != payload_hash:
            raise PersistenceError('IDEMPOTENCY_CONFLICT',
                'This idempotency key was already used for different batch content.', 409)
        if (content_hash(row['payload']) != row['payload_sha256']
                or content_hash(row['result']) != row['result_sha256']):
            raise PersistenceError('OPERATION_RECEIPT_INTEGRITY',
                'Stored operation receipt failed integrity verification.', 409)
        return row['result']

    def commit(self, key, request: OperationPreviewRequest, idempotency_key: str):
        request = OperationPreviewRequest.model_validate(request.model_dump(mode='json'))
        idempotency_key = TypeAdapter(StableID).validate_python(idempotency_key)
        if len(idempotency_key) > 200:
            raise PersistenceError('IDEMPOTENCY_KEY', 'Idempotency keys must have at most 200 characters.')
        payload = request.model_dump(mode='json')
        payload_hash = content_hash(payload)
        with self.db.sessions() as session:
            project = ProjectRepository(session).row(key)
            replay = self._replay(session, project['id'], idempotency_key, payload_hash)
            if replay is not None:
                return replay
            base = DocumentRepository(session).load(project)
            # Under READ COMMITTED another batch can commit between the project
            # and document reads. Its receipt is now visible before validation.
            replay = self._replay(session, project['id'], idempotency_key, payload_hash)
            if replay is not None:
                return replay
            choices = load_choices(session, AssetStore(self.db.settings.asset_root), base, request,
                                   project['archetype_version_id'])
        # All operation validation and canonical serialization occur after the
        # read session closes. Nothing expensive runs under the project lock.
        prepared = _prepare(base, request, choices)
        try:
            with self.db.sessions.begin() as session:
                projects = ProjectRepository(session)
                project = projects.row(key, lock=True)
                replay = self._replay(session, project['id'], idempotency_key, payload_hash)
                if replay is not None:
                    return replay
                saved = session.execute(select(m.design_documents).where(
                    m.design_documents.c.project_id == project['id'])).mappings().one()
                before = prepared.before
                if (project['lock_version'] != request.expected_version
                        or saved['id'] != request.document_id
                        or saved['document_sequence'] != request.base_sequence
                        or (str(saved['base_revision_id']) if saved['base_revision_id'] else None) != request.base_revision_id
                        or saved['content_sha256'] != document_hash(base.document)):
                    raise PersistenceError('DOCUMENT_CONFLICT',
                        'Operation base changed. Retain edits and reload for comparison.', 409)
                first_sequence = (session.scalar(select(func.max(m.document_operations.c.sequence)).where(
                    m.document_operations.c.project_id == project['id'])) or 0) + 1
                after = prepared.after
                result = dict(schema_version='1.0.0', status='COMMITTED', persisted=True,
                    batch_id=str(request.batch_id), idempotency_key=idempotency_key,
                    payload_sha256=payload_hash, base_sequence=request.base_sequence,
                    document_sequence=after.document.document_sequence,
                    lock_version=after.document.lock_version,
                    first_operation_sequence=first_sequence,
                    last_operation_sequence=first_sequence + len(prepared.members) - 1,
                    before_content_sha256=document_hash(base.document),
                    after_content_sha256=after.content_sha256,
                    required_checks=list(prepared.required_checks), result=after.model_dump(mode='json'))
                session.execute(insert(m.operation_batches).values(project_id=project['id'],
                    id=request.batch_id, document_id=request.document_id, schema_version=request.schema_version,
                    idempotency_key=idempotency_key, payload=payload, payload_sha256=payload_hash,
                    base_sequence=request.base_sequence, document_sequence=after.document.document_sequence,
                    base_lock_version=request.expected_version, lock_version=after.document.lock_version,
                    before_state=before, after_state=after.document.model_dump(mode='json'),
                    before_content_sha256=result['before_content_sha256'],
                    after_content_sha256=result['after_content_sha256'], operation_count=len(prepared.members),
                    result=result, result_sha256=content_hash(result)))
                if prepared.changed:
                    DocumentRepository(session).store(after)
                    projects.touch(project)
                for snapshot in prepared.snapshots:
                    session.execute(pg_insert(m.design_document_snapshots).values(**snapshot).on_conflict_do_nothing())
                for member in prepared.members:
                    session.execute(insert(m.document_operations).values(project_id=project['id'],
                        batch_id=request.batch_id, document_id=request.document_id,
                        sequence=first_sequence + member['batch_index'], **member))
                return result
        except IntegrityError:
            # The transaction context has rolled back before this translation.
            # Do not disclose SQL, parameters or filesystem/configuration details.
            raise PersistenceError('OPERATION_STORAGE_CONFLICT',
                'Operation identities or state references conflict with stored history.', 409) from None
