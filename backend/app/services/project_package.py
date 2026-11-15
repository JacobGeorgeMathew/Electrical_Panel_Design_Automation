"""Bounded JSON transport of verified, immutable publications and managed bytes.

V2 preserves presentation/output bytes and artifacts without executing generators.
Ownership-bearing snapshots acquire new hashes when rebound; their exact source
snapshots and hashes remain in the publication DOCUMENT's portable_source field.
V1 has only CEM/PDM: import preserves explicitly missing outputs and no artifacts.
"""
import base64
import binascii
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import re
from uuid import uuid4
from types import SimpleNamespace

from fastapi import Request
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import insert, select

from app.models.api import ProjectCreate, ProjectImport, ProjectUpdate, WorkspaceDocument
from app.models.cem import CanonicalEngineeringModel
from app.models.document import DocumentProvenance, ResolvedDocument, snapshot_sha256, validate_engineering_references
from app.models.pdm import PhysicalDesignModel
from app.persistence import models as m
from app.persistence.assets import AssetUnavailable, canonical_json, content_hash
from app.persistence.documents import DocumentRepository, document_hash
from app.persistence.repositories import CatalogRepository, ProjectRepository, PersistenceError, identifier, serial
from app.persistence.revision_outputs import prepare_outputs, verify_outputs
from app.persistence.revisions import write_revision
from app.services.validation_engine import ValidationEngine

MAX_PACKAGE = 32 * 1024 * 1024
MAX_ASSET = 8 * 1024 * 1024
MAX_ASSETS_BYTES = 16 * 1024 * 1024
MAX_ASSETS = 2048
FILE_FIELDS = ('artifact_type', 'file_format', 'storage_backend', 'storage_key',
               'sha256', 'byte_size', 'generator_name', 'generator_version')
FORMATS = {'GLB': 'glb', 'JSON': 'json', 'PY': 'py', 'STEP': 'step', 'FCSTD': 'fcstd', 'PDF': 'pdf'}
KEY_PATTERN = re.compile(r'sha256/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}\.(glb|json|py|step|fcstd|pdf)')


def invalid():
    return PersistenceError('INVALID_PROJECT_PACKAGE',
        'The project package is malformed or incompatible with this installation.')


def package_hash(package):
    return content_hash({k: v for k, v in package.items() if k != 'sha256'})


def bounded_json(value):
    """Bound depth/node count before recursive serialization of direct callers."""
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if depth > 64 or nodes > 500000:
            raise PersistenceError('PROJECT_TOO_LARGE', 'Project package structure exceeds its limits.', 413)
        if isinstance(item, dict):
            pending.extend((v, depth + 1) for v in item.values())
        elif isinstance(item, list):
            pending.extend((v, depth + 1) for v in item)
    if len(canonical_json(value)) > MAX_PACKAGE:
        raise PersistenceError('PROJECT_TOO_LARGE', 'Project packages are limited to 32 MiB.', 413)


async def read_project_package(request: Request):
    """Limit actual received bytes, including chunked bodies, before JSON parsing."""
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_PACKAGE:
            raise PersistenceError('PROJECT_TOO_LARGE', 'Project packages are limited to 32 MiB.', 413)
        body.extend(chunk)
    try:
        value = json.loads(body)
        bounded_json(value)
        return ProjectImport.model_validate(value)
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise invalid() from None


class PackageImportRoute(APIRoute):
    """Keep the typed OpenAPI body while checking raw bytes before FastAPI parses."""
    def get_route_handler(self):
        handler = super().get_route_handler()
        if self.path != '/api/projects/import':
            return handler

        async def bounded(request):
            package = await read_project_package(request)
            request._body = canonical_json(package.model_dump(mode='json', exclude_unset=True))
            return await handler(request)

        return bounded


