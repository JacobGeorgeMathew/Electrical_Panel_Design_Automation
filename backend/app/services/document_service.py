"""Explicit working-document persistence, without engineering computation."""
from uuid import uuid4

from app.models.document import (DocumentReferences, DocumentSnapshots, PinnedVersions,
    DocumentProvenance, ResolvedDocument, SnapshotReference, WorkingDocument, snapshot_sha256)
from app.models.requirements import RequirementSet
from app.persistence.assets import content_hash
from app.persistence.documents import DocumentRepository
from app.persistence.repositories import ProjectRepository, PersistenceError

DIRTY_STAGES = ['requirements', 'calculations', 'selection', 'connectivity', 'schematic',
                'placement', 'routes', 'physical_validation', 'bom', 'cad']


class DocumentService:
    def __init__(self, database):
        self.db = database

    @staticmethod
    def create_empty(session, project, template):
        DocumentRepository(session).store(DocumentService.empty_document(project, template), create=True)

    @staticmethod
    def empty_document(project, template):
        requirements = RequirementSet(project_id=str(project['id']), archetype='DB')
        # Input-only document: these pins identify its known input contract, not
        # a claim that downstream engineering/catalog outputs have been computed.
        pins = PinnedVersions(engine_version='db-pipeline-4',
            generator={'name': 'panelstudio-primitives', 'version': '3'},
            catalog_manifest_sha256=content_hash({'archetype_version_id': template['archetype_version_id']}),
            catalog_versions={'archetype': template['archetype_version_id']},
            validation_policy_version='strict-v1')
        document = WorkingDocument(document_id=str(uuid4()), project_id=str(project['id']),
            panel_id=str(uuid4()), lock_version=project['lock_version'],
            models=DocumentReferences(requirements=SnapshotReference(sha256=snapshot_sha256(requirements))),
            pins=pins, provenance=DocumentProvenance(origin='MANUAL', actor_id='local-user'),
            dirty_stages=DIRTY_STAGES)
        return ResolvedDocument(document=document, snapshots=DocumentSnapshots(requirements=requirements))

    def load(self, key):
        with self.db.sessions() as session:
            return DocumentRepository(session).load(ProjectRepository(session).row(key))

    def save(self, key, data):
        with self.db.sessions.begin() as session:
            projects = ProjectRepository(session)
            project = projects.check_version(key, data.expected_version)
            documents = DocumentRepository(session)
            saved = documents.load(project)
            doc = saved.document
            if doc.document_id != data.document_id or doc.document_sequence != data.expected_document_sequence:
                raise PersistenceError('DOCUMENT_CONFLICT',
                    'Working document changed. Retain local edits and reload for comparison.', 409)
            if data.requirements.project_id != doc.project_id or data.requirements.archetype != doc.archetype:
                raise PersistenceError('DOCUMENT_IDENTITY_MISMATCH', 'Requirements belong to a different project or archetype.')
            if (saved.snapshots.requirements == data.requirements and doc.configuration == data.configuration):
                return saved
            saved.snapshots.requirements = data.requirements
            doc.models.requirements = SnapshotReference(sha256=snapshot_sha256(data.requirements))
            doc.configuration = data.configuration
            doc.dirty_stages = list(DIRTY_STAGES)
            doc.document_sequence += 1
            doc.lock_version += 1
            doc.provenance = DocumentProvenance(origin='MANUAL', actor_id='local-user')
            documents.store(saved)
            # Recovery/drafts/display state are independent and never cleared by Save.
            projects.touch(project)
            return documents.load({**project, 'lock_version': doc.lock_version})
