"""Project lifecycle around the existing repository and revision publisher."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import insert, update
from pydantic import ValidationError
from app.persistence import models as m
from app.persistence.assets import content_hash, canonical_json
from app.persistence.repositories import ProjectRepository, CatalogRepository, PersistenceError
from app.persistence.revisions import write_revision
from app.persistence.revision_outputs import prepare_outputs
from app.persistence.documents import document_hash
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
        pid = str(uuid4())
        with self.db.sessions() as s:
            catalog = CatalogRepository(s, self.service.assets)
            template = catalog.template(data.archetype, data.archetype_version_id)
            historical_templates = [catalog.template(data.archetype, source['manifest']['archetype_version_id'])
                                    for source in package.revisions]
            enclosures = catalog.enclosures()
        from app.services.document_service import DocumentService
        from app.services.cad_engine import CADEngine
        from app.services.schematic_engine import SchematicEngine
        from app.services.panel_assembly import assembly_bom
        document = DocumentService.empty_document({'id': pid, 'lock_version': 1}, template)
        source_document = {**document.model_dump(mode='json'), 'content_sha256': document_hash(document.document)}
        prepared = []
        for index, source in enumerate(package.revisions):
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
            historical = historical_templates[index]
            values = {r.id:r.value for r in cem.requirements if r.value is not None}
            reqs = self.service.validate(historical, pid, values)
            project = dict(id=pid, database_id=pid, lock_version=index+1,
                           configuration=manifest.get('configuration', {}))
            result = {'cem': cem.model_dump(), 'pdm': pdm.model_dump(), 'validation_errors': []}
            result['cad'] = CADEngine().generate_parametric_geometry(pdm)
            result['schematic'] = SchematicEngine().generate_schematic_data(cem)
            result['bom'] = assembly_bom(cem, pdm)
            files = self.service.generate_files(result)
            manifest = {**manifest, 'copied_from_project': old}
            outputs = prepare_outputs(project, reqs, values, result, manifest, files,
                source_document, self.service.assets, project['lock_version'])
            prepared.append((project, historical, reqs, values, result, manifest, files, outputs))
        reqs = self.service.validate(template, pid, data.requirements)
        self.service.configure_enclosures(enclosures, package.configuration)
        # All validation, engine calls, serialization, hashes and file writes end
        # above. Project creation and every revision remain one atomic DB unit.
        with self.db.sessions.begin() as s:
            repo = ProjectRepository(s)
            s.execute(insert(m.projects).values(id=pid, name=data.name, status='ACTIVE',
                archetype_version_id=template['archetype_version_id'],
                description=data.description, location=data.location))
            doc = source_document['document']
            s.execute(insert(m.design_documents).values(id=doc['document_id'], project_id=pid,
                panel_id=doc['panel_id'], schema_version=doc['schema_version'], document_sequence=0,
                document=doc, content_sha256=source_document['content_sha256']))
            s.execute(insert(m.design_document_snapshots).values(document_id=doc['document_id'],
                model_kind='REQUIREMENTS', schema_version=1, sha256=doc['models']['requirements']['sha256'],
                snapshot=source_document['snapshots']['requirements']))
            for project, historical, historical_reqs, values, result, manifest, files, outputs in prepared:
                write_revision(s, project, historical, historical_reqs, values, result,
                    manifest, files, project['lock_version'], outputs=outputs)
            row = repo.row(pid)
            repo.save_requirements(row, template, reqs, data.requirements)
            repo.touch(row, configuration=package.configuration, workspace=package.workspace)
            return repo.get(pid)
