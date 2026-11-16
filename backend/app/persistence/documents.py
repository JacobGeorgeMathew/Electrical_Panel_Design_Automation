"""Hashed working aggregates and append-only referenced snapshots."""
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.document import ResolvedDocument
from app.models.document_api import DocumentView
from app.persistence import models as m
from app.persistence.assets import content_hash
from app.persistence.repositories import PersistenceError


def document_hash(document):
    payload = document.model_dump(mode='json', exclude={
        'lock_version', 'document_sequence', 'base_revision_id'})
    return content_hash(payload)


class DocumentRepository:
    def __init__(self, session):
        self.s = session

    def load(self, project):
        row = self.s.execute(select(m.design_documents).where(
            m.design_documents.c.project_id == project['id'])).mappings().first()
        if row is None:
            raise PersistenceError('DOCUMENT_NOT_INITIALIZED',
                'This project requires explicit working-document conversion.', 409)
        try:
            snapshots = {}
            for kind, ref in row['document']['models'].items():
                if ref is None:
                    snapshots[kind] = None
                    continue
                snapshots[kind] = self.s.scalar(select(m.design_document_snapshots.c.snapshot).where(
                    m.design_document_snapshots.c.document_id == row['id'],
                    m.design_document_snapshots.c.model_kind == kind.upper(),
                    m.design_document_snapshots.c.schema_version == ref['schema_version'],
                    m.design_document_snapshots.c.sha256 == ref['sha256']))
            resolved = ResolvedDocument.model_validate(dict(document=row['document'], snapshots=snapshots))
            doc = resolved.document
            if (doc.project_id != str(project['id']) or doc.document_id != row['id']
                    or doc.panel_id != row['panel_id'] or doc.schema_version != row['schema_version']
                    or doc.document_sequence != row['document_sequence']
                    or doc.base_revision_id != (str(row['base_revision_id']) if row['base_revision_id'] else None)
                    or document_hash(doc) != row['content_sha256']):
                raise ValueError('Document metadata or content differs')
        except (ValidationError, KeyError, TypeError, ValueError, AttributeError, RecursionError):
            raise PersistenceError('DOCUMENT_INTEGRITY',
                'Stored working-document content is corrupt or incompatible.', 409) from None
        doc.lock_version = project['lock_version']
        return DocumentView(**resolved.model_dump(), content_sha256=row['content_sha256'])

    def store(self, resolved, create=False):
        # Validate the entire resolved boundary even for internal callers.
        resolved = ResolvedDocument.model_validate(resolved.model_dump(mode='json', include={'document', 'snapshots'}))
        doc = resolved.document
        values = dict(document=doc.model_dump(mode='json'), document_sequence=doc.document_sequence,
                      content_sha256=document_hash(doc), updated_at=datetime.now(timezone.utc))
        if create:
            self.s.execute(insert(m.design_documents).values(id=doc.document_id, project_id=doc.project_id,
                panel_id=doc.panel_id, schema_version=doc.schema_version,
                base_revision_id=doc.base_revision_id, **values))
        else:
            self.s.execute(update(m.design_documents).where(
                m.design_documents.c.id == doc.document_id).values(**values))
        for kind in ('requirements', 'cem', 'pdm', 'schematic'):
            snapshot, ref = getattr(resolved.snapshots, kind), getattr(doc.models, kind)
            if snapshot is not None:
                self.s.execute(pg_insert(m.design_document_snapshots).values(document_id=doc.document_id,
                    model_kind=kind.upper(), schema_version=ref.schema_version, sha256=ref.sha256,
                    snapshot=snapshot.model_dump(mode='json')).on_conflict_do_nothing())
