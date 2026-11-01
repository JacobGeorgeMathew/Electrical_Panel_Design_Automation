"""Project lifecycle around the existing repository and revision publisher."""
from copy import deepcopy
from datetime import datetime, timezone
from sqlalchemy import update
from pydantic import ValidationError
from app.persistence import models as m
from app.persistence.assets import content_hash, canonical_json
from app.persistence.repositories import ProjectRepository, CatalogRepository, PersistenceError
from app.persistence.revisions import write_revision
from app.models.api import ProjectCreate, ProjectImport
from app.models.cem import CanonicalEngineeringModel
from app.models.pdm import PhysicalDesignModel
from app.services.validation_engine import ValidationEngine


class ProjectLifecycle:
    def __init__(self, service):
        self.service = service
        self.db = service.db

    def opened(self, key):
        with self.db.sessions.begin() as s:
            row = ProjectRepository(s).row(key)
            s.execute(update(m.projects).where(m.projects.c.id == row['id']).values(last_opened_at=datetime.now(timezone.utc)))
            return ProjectRepository(s).get(key)

    def delete(self, key, expected_version):
        # Tombstone preserves immutable engineering history and shared assets.
        with self.db.sessions.begin() as s:
            repo = ProjectRepository(s)
            row = repo.check_version(key, expected_version)
            repo.touch(row, deleted_at=datetime.now(timezone.utc), recovery=None)

    def recovery(self, key, data):
        with self.db.sessions.begin() as s:
            repo = ProjectRepository(s)
            row = repo.check_version(key, data.expected_version)
            if row['recovery_version'] != data.expected_recovery_version:
                raise PersistenceError('RECOVERY_CONFLICT', 'Another session changed the recovery checkpoint. Reopen the project before saving.', 409)
            if data.document is not None and len(canonical_json(data.document)) > 4 * 1024 * 1024:
                raise PersistenceError('DOCUMENT_TOO_LARGE', 'Recovery documents are limited to 4 MiB.', 413)
            checkpoint = None if data.document is None else {
                'base_version': row['lock_version'], 'saved_at': datetime.now(timezone.utc).isoformat(), 'document': data.document}
            s.execute(update(m.projects).where(m.projects.c.id == row['id']).values(
                recovery=checkpoint, recovery_version=row['recovery_version'] + 1))
            return repo.get(key)

    def export(self, key, expected_version=None):
        # A project row lock keeps metadata/revision identity consistent.
        with self.db.sessions.begin() as s:
            repo = ProjectRepository(s)
            repo.check_version(key, expected_version)
            p = repo.get(key)
            history=repo.revisions(key)
            if len(history)>200:
                raise PersistenceError('PROJECT_TOO_LARGE','JSON packages support at most 200 revisions. Use a database backup for larger projects.',413)
            revisions = [self.service.load_revision(key, r['id']) for r in reversed(history)]
            package = {'format': 'panelstudio-project', 'version': 1, 'source_project_id': p['id'],
                'project': {'name': p['name'], 'description': p['description'], 'location': p['location'],
                    'archetype': p['archetype'], 'archetype_version_id': p['archetype_version_id'], 'requirements': p['requirements']},
                'configuration': p['configuration'], 'workspace': p['workspace'],
                'revisions': [{'cem': r['cem'], 'pdm': r['pdm'], 'manifest': r['manifest'],
                    'sha256': content_hash({'cem': r['cem'], 'pdm': r['pdm'], 'manifest': r['manifest']})} for r in revisions]}
            if len(canonical_json(package))>32*1024*1024:
                raise PersistenceError('PROJECT_TOO_LARGE','JSON packages support at most 32 MiB. Use a database backup for larger projects.',413)
            return package

    def duplicate(self, key, data):
        package = self.export(key, data.expected_version)
        package['project']['name'] = data.name
        return self.import_project(ProjectImport(**package))

    def import_project(self, package):
        if len(canonical_json(package.model_dump())) > 32 * 1024 * 1024:
            raise PersistenceError('PROJECT_TOO_LARGE', 'Project packages are limited to 32 MiB.', 413)
        try:
            return self._import(package)
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            raise PersistenceError('INVALID_PROJECT_PACKAGE', 'The project package is malformed or incompatible with this installation.') from exc

    def _import(self, package):
        # Never adopt an imported identity or overwrite an existing project.
        data = ProjectCreate(**{**package.project.model_dump(), 'id': None})
        with self.db.sessions.begin() as s:
            repo = ProjectRepository(s)
            catalog = CatalogRepository(s, self.service.assets)
            template = catalog.template(data.archetype, data.archetype_version_id)
            pid = repo.create(data.name, template['archetype_version_id'])
            row = repo.row(pid)
            s.execute(update(m.projects).where(m.projects.c.id == row['id']).values(description=data.description, location=data.location))
            for source in package.revisions:
                payload = {k: source[k] for k in ('cem', 'pdm', 'manifest')}
                if content_hash(payload) != source['sha256']:
                    raise PersistenceError('PACKAGE_INTEGRITY', 'A design revision failed its integrity check.')
                old = package.source_project_id
                if payload['cem']['project_id']!=old or payload['pdm']['project_id']!=old:
                    raise PersistenceError('PROJECT_MISMATCH','A revision belongs to a different project.')
                def rebind(value):
                    if isinstance(value, dict): return {k: rebind(v) for k,v in value.items()}
                    if isinstance(value, list): return [rebind(v) for v in value]
                    if isinstance(value, str):
                        return {old: pid, 'DB-'+old: 'DB-'+pid, 'PDM-'+old: 'PDM-'+pid}.get(value, value)
                    return value
                payload = rebind(deepcopy(payload))
                cem = CanonicalEngineeringModel(**payload['cem'])
                pdm = PhysicalDesignModel(**payload['pdm'])
                failures = ValidationEngine().validate_pdm(pdm, cem)
                if failures:
                    raise PersistenceError('INVALID_IMPORTED_DESIGN', 'An imported design fails physical validation; no project was imported.')
                manifest = payload['manifest']
                historical = catalog.template(data.archetype, manifest['archetype_version_id'])
                values = {r.id:r.value for r in cem.requirements if r.value is not None}
                reqs = self.service.validate(historical, pid, values)
                project = repo.get(pid)
                project['configuration'] = manifest.get('configuration', {})
                result = {'cem': cem.model_dump(), 'pdm': pdm.model_dump(), 'validation_errors': []}
                from app.services.cad_engine import CADEngine
                result['cad'] = CADEngine().generate_parametric_geometry(pdm)
                files = self.service.generate_files(result)
                write_revision(s, project, historical, reqs, values, result,
                    {**manifest, 'copied_from_project': old}, files, project['lock_version'])
            row = repo.row(pid)
            reqs = self.service.validate(template, pid, data.requirements)
            self.service.configure_enclosures(catalog.enclosures(), package.configuration)
            repo.save_requirements(row, template, reqs, data.requirements)
            repo.touch(row, configuration=package.configuration, workspace=package.workspace)
            return repo.get(pid)
