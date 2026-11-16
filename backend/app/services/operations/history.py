"""Append-only batch history derived from immutable receipts and snapshots.

Every commit is one undo group. A drag uses transient previews and submits its
final move (or ordered moves) in one batch, never one durable batch per pointer
event. Undo/redo restore semantic state, pins and dirty stages exactly, while
document clocks and provenance advance. Revisions are never edited.
"""
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import select

from app.models.document import ResolvedDocument, WorkingDocument, DocumentProvenance
from app.models.operations import OperationHistory
from app.persistence import models as m
from app.persistence.assets import content_hash
from app.persistence.documents import document_hash
from app.persistence.repositories import PersistenceError


def semantic_hash(document):
    """Engineering state excludes mutation/audit clocks, not dependency status."""
    if isinstance(document, dict):
        document = WorkingDocument.model_validate(document)
    return content_hash(document.model_dump(mode='json', exclude={
        'document_sequence', 'lock_version', 'base_revision_id', 'provenance'}))


def conflict(message='History base changed. Retain edits and reload before undo or redo.'):
    raise PersistenceError('DOCUMENT_CONFLICT', message, 409)


def branch_state(document):
    if isinstance(document, dict):
        document = WorkingDocument.model_validate(document)
    # A direct changed Save clears last_operation_id even if a later Save returns
    # to identical values. It must not resurrect a discarded redo branch.
    return (semantic_hash(document), document.base_revision_id, document.provenance.last_operation_id)


def verified_rows(session, project_id, document_id):
    # Batch clocks alone cannot order no-op receipts. First member sequences can.
    rows = session.execute(select(m.operation_batches).join(m.document_operations,
        (m.operation_batches.c.project_id == m.document_operations.c.project_id)
        & (m.operation_batches.c.id == m.document_operations.c.batch_id))
        .where(m.operation_batches.c.project_id == project_id,
               m.operation_batches.c.document_id == document_id, m.document_operations.c.batch_index == 0)
        .order_by(m.document_operations.c.sequence)).mappings().all()
    try:
        for row in rows:
            if (content_hash(row['payload']) != row['payload_sha256']
                    or content_hash(row['result']) != row['result_sha256']
                    or document_hash(WorkingDocument.model_validate(row['before_state'])) != row['before_content_sha256']
                    or document_hash(WorkingDocument.model_validate(row['after_state'])) != row['after_content_sha256']
                    or row['result']['result']['document'] != row['after_state']):
                raise ValueError('History integrity')
    except (ValidationError, KeyError, TypeError, ValueError):
        raise PersistenceError('OPERATION_HISTORY_INTEGRITY', 'Retained history failed integrity verification.', 409) from None
    return rows


def history_stacks(rows, current):
    undo, redo, previous = [], [], None
    for row in rows:
        before, after = semantic_hash(row['before_state']), semantic_hash(row['after_state'])
        if previous is not None and branch_state(row['before_state']) != previous:
            # An explicit Save/conversion outside operations starts a new branch.
            undo, redo = [], []
        previous = branch_state(row['after_state'])
        if before == after:
            continue
        action = row['payload'].get('action')
        if action in ('UNDO', 'REDO'):
            source, destination = (undo, redo) if action == 'UNDO' else (redo, undo)
            target = row['payload']['target_batch_id']
            if not source or str(source[-1]['id']) != target:
                raise PersistenceError('OPERATION_HISTORY_INTEGRITY', 'Retained history has an invalid branch transition.', 409)
            destination.append(source.pop())
        else:
            undo.append(row)
            redo = []
    if previous is not None and previous != branch_state(current):
        return [], []
    return undo, redo


def history_view(base, rows):
    undo, redo = history_stacks(rows, base.document)
    return OperationHistory(document_id=base.document.document_id,
        document_sequence=base.document.document_sequence, lock_version=base.document.lock_version,
        content_sha256=document_hash(base.document),
        undo_batch_ids=[row['id'] for row in undo], redo_batch_ids=[row['id'] for row in redo])


@dataclass(frozen=True)
class HistoryContext:
    rows: tuple
    restored: ResolvedDocument | None


def load_history_context(session, project_id, base, request):
    rows = verified_rows(session, project_id, base.document.document_id)
    row = next((row for row in rows if str(row['id']) == str(request.target_batch_id)), None)
    if row is None:
        return HistoryContext(tuple(rows), None)
    state = row['before_state'] if request.action == 'UNDO' else row['after_state']
    snapshots = {}
    for kind, ref in state['models'].items():
        snapshots[kind] = None if ref is None else session.scalar(select(m.design_document_snapshots.c.snapshot).where(
            m.design_document_snapshots.c.document_id == base.document.document_id,
            m.design_document_snapshots.c.model_kind == kind.upper(),
            m.design_document_snapshots.c.schema_version == ref['schema_version'],
            m.design_document_snapshots.c.sha256 == ref['sha256']))
    try:
        restored = ResolvedDocument.model_validate(dict(document=state, snapshots=snapshots))
    except (ValidationError, ValueError, TypeError):
        raise PersistenceError('OPERATION_HISTORY_INTEGRITY', 'Retained inverse snapshots failed integrity verification.', 409) from None
    return HistoryContext(tuple(rows), restored)


def restore_history(base, request, context):
    """Detached inverse evaluation, fenced again by the transactional writer."""
    doc = base.document
    if (request.document_id != doc.document_id or request.base_sequence != doc.document_sequence
            or request.expected_version != doc.lock_version or request.base_revision_id != doc.base_revision_id
            or request.before_content_sha256 != document_hash(doc)):
        conflict()
    undo, redo = history_stacks(context.rows, doc)
    stack = undo if request.action == 'UNDO' else redo
    if not stack or str(stack[-1]['id']) != str(request.target_batch_id) or context.restored is None:
        conflict('Only the current history branch tip can be undone or redone. Review current history.')
    target = stack[-1]
    expected_state = target['after_state'] if request.action == 'UNDO' else target['before_state']
    if semantic_hash(doc) != semantic_hash(expected_state):
        conflict()
    candidate = ResolvedDocument.model_validate(context.restored.model_dump(mode='json'))
    restored = candidate.document
    if (restored.document_id, restored.project_id, restored.panel_id, restored.base_revision_id) != (
            doc.document_id, doc.project_id, doc.panel_id, doc.base_revision_id):
        conflict('History belongs to a different document or revision base.')
    restored.document_sequence, restored.lock_version = doc.document_sequence + 1, doc.lock_version + 1
    restored.provenance = DocumentProvenance(origin=request.origin.kind, actor_id=request.origin.actor_id,
        last_operation_id=str(request.operation_id), job_id=request.origin.job_id)
    return ResolvedDocument.model_validate(candidate.model_dump(mode='json'))
