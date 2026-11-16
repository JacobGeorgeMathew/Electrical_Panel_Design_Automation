"""Shared, generator-free verification of detached revision rows."""
from sqlalchemy import select

from app.persistence import models as m
from app.persistence.assets import AssetUnavailable, content_hash
from app.persistence.repositories import PersistenceError
from app.persistence.revision_outputs import OUTPUT_KINDS, verify_outputs


def revision_rows(session, revision):
    rid = revision['id']
    models = {kind: session.execute(select(table).where(
        table.c.project_revision_id == rid)).mappings().first()
        for kind, table in [('CEM', m.cem_snapshots), ('PDM', m.pdm_snapshots)]}
    bundle = session.execute(select(m.revision_output_manifests).where(
        m.revision_output_manifests.c.project_revision_id == rid)).mappings().first()
    snapshots = {row['output_kind']: dict(row) for row in session.execute(
        select(m.revision_output_snapshots).where(
            m.revision_output_snapshots.c.project_revision_id == rid)).mappings()}
    files = [dict(row) for row in session.execute(select(m.generated_artifacts).where(
        m.generated_artifacts.c.project_revision_id == rid).order_by(
            m.generated_artifacts.c.created_at.desc())).mappings()]
    return dict(revision=dict(revision), models={k: dict(v) if v else None for k, v in models.items()},
                bundle=dict(bundle) if bundle else None, snapshots=snapshots, files=files)


def verify_revision_rows(rows, assets):
    """Check envelopes and anchors without interpreting installed engine defaults."""
    revision, models, bundle, snapshots, files = (
        rows[k] for k in ('revision', 'models', 'bundle', 'snapshots', 'files'))
    try:
        if type(revision['schema_version']) is not int or revision['schema_version'] != 1:
            raise ValueError('Unsupported revision schema')
        for row in models.values():
            if (row is None or type(row['schema_version']) is not int or row['schema_version'] != 1
                    or content_hash(row['snapshot']) != row['sha256']):
                raise ValueError('Unsupported or corrupt model snapshot')
        manifest = revision['model_manifest']
        if content_hash(dict(cem=models['CEM']['sha256'], pdm=models['PDM']['sha256'],
                             manifest=manifest)) != revision['content_sha256']:
            raise ValueError('Revision root differs')
        if bundle is None:
            if snapshots or manifest.get('output_manifest_sha256'):
                raise ValueError('Anchored bundle missing')
            outputs = {k: row['snapshot'] for k, row in models.items()}
        else:
            root = bundle['manifest']
            if (bundle['schema_version'] != '1.0.0'
                    or manifest.get('output_manifest_sha256') != bundle['sha256']
                    or root['project_revision_id'] != str(revision['id'])
                    or root['project_id'] != str(revision['project_id'])
                    or str(bundle['project_id']) != root['project_id']
                    or root['source_document'] != {'id': bundle['source_document_id'],
                        'sequence': bundle['source_document_sequence'], 'sha256': bundle['source_document_sha256']}):
                raise ValueError('Manifest envelope differs')
            verify_outputs(root, bundle['sha256'], snapshots, files, assets)
            if any(snapshots[k]['sha256'] != models[k]['sha256'] for k in models):
                raise ValueError('Model copies differ')
            pins = snapshots['INPUTS_AND_PINS']['snapshot']['pins']
            if pins != {k: v for k, v in manifest.items() if k != 'output_manifest_sha256'}:
                raise ValueError('Input pin manifest differs')
            outputs = {k: row['snapshot'] for k, row in snapshots.items()}
        # Later READY exports and legacy assets are also verified. Pending/failed
        # jobs are reported as such, and do not claim available content.
        for row in files:
            if row['generation_status'] == 'READY':
                if row['storage_backend'] != 'LOCAL':
                    raise ValueError('Unsupported storage')
                assets.verified_path(row['storage_key'], row['sha256'], row['byte_size'])
        return outputs, sorted(OUTPUT_KINDS - outputs.keys())
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError, AssetUnavailable, OSError):
        raise PersistenceError('REVISION_OUTPUT_INTEGRITY',
            'Saved revision outputs are incomplete, corrupt or incompatible.', 409) from None
