"""Prepare complete publication bundles before opening the revision transaction.

The legacy revision digest remains unchanged in meaning. Its model manifest pins
the independent complete-output manifest digest; neither digest is a backfill of
legacy history. Asset bytes are verified here, never in the database writer.
"""
from copy import deepcopy
from dataclasses import dataclass
import math
from uuid import uuid4

from sqlalchemy import insert, select
from pydantic import ValidationError

from app.persistence import models as m
from app.persistence.assets import AssetUnavailable, content_hash
from app.persistence.repositories import PersistenceError, identifier
from app.models.document import ResolvedDocument
from app.persistence.documents import document_hash

OUTPUT_KINDS = frozenset({'DOCUMENT', 'REQUIREMENTS', 'CEM', 'PDM', 'SCHEMATIC',
                          'BOM', 'CAD', 'VALIDATION', 'INPUTS_AND_PINS'})
ARTIFACT_FIELDS = frozenset({'id', 'artifact_type', 'file_format', 'storage_backend',
    'storage_key', 'sha256', 'byte_size', 'generator_name', 'generator_version',
    'source_model_kind', 'source_model_sha256'})
ASSET_FORMATS = {'GLB': 'glb', 'JSON': 'json', 'PY': 'py', 'STEP': 'step',
                 'FCSTD': 'fcstd', 'PDF': 'pdf'}


@dataclass(frozen=True)
class PreparedOutputs:
    revision_id: object
    project_id: str
    expected_version: int
    source: dict
    snapshots: dict
    hashes: dict
    manifest: dict
    sha256: str
    model_manifest: dict
    revision_sha256: str
    files: list
    dependencies: list
    transforms: dict
    bounds: dict
    complete: bool = True


def transform(position, angle=0):
    half = math.radians(angle) / 2
    return {'translation_mm': [position[k] for k in ('x', 'y', 'z')],
            'quaternion_xyzw': [0, 0, math.sin(half), math.cos(half)]}


def prepare_outputs(project, requirements, answers, result, manifest, files, source, assets,
                    expected_version, *, revision_id=None):
    """Detach and hash exact engine representations, inputs/pins and artifact metadata.

    DOCUMENT captures the source aggregate and its resolved values, not a claim
    that the current generation endpoint has installed outputs in working state.
    REQUIREMENTS captures the validated inputs actually used for this generation.
    """
    if expected_version is None:
        raise ValueError('Publication requires an explicit version fence.')
    if result['validation_errors'] or result['pdm']['validation_results']:
        raise PersistenceError('INVALID_PUBLICATION', 'Physical violations block publication.', 409)
    rid = revision_id or uuid4()
    source = deepcopy(source)
    model_manifest = deepcopy(manifest)
    model_manifest.pop('output_manifest_sha256', None)
    model_manifest.update(configuration=deepcopy(project.get('configuration', {})),
                          saved_lock_version=expected_version + 1)
    snapshots = deepcopy({
        'DOCUMENT': source,
        'REQUIREMENTS': requirements.model_dump(mode='json'),
        'CEM': result['cem'], 'PDM': result['pdm'],
        'SCHEMATIC': result['schematic'], 'BOM': result['bom'], 'CAD': result['cad'],
        'VALIDATION': {'validation_errors': result['validation_errors'],
                       'validation_policy': result['pdm']['validation_policy']},
        'INPUTS_AND_PINS': {'answers': answers, 'configuration': project.get('configuration', {}),
                            'pins': model_manifest},
    })
    files = deepcopy(files)
    for file in files:
        file.setdefault('id', uuid4())
        assets.verified_path(file['storage_key'], file['sha256'], file['byte_size'])
    hashes = {kind: content_hash(value) for kind, value in snapshots.items()}
    doc = source['document']
    project_id = project['database_id']
    if doc['project_id'] != project_id:
        raise ValueError('Source document belongs to a different project.')
    bundle = dict(schema_version='1.0.0', project_revision_id=str(rid), project_id=project_id,
        source_document={'id': doc['document_id'], 'sequence': doc['document_sequence'],
                         'sha256': source['content_sha256']},
        outputs={kind: {'schema_version': 1, 'sha256': digest} for kind, digest in hashes.items()},
        artifacts=[{**file, 'id': str(file['id']), 'source_model_kind': 'PDM',
                    'source_model_sha256': hashes['PDM']} for file in files])
    digest = content_hash(bundle)
    model_manifest['output_manifest_sha256'] = digest
    revision_digest = content_hash({'cem': hashes['CEM'], 'pdm': hashes['PDM'], 'manifest': model_manifest})
    routes_hash = content_hash(result['pdm']['routes'])
    dependencies = [
        ('REQUIREMENTS', 'project', 'CEM', 'design', 'DERIVES', content_hash(answers), hashes['CEM']),
        ('CEM', 'design', 'PDM', 'layout', 'DERIVES', hashes['CEM'], hashes['PDM']),
        ('PDM', 'layout', 'ROUTING', 'routes', 'DERIVES', hashes['PDM'], routes_hash),
        ('ROUTING', 'routes', 'CAD', 'assembly', 'DERIVES', routes_hash, hashes['PDM']),
    ]
    dependencies += [('PARAMETER', 'ENCLOSURE.' + code, 'PDM', 'layout', 'GEOMETRY_INPUT',
                      content_hash(value), hashes['PDM'])
                     for code, value in project.get('configuration', {}).get('enclosure_parameters', {}).items()]
    dependencies += [('COMPONENT_VERSION', c['component_version_id'], 'CEM', c['id'],
                      'SELECTED_SPECIFICATION', content_hash(c['component_version_id']), hashes['CEM'])
                     for c in result['cem']['components']]
    pdm = snapshots['PDM']
    transforms = {('BACKPLATE', 'BACKPLATE'): transform({axis: pdm['mounting_plate_' + axis] for axis in ('x', 'y', 'z')})}
    for kind in ('rails', 'ducts', 'busbars', 'accessories', 'components'):
        for item in pdm.get(kind, []):
            transforms[(kind, item['id'])] = transform(item.get('position', item), item.get('rotation_deg', 0))
    bounds = {p['id']: {'min': [p['position'][k] for k in ('x', 'y', 'z')],
                       'max': [p['position'][k] + p[dimension]
                               for k, dimension in zip(('x', 'y', 'z'), ('width', 'height', 'depth'))]}
              for p in pdm['components']}
    return PreparedOutputs(rid, project_id, expected_version, source, snapshots, hashes,
                           bundle, digest, model_manifest, revision_digest, files, dependencies, transforms, bounds)


