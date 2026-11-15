"""Project lifecycle around the existing repository and revision publisher."""
from datetime import datetime, timezone
from sqlalchemy import update
from app.persistence import models as m
from app.persistence.assets import content_hash, canonical_json
from app.persistence.repositories import ProjectRepository, PersistenceError
from app.models.api import ProjectImport
from app.services.project_package import ProjectPackage, package_hash


class ProjectLifecycle:
    def __init__(self, service):
        self.service = service
        self.db = service.db

    def opened(self, key):
        with self.db.sessions.begin() as s:
            row = ProjectRepository(s).row(key)
            s.execute(update(m.projects).where(m.projects.c.id == row['id']).values(last_opened_at=datetime.now(timezone.utc)))
            return ProjectRepository(s).get(key)

    def compatibility_proposal(self, key, data):
        from app.services.document_compatibility import overlay_proposal
        with self.db.sessions() as session:
            repo = ProjectRepository(session)
            repo.check_version(key, data.expected_version)
            project = repo.get(key)
        revision = self.service.load_revision(key, data.revision_id)
        if data.source == 'workspace':
            overlay = project['workspace']
        elif data.source == 'recovery':
            overlay = (project['recovery'] or {}).get('document', {}).get('workspace', {})
        else:
            overlay = data.overlay
        proposal = overlay_proposal(revision, overlay, data.base)
        if data.source == 'recovery':
            checkpoint_base = (project['recovery'] or {}).get('document', {}).get('baseRevisionId')
            if checkpoint_base != revision['revision_id']:
                proposal['status'] = 'BLOCKED'
                proposal['operations'] = []
                proposal['blocked'].append({'item': 'recovery.baseRevisionId', 'reason':
                    'Recovery belongs to a different or unknown base. Retain it and explicitly review its original revision before conversion.'})
        # Preserve all server originals as review/recovery evidence. No writes,
        # implicit base inference, generators or operation application occur here.
        return {**proposal, 'lock_version': project['lock_version'],
            'recovery_version': project['recovery_version'],
            'original_workspace': project['workspace'], 'original_recovery': project['recovery']}

    def delete(self, key, expected_version):
        # Tombstone preserves immutable engineering history and shared assets.
        with self.db.sessions.begin() as s:
            repo = ProjectRepository(s)
            row = repo.check_version(key, expected_version)
            repo.touch(row, deleted_at=datetime.now(timezone.utc), recovery=None)

    def recovery(self, key, data):
        with self.db.sessions.begin() as s:
            repo = ProjectRepository(s)
            # Serialize on the project row, but fence only the recovery clock.
            # A changed document base is retained for explicit client resolution.
            row = repo.check_version(key)
            if row['recovery_version'] != data.expected_recovery_version:
                raise PersistenceError('RECOVERY_CONFLICT', 'Another session changed the recovery checkpoint. Reopen the project before saving.', 409)
            if data.document is not None and len(canonical_json(data.document)) > 4 * 1024 * 1024:
                raise PersistenceError('DOCUMENT_TOO_LARGE', 'Recovery documents are limited to 4 MiB.', 413)
            checkpoint = None if data.document is None else {
                'schema_version': 2, 'recovery_sequence': row['recovery_version'] + 1,
                'base_version': data.expected_version,
                'saved_at': datetime.now(timezone.utc).isoformat(), 'document': data.document}
            s.execute(update(m.projects).where(m.projects.c.id == row['id']).values(
                recovery=checkpoint, recovery_version=row['recovery_version'] + 1))
            return repo.get(key)

    def export(self, key, expected_version=None):
        return ProjectPackage(self.service).export(key, expected_version)

    def duplicate(self, key, data):
        package = self.export(key, data.expected_version)
        package['project']['name'] = data.name
        package['sha256'] = package_hash(package)
        return self.import_project(ProjectImport(**package))

    def import_project(self, package):
        return ProjectPackage(self.service).import_project(package)
