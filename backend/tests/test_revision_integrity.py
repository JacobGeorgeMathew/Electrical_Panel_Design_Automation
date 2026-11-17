"""Mutation guards, hostile persisted content and non-destructive audits."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, event, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.persistence import models as m
from app.persistence.assets import AssetStore, AssetUnavailable, content_hash
from app.persistence.audit import audit_assets, audit_revisions
from app.persistence.integrity import verify_revision_rows
from app.persistence.publication_guards import IMMUTABLE_TABLES, install_publication_guards
from app.persistence.repositories import PersistenceError, identifier
from app.persistence.revision_outputs import verify_outputs
from app.services.project_service import ProjectService
from tests.integrity_support import privileged_connection
from tests.test_postgres import create
from tests.test_revision_outputs import bundle, stored_bundle


@pytest.mark.parametrize('name', sorted(IMMUTABLE_TABLES))
def test_every_immutable_table_rejects_mutation_before_sql(name):
    engine = create_engine('sqlite://')
    install_publication_guards(engine)
    table = m.metadata.tables[name]
    column = next(iter(table.c))
    try:
        with engine.connect() as connection:
            for statement in (update(table).values({column: None}), delete(table),
                    pg_insert(table).values({column: None}).on_conflict_do_update(
                        index_elements=[column], set_={column: None})):
                with pytest.raises(PersistenceError) as caught:
                    connection.execute(statement)
                assert caught.value.code == 'IMMUTABLE_PUBLICATION'
                assert caught.value.status == 409
                assert name not in caught.value.message
    finally:
        engine.dispose()


def test_asset_put_never_clobbers_a_competing_publication(tmp_path, monkeypatch):
    assets = AssetStore(tmp_path)
    real_link = __import__('os').link

    def competing_link(source, destination):
        destination.write_bytes(b'competing-corrupt-data')
        return real_link(source, destination)

    monkeypatch.setattr('app.persistence.assets.os.link', competing_link)
    with pytest.raises(AssetUnavailable):
        assets.put(b'original', 'json')
    assert next(tmp_path.glob('sha256/*/*/*')).read_bytes() == b'competing-corrupt-data'
    assert not list(tmp_path.glob('sha256/*/*/.pending-*'))


def test_asset_keys_symlinks_io_errors_and_corrupt_republication(tmp_path, monkeypatch):
    assets = AssetStore(tmp_path)
    row = assets.put(b'original', 'json')
    path = assets.verified_path(row['storage_key'], row['sha256'], row['byte_size'])
    path.write_bytes(b'corrupt')
    with pytest.raises(AssetUnavailable):
        assets.put(b'original', 'json')
    assert path.read_bytes() == b'corrupt'
    for key in ('../private-secret', '/private-secret', row['storage_key'] + '\x00'):
        with pytest.raises(AssetUnavailable) as caught:
            assets.verified_path(key, row['sha256'])
        assert 'private-secret' not in str(caught.value)
    other = tmp_path / 'other'
    other.write_bytes(b'original')
    path.unlink()
    path.symlink_to(other)
    with pytest.raises(AssetUnavailable):
        assets.verified_path(row['storage_key'], row['sha256'])
    path.unlink()
    path.write_bytes(b'original')

    def denied(*args, **kwargs):
        raise PermissionError('/private-secret/storage')

    monkeypatch.setattr(Path, 'open', denied)
    assert assets.availability(row) == 'MISSING_OR_CORRUPT'
    with pytest.raises(AssetUnavailable) as caught:
        assets.verified_path(row['storage_key'], row['sha256'])
    assert 'private-secret' not in str(caught.value)


def test_asset_download_redacts_storage_adapter_errors(monkeypatch):
    from app.api import routes_assets

    def unavailable(*args):
        raise AssetUnavailable('/private-secret/storage')

    monkeypatch.setattr(routes_assets, 'asset_row', lambda *args: dict(
        generation_status='READY', storage_backend='LOCAL', storage_key='key', sha256='hash', byte_size=1))
    service = SimpleNamespace(assets=SimpleNamespace(verified_path=unavailable))
    with pytest.raises(PersistenceError) as caught:
        routes_assets.content(None, service, 'id', True)
    assert caught.value.status == 404 and caught.value.code == 'ASSET_UNAVAILABLE'
    assert 'private-secret' not in str(caught.value)


@pytest.mark.parametrize('tamper', ['schema', 'document_schema', 'document_hash',
    'source_sequence', 'artifact_field', 'artifact_duplicate', 'artifact_source',
    'artifact_status', 'artifact_owner', 'snapshot_bool_schema', 'malformed'])
def test_rehashed_hostile_bundles_fail_closed(bundle, tamper):
    prepared, assets, _ = bundle
    snapshots, artifacts = stored_bundle(prepared)
    manifest = deepcopy(prepared.manifest)
    if tamper == 'schema':
        manifest['schema_version'] = '2.0.0'
    elif tamper.startswith('document_'):
        source = snapshots['DOCUMENT']['snapshot']
        if tamper == 'document_schema':
            source['document']['schema_version'] = '2.0.0'
        else:
            source['content_sha256'] = '0' * 64
        snapshots['DOCUMENT']['sha256'] = content_hash(source)
        manifest['outputs']['DOCUMENT']['sha256'] = content_hash(source)
    elif tamper == 'source_sequence':
        manifest['source_document']['sequence'] += 1
    elif tamper == 'artifact_field':
        del manifest['artifacts'][0]['generator_version']
    elif tamper == 'artifact_duplicate':
        manifest['artifacts'] *= 2
    elif tamper == 'artifact_source':
        manifest['artifacts'][0]['source_model_sha256'] = artifacts[0]['source_model_sha256'] = '0'*64
    elif tamper == 'artifact_status':
        artifacts[0]['generation_status'] = 'PENDING'
    elif tamper == 'artifact_owner':
        artifacts[0]['project_revision_id'] = str(uuid4())
    elif tamper == 'snapshot_bool_schema':
        snapshots['CAD']['schema_version'] = True
        manifest['outputs']['CAD']['schema_version'] = True
    else:
        manifest['artifacts'] = [None]
    with pytest.raises(PersistenceError) as caught:
        verify_outputs(manifest, content_hash(manifest), snapshots, artifacts, assets)
    assert caught.value.code == 'REVISION_OUTPUT_INTEGRITY'
    assert str(caught.value) == 'Saved revision outputs are incomplete, corrupt or incompatible.'


@pytest.mark.parametrize('tamper', ['revision_schema', 'model_schema', 'bundle_schema',
    'source_column', 'owner_column', 'pins', 'anchor', 'legacy_model_schema',
    'revision_bool_schema', 'model_bool_schema'])
def test_revision_envelopes_and_pin_anchors_are_verified(bundle, tamper):
    prepared, assets, _ = bundle
    snapshots, files = stored_bundle(prepared)
    for file in files:
        file.update(generation_status='READY', project_revision_id=prepared.revision_id)
    source = prepared.manifest['source_document']
    revision = dict(id=prepared.revision_id, project_id=prepared.project_id,
        schema_version=1, model_manifest=deepcopy(prepared.model_manifest),
        content_sha256=prepared.revision_sha256)
    root = dict(schema_version='1.0.0', manifest=deepcopy(prepared.manifest),
        sha256=prepared.sha256, project_id=prepared.project_id,
        source_document_id=source['id'], source_document_sequence=source['sequence'],
        source_document_sha256=source['sha256'])
    rows = dict(revision=revision, models={k: deepcopy(snapshots[k]) for k in ('CEM', 'PDM')},
        bundle=root, snapshots=snapshots, files=files)
    assert not verify_revision_rows(rows, assets)[1]
    if tamper in {'revision_schema', 'revision_bool_schema'}:
        revision['schema_version'] = True if tamper == 'revision_bool_schema' else 2
    elif tamper in {'model_schema', 'legacy_model_schema', 'model_bool_schema'}:
        rows['models']['CEM']['schema_version'] = True if tamper == 'model_bool_schema' else 2
        if tamper == 'legacy_model_schema':
            rows.update(bundle=None, snapshots={})
            revision['model_manifest'].pop('output_manifest_sha256')
    elif tamper == 'bundle_schema':
        root['schema_version'] = '2.0.0'
    elif tamper == 'source_column':
        root['source_document_sequence'] += 1
    elif tamper == 'owner_column':
        root['project_id'] = str(uuid4())
    elif tamper == 'anchor':
        revision['model_manifest']['output_manifest_sha256'] = '0'*64
    else:
        snapshots['INPUTS_AND_PINS']['snapshot']['pins']['engine_version'] = 'tampered'
        digest = content_hash(snapshots['INPUTS_AND_PINS']['snapshot'])
        snapshots['INPUTS_AND_PINS']['sha256'] = digest
        root['manifest']['outputs']['INPUTS_AND_PINS']['sha256'] = digest
        root['sha256'] = content_hash(root['manifest'])
        revision['model_manifest']['output_manifest_sha256'] = root['sha256']
    revision['content_sha256'] = content_hash(dict(cem=rows['models']['CEM']['sha256'],
        pdm=rows['models']['PDM']['sha256'], manifest=revision['model_manifest']))
    with pytest.raises(PersistenceError):
        verify_revision_rows(rows, assets)


def test_runtime_guards_preserve_publications_and_allow_tombstones(api, postgres_database):
    db = postgres_database
    project = create(api)
    service = ProjectService(db)
    design = service.generate(project['id'], {'num_feeders': 4}, project['lock_version'])
    rid = identifier(design['revision_id'])
    with db.sessions() as session:
        requirement = session.scalar(select(m.project_requirements.c.id).where(
            m.project_requirements.c.project_revision_id == rid))
    attempts = [update(m.cem_snapshots).values(snapshot={}), delete(m.pdm_snapshots),
        update(m.component_versions).values(specification={}), delete(m.cad_assets),
        update(m.generated_artifacts).values(sha256='0'*64),
        update(m.project_requirements).where(m.project_requirements.c.id == requirement).values(value={}),
        delete(m.project_requirements).where(m.project_requirements.c.id == requirement),
        delete(m.requirement_sources).where(m.requirement_sources.c.requirement_id == requirement),
        delete(m.projects).where(m.projects.c.id == identifier(project['id']))]
    for statement in attempts:
        with pytest.raises(PersistenceError) as caught:
            with db.sessions.begin() as session:
                session.execute(statement)
        assert caught.value.code == 'IMMUTABLE_PUBLICATION'
    assert service.load_revision(project['id'])['snapshot_sha256'] == design['snapshot_sha256']
    # Existing save/recompute lifecycle remains supported after guard rejections.
    second = service.generate(project['id'], {'num_feeders': 5}, design['lock_version'])
    response = api.request('DELETE', '/api/projects/'+project['id'], json={'expected_version': second['lock_version']})
    assert response.status_code == 204, response.text
    with db.sessions() as session:
        assert session.scalar(select(m.projects.c.deleted_at).where(m.projects.c.id == identifier(project['id'])))
        assert session.scalar(select(m.cem_snapshots.c.sha256).where(m.cem_snapshots.c.project_revision_id == rid))
    assert audit_revisions(db)['complete'] >= 2


def test_jobs_can_finish_once_but_cannot_change_ready_content(api, postgres_database):
    db = postgres_database
    project = create(api)
    design = ProjectService(db).generate(project['id'], {'num_feeders': 4}, project['lock_version'])
    job = uuid4()
    with db.sessions.begin() as session:
        session.execute(insert(m.generated_artifacts).values(id=job,
            project_revision_id=identifier(design['revision_id']), artifact_type='CAD_PREVIEW',
            file_format='GLB', generator_name='test', generator_version='1', generation_status='PENDING',
            source_model_kind='PDM', source_model_sha256=content_hash(design['pdm'])))
        session.execute(update(m.generated_artifacts).where(m.generated_artifacts.c.id == job).values(
            generation_status='FAILED', error={'code': 'TEST'}))
    with pytest.raises(PersistenceError):
        with db.sessions.begin() as session:
            session.execute(update(m.generated_artifacts).where(m.generated_artifacts.c.id == job).values(
                generation_status='PENDING'))
    ready_job = uuid4()
    artifact = next(a for a in design['output_manifest']['artifacts'] if a['file_format'] == 'GLB')
    with db.sessions.begin() as session:
        session.execute(insert(m.generated_artifacts).values(id=ready_job,
            project_revision_id=identifier(design['revision_id']), artifact_type='CAD_PREVIEW',
            file_format='GLB', generator_name='test', generator_version='1', generation_status='PENDING',
            source_model_kind='PDM', source_model_sha256=content_hash(design['pdm'])))
    barrier = Barrier(2)

    def complete(_):
        barrier.wait(timeout=10)
        try:
            with db.sessions.begin() as session:
                session.execute(update(m.generated_artifacts).where(m.generated_artifacts.c.id == ready_job).values(
                    **{k: artifact[k] for k in ('storage_backend', 'storage_key', 'sha256', 'byte_size')},
                    generation_status='READY'))
            return 'READY'
        except PersistenceError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(complete, range(2))) == ['IMMUTABLE_PUBLICATION', 'READY']
    with db.sessions() as session:
        assert session.scalar(select(m.generated_artifacts.c.generation_status).where(
            m.generated_artifacts.c.id == ready_job)) == 'READY'


def test_read_and_audit_reject_tampering_without_deleting(api, postgres_database, monkeypatch):
    db = postgres_database
    project = create(api)
    service = ProjectService(db)
    design = service.generate(project['id'], {'num_feeders': 4}, project['lock_version'])
    rid = identifier(design['revision_id'])
    baseline = audit_revisions(db)
    with db.sessions() as session:
        snapshot = dict(session.execute(select(m.revision_output_snapshots).where(
            m.revision_output_snapshots.c.project_revision_id == rid,
            m.revision_output_snapshots.c.output_kind == 'SCHEMATIC')).mappings().one())
    predicate = (m.revision_output_snapshots.c.project_revision_id == rid,
                 m.revision_output_snapshots.c.output_kind == 'SCHEMATIC')
    try:
        with privileged_connection(db) as connection:
            connection.execute(update(m.revision_output_snapshots).where(*predicate).values(snapshot={'secret': '/private-secret'}))
        response = api.get('/api/projects/'+project['id']+'/design')
        assert response.status_code == 409 and 'REVISION_OUTPUT_INTEGRITY' in response.text
        assert 'private-secret' not in response.text
        report = audit_revisions(db)
        assert report['invalid_revisions'] == baseline['invalid_revisions'] + 1
        assert report['automatic_deletion'] is False
        assert 'private-secret' not in json.dumps(report)
        with db.sessions() as session:
            assert session.scalar(select(m.revision_output_snapshots.c.snapshot).where(*predicate)) == {'secret': '/private-secret'}
    finally:
        with privileged_connection(db) as connection:
            connection.execute(update(m.revision_output_snapshots).where(*predicate).values(**snapshot))
    artifact = design['output_manifest']['artifacts'][0]
    path = service.assets.verified_path(artifact['storage_key'], artifact['sha256'], artifact['byte_size'])
    original = path.read_bytes()
    orphan = service.assets.put(b'unreferenced-file', 'json')
    try:
        path.write_bytes(b'tampered /private-secret')
        assert api.get('/api/projects/'+project['id']+'/design').status_code == 409
        response = api.get('/api/artifacts/'+artifact['id']+'/content')
        assert response.status_code == 404 and 'private-secret' not in response.text
        assert audit_assets(db)['missing_or_corrupt'] >= 1
        # Content-addressed bytes can be shared by many historical revisions.
        assert audit_revisions(db)['invalid_revisions'] >= baseline['invalid_revisions'] + 1
        assert path.read_bytes() == b'tampered /private-secret'
        assert (service.assets.root / orphan['storage_key']).is_file()
    finally:
        path.write_bytes(original)
    # CLI runs the same read-only audits and returns a failure status for findings.
    from app.persistence import manage
    monkeypatch.setattr(manage, 'Database', lambda _: db)
    monkeypatch.setattr(db, 'close', lambda: None)
    monkeypatch.setattr('sys.argv', ['manage', 'audit-revisions'])
    with pytest.raises(SystemExit) as caught:
        manage.main()  # Frozen illustrative/storage-only fixtures are invalid.
    assert caught.value.code == 1


@pytest.mark.parametrize('tamper', ['schema', 'models'])
def test_audits_check_document_compatibility_and_only_read(api, postgres_database, tamper):
    # Observe only audit SQL, not the independent durable queue consumer.
    api.app.state.cad_executor.shutdown()
    db = postgres_database
    project = create(api)
    baseline = audit_revisions(db)
    with db.sessions() as session:
        original = dict(session.execute(select(m.design_documents).where(
            m.design_documents.c.project_id == identifier(project['id']))).mappings().one())
    changed = deepcopy(original['document'])
    if tamper == 'schema':
        changed['schema_version'] = 'unsupported-private-secret'
    else:
        changed['models'] = ['/private-secret']
    statements = []

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split()[0].upper())

    try:
        with privileged_connection(db) as connection:
            connection.execute(update(m.design_documents).where(m.design_documents.c.id == original['id']).values(
                document=changed, schema_version=changed['schema_version']))
        response = api.get('/api/v1/projects/'+project['id']+'/document')
        assert response.status_code == 409 and 'private-secret' not in response.text
        event.listen(db.engine, 'before_cursor_execute', observe)
        try:
            report = audit_revisions(db)
            audit_assets(db)
        finally:
            event.remove(db.engine, 'before_cursor_execute', observe)
        assert report['invalid_documents'] == baseline['invalid_documents'] + 1
        assert report['automatic_deletion'] is False
        assert statements and set(statements) == {'SELECT'}
    finally:
        with privileged_connection(db) as connection:
            connection.execute(update(m.design_documents).where(m.design_documents.c.id == original['id']).values(**original))
