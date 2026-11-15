"""Read immutable revision representations without invoking installed generators."""
from copy import deepcopy

from sqlalchemy import select

from app.persistence import models as m
from app.persistence.assets import AssetUnavailable, content_hash
from app.persistence.repositories import CatalogRepository, ProjectRepository, PersistenceError, identifier
from app.persistence.revision_outputs import OUTPUT_KINDS, verify_outputs


class RevisionReader:
    def __init__(self, database, assets, engine_version):
        self.db, self.assets, self.engine_version = database, assets, engine_version

    def read(self, key, revision_id=None):
        with self.db.sessions() as session:
            project = ProjectRepository(session).get(key)
            rid = identifier(revision_id or project['current_revision_id'])
            revision = session.execute(select(m.project_revisions).where(
                m.project_revisions.c.id == rid,
                m.project_revisions.c.project_id == identifier(project['database_id']))).mappings().first()
            if revision is None:
                raise PersistenceError('DESIGN_NOT_FOUND', 'No saved design revision was found.', 404)
            models = {}
            for kind, table in [('CEM', m.cem_snapshots), ('PDM', m.pdm_snapshots)]:
                row = session.execute(select(table).where(table.c.project_revision_id == rid)).mappings().first()
                if row is None or content_hash(row['snapshot']) != row['sha256']:
                    raise PersistenceError('SNAPSHOT_INTEGRITY', 'Saved snapshot integrity verification failed.', 409)
                models[kind] = dict(row)
            manifest = deepcopy(revision['model_manifest'])
            if content_hash(dict(cem=models['CEM']['sha256'], pdm=models['PDM']['sha256'],
                                 manifest=manifest)) != revision['content_sha256']:
                raise PersistenceError('REVISION_INTEGRITY', 'Saved revision manifest integrity verification failed.', 409)
            bundle = session.execute(select(m.revision_output_manifests).where(
                m.revision_output_manifests.c.project_revision_id == rid)).mappings().first()
            snapshots = {row['output_kind']: dict(row) for row in session.execute(
                select(m.revision_output_snapshots).where(
                    m.revision_output_snapshots.c.project_revision_id == rid)).mappings()}
            files = [dict(row) for row in session.execute(select(m.generated_artifacts).where(
                m.generated_artifacts.c.project_revision_id == rid).order_by(
                    m.generated_artifacts.c.created_at.desc())).mappings()]

        # File verification takes place after closing the database read transaction.
        artifacts = [CatalogRepository(None, self.assets).asset_dto(row, True) for row in files]
        if bundle is not None:
            if (manifest.get('output_manifest_sha256') != bundle['sha256']
                    or bundle['manifest'].get('project_revision_id') != str(rid)
                    or bundle['manifest'].get('project_id') != project['database_id']):
                raise PersistenceError('REVISION_OUTPUT_INTEGRITY', 'Saved output manifest reference differs.', 409)
            verify_outputs(bundle['manifest'], bundle['sha256'], snapshots, files, self.assets)
            if any(snapshots[k]['sha256'] != models[k]['sha256'] for k in models):
                raise PersistenceError('REVISION_OUTPUT_INTEGRITY', 'Saved model snapshot references differ.', 409)
            outputs = {kind: deepcopy(row['snapshot']) for kind, row in snapshots.items()}
            missing = []
        else:
            if snapshots or manifest.get('output_manifest_sha256'):
                raise PersistenceError('REVISION_OUTPUT_INTEGRITY', 'Saved output manifest is missing.', 409)
            outputs = {kind: deepcopy(row['snapshot']) for kind, row in models.items()}
            missing = sorted(OUTPUT_KINDS - outputs.keys())

        non_current = project['current_revision_id'] != str(rid)
        input_stale = manifest.get('input_sha256') != content_hash({
            'requirements': project['requirements'], 'configuration': project['configuration']})
        incompatible = (manifest.get('engine_version') != self.engine_version
                        or manifest.get('generator') != {'name': 'panelstudio-primitives', 'version': '3'})
        return dict(cem=outputs['CEM'], pdm=outputs['PDM'], schematic=outputs.get('SCHEMATIC'),
            cad=outputs.get('CAD'), bom=outputs.get('BOM'),
            validation_errors=outputs.get('VALIDATION', {}).get('validation_errors',
                outputs['PDM'].get('validation_results', [])),
            revision_id=str(rid), revision_no=revision['revision_no'], lock_version=project['lock_version'],
            snapshot_sha256=revision['content_sha256'], manifest=manifest, artifacts=artifacts,
            is_stale=non_current or input_stale or incompatible,
            is_non_current=non_current, is_input_stale=input_stale, is_version_incompatible=incompatible,
            output_status='MISSING_OUTPUTS' if missing else 'COMPLETE', missing_outputs=missing,
            output_manifest=deepcopy(bundle['manifest']) if bundle else None,
            output_manifest_sha256=bundle['sha256'] if bundle else None,
            compatibility_conversion_available=bool(missing))

    def freecad_script(self, key, revision_id=None):
        design = self.read(key, revision_id)
        # Complete bundles identify the original publication, not later export jobs.
        refs = (design['output_manifest'] or {}).get('artifacts', [])
        if design['output_manifest'] is None:
            with self.db.sessions() as session:
                refs = [dict(row) for row in session.execute(select(m.generated_artifacts).where(
                    m.generated_artifacts.c.project_revision_id == identifier(design['revision_id']),
                    m.generated_artifacts.c.generation_status == 'READY')).mappings()]
        for row in refs:
            if row['artifact_type'] == 'FREECAD_SCRIPT' and row['file_format'] == 'PY':
                try:
                    path = self.assets.verified_path(row['storage_key'], row['sha256'], row['byte_size'])
                    return {'script': path.read_bytes().decode('utf-8'), 'revision_id': design['revision_id']}
                except (AssetUnavailable, OSError, UnicodeError) as exc:
                    raise PersistenceError('REVISION_OUTPUT_INTEGRITY',
                        'Saved FreeCAD script is unavailable or corrupt.', 409) from exc
        raise PersistenceError('REVISION_OUTPUT_MISSING',
            'This revision has no saved publication FreeCAD script.', 409)