def write_outputs(session, prepared):
    """Insert only precomputed JSON and references in the caller's transaction."""
    if not prepared.complete:
        # A v1 package never contained frozen outputs. Preserve that absence;
        # only explicit compatibility conversion may create new representations.
        return
    source = prepared.manifest['source_document']
    row = session.execute(select(m.design_documents).where(
        m.design_documents.c.project_id == identifier(prepared.project_id)).with_for_update()).mappings().first()
    if (row is None or row['id'] != source['id'] or row['document_sequence'] != source['sequence']
            or row['content_sha256'] != source['sha256']):
        raise PersistenceError('DOCUMENT_CONFLICT',
            'Working document changed during publication. Retain local edits and reload.', 409)
    session.execute(insert(m.revision_output_manifests).values(
        project_revision_id=prepared.revision_id, project_id=identifier(prepared.project_id),
        schema_version='1.0.0', source_document_id=source['id'],
        source_document_sequence=source['sequence'], source_document_sha256=source['sha256'],
        manifest=prepared.manifest, sha256=prepared.sha256))
    for kind, snapshot in prepared.snapshots.items():
        session.execute(insert(m.revision_output_snapshots).values(
            project_revision_id=prepared.revision_id, output_kind=kind, schema_version=1,
            snapshot=snapshot, sha256=prepared.hashes[kind]))


def verify_outputs(manifest, digest, snapshots, artifacts, assets):
    """Verify a stored complete bundle, including each original artifact's bytes.

    Additional asynchronous exports are outside this publication manifest. This
    function deliberately performs no generation and must run outside write UoWs.
    """
    try:
        if manifest['schema_version'] != '1.0.0' or content_hash(manifest) != digest:
            raise ValueError('Manifest digest or schema differs')
        if set(snapshots) != OUTPUT_KINDS or set(manifest['outputs']) != OUTPUT_KINDS:
            raise ValueError('Incomplete output set')
        for kind, row in snapshots.items():
            ref = manifest['outputs'][kind]
            if (type(row['schema_version']) is not int or row['schema_version'] != 1
                    or type(ref['schema_version']) is not int
                    or ref != {'schema_version': 1, 'sha256': row['sha256']}):
                raise ValueError('Snapshot reference differs')
            if content_hash(row['snapshot']) != row['sha256']:
                raise ValueError('Snapshot digest differs')
        source = snapshots['DOCUMENT']['snapshot']
        resolved = ResolvedDocument.model_validate({k: source[k] for k in ('document', 'snapshots')})
        doc = resolved.document
        if (doc.project_id != manifest['project_id']
                or source['content_sha256'] != document_hash(doc)
                or manifest['source_document'] != {'id': doc.document_id,
                    'sequence': doc.document_sequence, 'sha256': source['content_sha256']}):
            raise ValueError('Source document differs')
        stored = {str(row['id']): row for row in artifacts}
        if len(stored) != len(artifacts):
            raise ValueError('Duplicate artifact rows')
        seen = set()
        for ref in manifest['artifacts']:
            if set(ref) != ARTIFACT_FIELDS or not identifier(ref['id']) or ref['id'] in seen:
                raise ValueError('Invalid artifact reference')
            seen.add(ref['id'])
            row = stored[ref['id']]
            if any(str(row[key]) != str(value) for key, value in ref.items()):
                raise ValueError('Artifact metadata differs')
            if (row.get('generation_status', 'READY') != 'READY'
                    or str(row.get('project_revision_id', manifest['project_revision_id'])) != manifest['project_revision_id']
                    or ref['source_model_kind'] != 'PDM'
                    or ref['source_model_sha256'] != snapshots['PDM']['sha256']
                    or ref['storage_backend'] != 'LOCAL'
                    or ASSET_FORMATS.get(ref['file_format']) != ref['storage_key'].rsplit('.', 1)[-1]):
                raise ValueError('Artifact source or status differs')
            assets.verified_path(row['storage_key'], row['sha256'], row['byte_size'])
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError, ValidationError, AssetUnavailable, OSError):
        raise PersistenceError('REVISION_OUTPUT_INTEGRITY',
            'Saved revision outputs are incomplete, corrupt or incompatible.', 409) from None