def check_asset(ref):
    key, digest, size = ref['storage_key'], ref['sha256'], ref['byte_size']
    if (not isinstance(key, str) or not KEY_PATTERN.fullmatch(key)
            or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)
            or key != f'sha256/{digest[:2]}/{digest[2:4]}/{digest}.{key.rsplit(".", 1)[-1]}'
            or type(size) is not int or not 0 <= size <= MAX_ASSET):
        raise PersistenceError('PACKAGE_ASSET_INTEGRITY', 'Invalid managed asset path, hash or size.')
    return key


class EmbeddedAssets:
    """An in-memory verification adapter; package keys are never filesystem paths."""
    def __init__(self, entries):
        self.data = {}
        total = 0
        if len(entries) > MAX_ASSETS:
            raise invalid()
        for entry in entries:
            if set(entry) != {'storage_key', 'sha256', 'byte_size', 'data_base64'}:
                raise invalid()
            key = check_asset(entry)
            encoded = entry['data_base64']
            if key in self.data or not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_ASSET + 2) // 3):
                raise invalid()
            try:
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                raise invalid() from None
            total += len(data)
            if total > MAX_ASSETS_BYTES:
                raise PersistenceError('PROJECT_TOO_LARGE', 'Embedded assets are limited to 16 MiB.', 413)
            if len(data) != entry['byte_size'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise PersistenceError('PACKAGE_ASSET_INTEGRITY', 'Embedded asset content failed verification.')
            self.data[key] = data

    def verified_path(self, key, digest, size=None):
        check_asset(dict(storage_key=key, sha256=digest, byte_size=size))
        data = self.data.get(key)
        if data is None or len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise AssetUnavailable('Embedded asset is missing or corrupt.')


def validate_pins(session, manifest, cem):
    """Every required immutable FK/pin must exist; never substitute latest."""
    refs = {}

    def add(table, values):
        refs.setdefault(table, set()).update(v for v in values if v is not None)

    add(m.panel_archetype_versions, [manifest['archetype_version_id']])
    add(m.questionnaire_versions, [manifest.get('questionnaire_version_id')])
    add(m.rule_set_versions, [manifest.get('rule_set_version_id')])
    add(m.design_rule_versions, manifest.get('rule_versions', []))
    add(m.design_rule_versions, manifest.get('validation_rule_versions', {}).values())
    add(m.component_versions, [manifest['enclosure_component_version_id']])
    add(m.component_versions, manifest.get('hardware_component_versions', {}).values())
    for key, table in [('component_versions', m.component_versions), ('product_versions', m.product_versions),
                       ('cad_model_versions', m.cad_model_versions)]:
        add(table, manifest.get(key, {}).values())
    add(m.cad_model_versions, [manifest.get('enclosure_cad_model_version_id')])
    for component in cem['components']:
        if not component.get('component_version_id'):
            raise PersistenceError('PACKAGE_PIN_MISSING', 'A required catalog version is missing.', 409)
        for key, table in [('component_version_id', m.component_versions),
                           ('product_version_id', m.product_versions), ('cad_model_version_id', m.cad_model_versions)]:
            add(table, [component.get(key)])
    for template in manifest.get('electrical_templates', []):
        add(m.electrical_template_versions, [template['id']])
        add(m.template_component_roles, [r['id'] for r in template.get('roles', [])])
    for table, values in refs.items():
        ids = [identifier(v) for v in values]
        if None in ids or set(session.scalars(select(table.c.id).where(table.c.id.in_(ids)))) != set(ids):
            raise PersistenceError('PACKAGE_PIN_MISSING',
                'Required catalog versions are unavailable. Install a compatible catalog before importing.', 409)


class ProjectPackage:
    def __init__(self, service):
        self.service, self.db, self.assets = service, service.db, service.assets

    def export(self, key, expected_version=None):
        # Detach all metadata in one consistent project-locked read. Hashing and
        # filesystem reads occur only after releasing the transaction.
        with self.db.sessions.begin() as session:
            repo = ProjectRepository(session)
            repo.check_version(key, expected_version)
            project = repo.get(key)
            history = repo.revisions(key)
            if len(history) > 200:
                raise PersistenceError('PROJECT_TOO_LARGE', 'Packages support at most 200 revisions.', 413)
            document = DocumentRepository(session).load(repo.row(key)).model_dump(mode='json')
            revisions = []
            for summary in reversed(history):
                rid = identifier(summary['id'])
                row = session.execute(select(m.project_revisions).where(m.project_revisions.c.id == rid)).mappings().one()
                source = dict(revision_id=str(rid), manifest=row['model_manifest'], revision_sha256=row['content_sha256'])
                for kind, table in [('cem', m.cem_snapshots), ('pdm', m.pdm_snapshots)]:
                    saved = session.execute(select(table).where(table.c.project_revision_id == rid)).mappings().one()
                    source[kind] = saved['snapshot']
                    source[kind + '_sha256'] = saved['sha256']
                bundle = session.execute(select(m.revision_output_manifests).where(
                    m.revision_output_manifests.c.project_revision_id == rid)).mappings().first()
                source['output_manifest'] = bundle['manifest'] if bundle else None
                source['output_manifest_sha256'] = bundle['sha256'] if bundle else None
                source['outputs'] = {r['output_kind']: {k: r[k] for k in ('schema_version', 'sha256', 'snapshot')}
                    for r in session.execute(select(m.revision_output_snapshots).where(
                        m.revision_output_snapshots.c.project_revision_id == rid)).mappings()}
                source['artifacts'] = serial([dict(r) for r in session.execute(select(m.generated_artifacts).where(
                    m.generated_artifacts.c.project_revision_id == rid).order_by(m.generated_artifacts.c.id)).mappings()])
                revisions.append(source)
        entries = {}

        def embed(ref):
            asset_key = check_asset(ref)
            if asset_key not in entries:
                if len(entries) >= MAX_ASSETS or sum(e['byte_size'] for e in entries.values()) + ref['byte_size'] > MAX_ASSETS_BYTES:
                    raise PersistenceError('PROJECT_TOO_LARGE', 'Embedded assets exceed package limits.', 413)
                data = self.assets.verified_path(asset_key, ref['sha256'], ref['byte_size']).read_bytes()
                entries[asset_key] = dict(storage_key=asset_key, sha256=ref['sha256'], byte_size=len(data),
                    data_base64=base64.b64encode(data).decode('ascii'))

        try:
            preview_components = list((document['snapshots'].get('pdm') or {}).get('components', []))
            for source in revisions:
                for artifact in source['artifacts']:
                    if artifact['generation_status'] != 'READY':
                        raise PersistenceError('PACKAGE_ASSET_UNAVAILABLE', 'All saved artifacts must be ready before export.', 409)
                    embed(artifact)
                preview_components.extend(source['pdm']['components'])
                source['sha256'] = content_hash({k: source[k] for k in ('cem', 'pdm', 'manifest')})
            for component in preview_components:
                preview = component.get('preview_asset')
                if preview:
                    with self.db.sessions() as session:
                        ref = session.execute(select(m.cad_assets).where(m.cad_assets.c.id == identifier(preview['id']))).mappings().one()
                    embed(ref)
            package = dict(format='panelstudio-project', version=2, source_project_id=project['id'],
                source_database_id=project['database_id'],
                project={k: project[k] for k in ('name', 'description', 'location', 'archetype', 'archetype_version_id', 'requirements')},
                configuration=project['configuration'], workspace=WorkspaceDocument(**project['workspace']).model_dump(mode='json'), working_document=document,
                revisions=revisions, assets=list(entries.values()))
            # Use the same verifier on export and import, including legacy bundles.
            embedded = EmbeddedAssets(package['assets'])
            for source in revisions:
                self.verify_revision(source, package['source_project_id'], embedded, project['database_id'])
            package['sha256'] = package_hash(package)
            bounded_json(package)
            return package
        except (AssetUnavailable, OSError):
            raise PersistenceError('PACKAGE_ASSET_UNAVAILABLE', 'A required managed asset is missing or corrupt.', 409) from None
        except (KeyError, TypeError, ValueError):
            raise PersistenceError('REVISION_OUTPUT_INTEGRITY', 'Saved revision outputs are corrupt or incompatible.', 409) from None

    @staticmethod
    def verify_revision(source, old, assets, source_database_id=None):
        if content_hash({k: source[k] for k in ('cem', 'pdm', 'manifest')}) != source['sha256']:
            raise PersistenceError('PACKAGE_INTEGRITY', 'A design revision failed its integrity check.')
        if source['cem']['project_id'] != old or source['pdm']['project_id'] != old:
            raise PersistenceError('PROJECT_MISMATCH', 'A revision belongs to a different project.')
        if source.get('revision_id'):
            if (source['cem_sha256'] != content_hash(source['cem']) or source['pdm_sha256'] != content_hash(source['pdm'])
                    or source['revision_sha256'] != content_hash(dict(cem=source['cem_sha256'],
                        pdm=source['pdm_sha256'], manifest=source['manifest']))):
                raise invalid()
            if source['output_manifest'] is not None:
                bundle = source['output_manifest']
                saved_document = source['outputs']['DOCUMENT']['snapshot']
                resolved = ResolvedDocument.model_validate({k: saved_document[k] for k in ('document', 'snapshots')})
                doc = resolved.document
                if (bundle['project_revision_id'] != source['revision_id']
                        or bundle['project_id'] != doc.project_id
                        or doc.project_id != (source_database_id or old)
                        or bundle['source_document'] != {'id': doc.document_id, 'sequence': doc.document_sequence,
                            'sha256': document_hash(doc)}
                        or saved_document['content_sha256'] != document_hash(doc)
                        or source['manifest']['output_manifest_sha256'] != source['output_manifest_sha256']):
                    raise invalid()
                verify_outputs(bundle, source['output_manifest_sha256'], source['outputs'], source['artifacts'], assets)
                if any(source['outputs'][k]['snapshot'] != source[k.lower()] for k in ('CEM', 'PDM')):
                    raise invalid()
            elif source['outputs'] or source['manifest'].get('output_manifest_sha256'):
                raise invalid()
            artifact_ids = set()
            for ref in source['artifacts']:
                if not identifier(ref['id']) or ref['id'] in artifact_ids:
                    raise invalid()
                artifact_ids.add(ref['id'])
                if ref['generation_status'] != 'READY' or ref['project_revision_id'] != source['revision_id']:
                    raise invalid()
                assets.verified_path(ref['storage_key'], ref['sha256'], ref['byte_size'])
                if FORMATS.get(ref['file_format']) != ref['storage_key'].rsplit('.', 1)[-1] or ref['storage_backend'] != 'LOCAL':
                    raise invalid()

    def import_project(self, package):
        try:
            raw = package.model_dump(mode='json', exclude_unset=True)
            bounded_json(raw)
            if package.version not in (1, 2):
                raise PersistenceError('UNSUPPORTED_PACKAGE_VERSION', 'Supported project package versions are 1 and 2.')
            if package.version == 2 and package.sha256 != package_hash(raw):
                raise PersistenceError('PACKAGE_INTEGRITY', 'The project package failed its integrity check.')
            return self._import(package)
        except (ValidationError, KeyError, TypeError, ValueError, AttributeError, RecursionError, AssetUnavailable, OSError):
            raise invalid() from None

    def _import(self, package):
        from app.services.document_service import DocumentService

        pid = str(uuid4())
        data = ProjectCreate(**{**package.project.model_dump(), 'id': None})
        configuration = ProjectUpdate.configuration_shape(package.configuration)
        workspace = WorkspaceDocument(**package.workspace).model_dump(mode='json')
        embedded = EmbeddedAssets(package.assets)
        old = package.source_project_id
        # V1 must not smuggle v2 fields or a misleading complete-output claim.
        if package.version == 1 and (package.assets or package.working_document or package.sha256 or package.source_database_id):
            raise invalid()
        seen = set()
        for source in package.revisions:
            if package.version == 1:
                if set(source) != {'cem', 'pdm', 'manifest', 'sha256'}:
                    raise invalid()
            else:
                if not identifier(source['revision_id']) or source['revision_id'] in seen:
                    raise invalid()
                seen.add(source['revision_id'])
            self.verify_revision(source, old, embedded, package.source_database_id)

        # All catalog resolution is explicit and read-only. No project/asset
        # writes occur until every revision, pin and payload has passed checks.
        referenced_assets = set()
        with self.db.sessions() as session:
            catalog = CatalogRepository(session, self.assets)
            if package.version == 2 and not data.archetype_version_id:
                raise invalid()
            try:
                template = catalog.template(data.archetype, data.archetype_version_id, resolve_capabilities=False)
                templates = [catalog.template(data.archetype, source['manifest']['archetype_version_id'],
                    resolve_capabilities=False) for source in package.revisions]
            except PersistenceError:
                raise PersistenceError('PACKAGE_PIN_MISSING', 'A required published archetype version is unavailable.', 409) from None
            enclosures = catalog.enclosures()
            preview_components = list(((package.working_document or {}).get('snapshots', {}).get('pdm') or {}).get('components', []))
            for source, historical in zip(package.revisions, templates):
                if historical['questionnaire_version_id'] != source['manifest'].get('questionnaire_version_id'):
                    raise PersistenceError('PACKAGE_PIN_MISSING', 'The pinned questionnaire differs from this catalog.', 409)
                validate_pins(session, source['manifest'], source['cem'])
                for ref in source.get('artifacts', []):
                    referenced_assets.add(check_asset(ref))
                preview_components.extend(source['pdm']['components'])
            for component in preview_components:
                preview = component.get('preview_asset')
                if not preview:
                    continue
                ref = session.execute(select(m.cad_assets).where(m.cad_assets.c.id == identifier(preview['id']))).mappings().first()
                if ref is None or str(ref['cad_model_version_id']) != component.get('cad_model_version_id'):
                    raise PersistenceError('PACKAGE_PIN_MISSING', 'A required catalog preview is unavailable.', 409)
                # Imported paths/URLs never drive a filesystem lookup or fetch.
                if (preview.get('sha256') != ref['sha256'] or preview.get('byte_size') != ref['byte_size']
                        or preview.get('url') != f"/api/assets/{ref['id']}/content"):
                    raise invalid()
                if package.version == 2:
                    embedded.verified_path(ref['storage_key'], ref['sha256'], ref['byte_size'])
                    referenced_assets.add(ref['storage_key'])
            if set(embedded.data) != referenced_assets:
                raise invalid()

        reqs = self.service.validate(template, pid, data.requirements)
        self.service.configure_enclosures(enclosures, configuration)
        if package.version == 2:
            original = package.working_document
            resolved = ResolvedDocument.model_validate({k: original[k] for k in ('document', 'snapshots')})
            if (resolved.document.project_id != (package.source_database_id or old)
                    or original['content_sha256'] != document_hash(resolved.document)):
                raise invalid()
            # Known pin kinds are deliberately explicit; unknown kinds cannot be
            # resolved by guessing a latest version or another catalog table.
            with self.db.sessions() as session:
                pin_tables = {'archetype': m.panel_archetype_versions, 'component': m.component_versions,
                    'product': m.product_versions, 'questionnaire': m.questionnaire_versions,
                    'rule_set': m.rule_set_versions, 'rule': m.design_rule_versions}
                for key, version in resolved.document.pins.catalog_versions.items():
                    table = pin_tables.get(key.split(':', 1)[0])
                    if table is None or session.scalar(select(table.c.id).where(table.c.id == identifier(version))) is None:
                        raise PersistenceError('PACKAGE_PIN_MISSING', 'A working-document catalog pin is unavailable.', 409)
                for version in resolved.document.pins.model_versions.values():
                    if session.scalar(select(m.cad_model_versions.c.id).where(m.cad_model_versions.c.id == identifier(version))) is None:
                        raise PersistenceError('PACKAGE_PIN_MISSING', 'A working-document model pin is unavailable.', 409)
                for component in (resolved.snapshots.cem.components if resolved.snapshots.cem else []):
                    for key, table in [('component_version_id', m.component_versions),
                                       ('product_version_id', m.product_versions), ('cad_model_version_id', m.cad_model_versions)]:
                        version = getattr(component, key)
                        if (key == 'component_version_id' and not version) or (version and
                                session.scalar(select(table.c.id).where(table.c.id == identifier(version))) is None):
                            raise PersistenceError('PACKAGE_PIN_MISSING', 'A working-document component pin is unavailable.', 409)
            doc = resolved.document
            doc.document_id, doc.project_id, doc.panel_id = str(uuid4()), pid, str(uuid4())
            doc.document_sequence, doc.lock_version, doc.base_revision_id = 0, 1, None
            doc.provenance = DocumentProvenance(origin='IMPORT', actor_id='local-user')
            for kind in ('requirements', 'cem', 'pdm', 'schematic'):
                snapshot = getattr(resolved.snapshots, kind)
                if snapshot is not None:
                    snapshot.project_id = pid
                    if kind != 'requirements':
                        snapshot.panel_id = doc.panel_id
                    if kind == 'cem' and snapshot.electrical_graph:
                        snapshot.electrical_graph.project_id = pid
                    getattr(doc.models, kind).sha256 = snapshot_sha256(snapshot)
            resolved = ResolvedDocument.model_validate(resolved.model_dump(mode='json'))
        else:
            resolved = DocumentService.empty_document({'id': pid, 'lock_version': 1}, template)
        source_document = {**resolved.model_dump(mode='json'), 'content_sha256': document_hash(resolved.document)}

        prepared = []
        revision_ids = {source['revision_id']: uuid4() for source in package.revisions if package.version == 2}
        for index, (source, historical) in enumerate(zip(package.revisions, templates)):
            cem, pdm = deepcopy(source['cem']), deepcopy(source['pdm'])
            # Change ownership fields only. Stable device/terminal/net/route IDs
            # and frozen schematic/CAD/BOM representations remain byte-identical.
            cem['project_id'] = pdm['project_id'] = pid
            cem['panel_id'] = pdm['panel_id'] = 'DB-' + pid
            pdm['id'] = 'PDM-' + pid
            cem['physical_design_id'] = pdm['id']
            if cem.get('electrical_graph'):
                cem['electrical_graph']['project_id'] = pid
            cem_model, pdm_model = CanonicalEngineeringModel(**cem), PhysicalDesignModel(**pdm)
            interfaces = [SimpleNamespace(component_id='PANEL_ROOT', terminal_ids=sorted({
                c[side + '_terminal'] for c in cem['connections'] for side in ('from', 'to')
                if c[side + '_component'] == 'PANEL_ROOT'}))]
            doc = SimpleNamespace(archetype='DB', project_id=pid, enclosure_interfaces=interfaces,
                pins=SimpleNamespace(validation_policy_version=source['manifest']['validation_policy_version']))
            validate_engineering_references(doc, SimpleNamespace(cem=cem_model, pdm=pdm_model, schematic=None))
            if pdm['validation_results'] or ValidationEngine().validate_pdm(pdm_model, cem_model):
                raise PersistenceError('INVALID_IMPORTED_DESIGN', 'An imported design fails physical validation; no project was imported.')
            saved_outputs = source.get('outputs', {})
            complete = bool(saved_outputs)
            answers = (deepcopy(saved_outputs['INPUTS_AND_PINS']['snapshot']['answers']) if complete else
                {r['id']: r['value'] for r in cem['requirements'] if r['value'] is not None})
            historical_reqs = self.service.validate(historical, pid, answers)
            manifest = deepcopy(source['manifest'])
            manifest.pop('output_manifest_sha256', None)
            for link in ('restored_from_revision_id', 'compatibility_converted_from_revision_id'):
                if link in manifest:
                    replacement = revision_ids.get(manifest.pop(link))
                    if replacement is not None:
                        manifest[link] = str(replacement)
            if not complete:
                manifest['legacy_package_limitations'] = 'CEM/PDM only; original outputs and artifacts were not included.'
            manifest.update(copied_from_project=old, copied_from_revision=source.get('revision_id'),
                input_sha256=content_hash({'requirements': answers, 'configuration': manifest.get('configuration', {})}))
            self.service.configure_enclosures(enclosures, manifest.get('configuration', {}))
            project = dict(id=pid, database_id=pid, lock_version=index + 1, configuration=manifest.get('configuration', {}))
            result = dict(cem=cem, pdm=pdm, validation_errors=[], **{
                key.lower(): deepcopy(saved_outputs[key]['snapshot']) if complete else None
                for key in ('SCHEMATIC', 'BOM', 'CAD')})
            if complete:
                validation = saved_outputs['VALIDATION']['snapshot']
                if validation != {'validation_errors': [], 'validation_policy': pdm['validation_policy']}:
                    raise invalid()
            files = [{k: ref[k] for k in FILE_FIELDS} for ref in source.get('artifacts', [])] if package.version == 2 else []
            # Exact original source snapshots/hashes survive ownership rebinding.
            # They are historical evidence, never interpreted as destination IDs.
            publication_source = {**deepcopy(source_document), 'portable_source': deepcopy(source)}
            prepared.append((project, historical, historical_reqs, answers, result, manifest, files,
                             publication_source, complete))

        # No input can cause a filesystem write before all checks above pass.
        # A later database failure can leave unreferenced verified content, as in
        # generation; existing/shared content is never removed or overwritten.
        for key, blob in embedded.data.items():
            self.assets.put(blob, key.rsplit('.', 1)[-1])
        publications = []
        for project, historical, historical_reqs, answers, result, manifest, files, source, complete in prepared:
            outputs = prepare_outputs(project, historical_reqs, answers, result, manifest, files,
                source, self.assets, project['lock_version'],
                revision_id=revision_ids.get(source['portable_source'].get('revision_id')))
            if not complete:
                model_manifest = {k: v for k, v in outputs.model_manifest.items() if k != 'output_manifest_sha256'}
                outputs = replace(outputs, complete=False, model_manifest=model_manifest,
                    revision_sha256=content_hash(dict(cem=outputs.hashes['CEM'], pdm=outputs.hashes['PDM'], manifest=model_manifest)))
            publications.append((project, historical, historical_reqs, answers, result, manifest, files, outputs))

        with self.db.sessions.begin() as session:
            repo = ProjectRepository(session)
            session.execute(insert(m.projects).values(id=pid, name=data.name, status='ACTIVE',
                archetype_version_id=template['archetype_version_id'], description=data.description, location=data.location))
            # The aggregate was fully validated/hashed before this transaction.
            doc = source_document['document']
            session.execute(insert(m.design_documents).values(id=doc['document_id'], project_id=pid,
                panel_id=doc['panel_id'], schema_version=doc['schema_version'], document_sequence=0,
                document=doc, content_sha256=source_document['content_sha256']))
            for kind, reference in doc['models'].items():
                if reference is not None:
                    session.execute(insert(m.design_document_snapshots).values(document_id=doc['document_id'],
                        model_kind=kind.upper(), schema_version=reference['schema_version'], sha256=reference['sha256'],
                        snapshot=source_document['snapshots'][kind]))
            for project, historical, historical_reqs, answers, result, manifest, files, outputs in publications:
                write_revision(session, project, historical, historical_reqs, answers, result,
                    manifest, files, project['lock_version'], outputs=outputs)
            row = repo.row(pid)
            repo.save_requirements(row, template, reqs, data.requirements)
            repo.touch(row, configuration=configuration, workspace=workspace)
            return repo.get(pid)

