"""Portable publications: isolated installation, hostile inputs and atomicity."""
from tests.historical_publication import seed_historical_revision
import asyncio
import base64
from copy import deepcopy
from dataclasses import replace
import hashlib
from uuid import uuid4

import pytest
from fastapi import Request
from tests.local_client import LocalClient as TestClient
from sqlalchemy import event, func, select

from app.main import create_app
from app.models.api import ProjectImport
from app.persistence import models as m
from app.persistence.assets import AssetStore, AssetUnavailable, canonical_json, content_hash
from app.persistence.import_legacy import import_legacy
from app.persistence.manage import initialize
from app.persistence.repositories import PersistenceError, identifier
from app.services.project_lifecycle import ProjectLifecycle
from app.services.project_package import (EmbeddedAssets, MAX_ASSET, bounded_json,
    check_asset, package_hash, read_project_package)
from app.services.project_service import ProjectService
from tests.test_design_document_storage import isolated_database
from tests.test_project_lifecycle import create, ok
from tests.test_revision_reader import disable_generators
from tests.test_revision_outputs import read_bundle


def entry(data=b'portable artifact', extension='glb'):
    digest = hashlib.sha256(data).hexdigest()
    return dict(storage_key=f'sha256/{digest[:2]}/{digest[2:4]}/{digest}.{extension}',
        sha256=digest, byte_size=len(data), data_base64=base64.b64encode(data).decode('ascii'))


@pytest.mark.parametrize('path', ['../escape.py', '/tmp/escape.py', 'C:\\escape.py',
    'sha256/aa/bb/' + 'a'*64 + '.py', 'sha256/aa/../escape.py', 'https://example.com/a.glb'])
def test_unsafe_and_noncanonical_paths_are_rejected(path):
    value = entry()
    value['storage_key'] = path
    with pytest.raises(PersistenceError):
        EmbeddedAssets([value])


def test_embedded_assets_reject_corruption_duplicates_and_limits(monkeypatch):
    from app.services import project_package as packages
    value = entry()
    EmbeddedAssets([value]).verified_path(value['storage_key'], value['sha256'], value['byte_size'])
    for changed in ({**value, 'data_base64': 'not base64'}, {**value, 'byte_size': 0},
                    {**value, 'sha256': '0'*64}, {**value, 'byte_size': MAX_ASSET + 1},
                    {**value, 'byte_size': True}, {**value, 'file_path': '/private/secret'}):
        with pytest.raises(PersistenceError):
            EmbeddedAssets([changed])
    with pytest.raises(PersistenceError):
        EmbeddedAssets([value, value])
    with pytest.raises(AssetUnavailable):
        EmbeddedAssets([]).verified_path(value['storage_key'], value['sha256'], value['byte_size'])
    monkeypatch.setattr(packages, 'MAX_ASSETS_BYTES', value['byte_size'] - 1)
    with pytest.raises(PersistenceError) as caught:
        EmbeddedAssets([value])
    assert caught.value.status == 413


def test_managed_put_rejects_symlink_escape(tmp_path):
    root, outside = tmp_path / 'assets', tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    (root / 'sha256').symlink_to(outside, target_is_directory=True)
    with pytest.raises(AssetUnavailable):
        AssetStore(root).put(b'never written outside storage', 'py')
    assert list(outside.iterdir()) == []


def test_request_stream_is_bounded_before_json_parsing(monkeypatch):
    from app.services import project_package as packages
    monkeypatch.setattr(packages, 'MAX_PACKAGE', 16)

    async def run(chunks):
        messages = iter(chunks)
        async def receive():
            return next(messages)
        return await read_project_package(Request({'type': 'http'}, receive))

    with pytest.raises(PersistenceError) as caught:
        asyncio.run(run([{'type': 'http.request', 'body': b'X'*12, 'more_body': True},
                         {'type': 'http.request', 'body': b'X'*12, 'more_body': False}]))
    assert caught.value.status == 413
    for body in (b'{malformed', b'NaN', b'[]'):
        with pytest.raises(PersistenceError):
            asyncio.run(run([{'type': 'http.request', 'body': body, 'more_body': False}]))
    nested = {}
    for _ in range(65):
        nested = {'child': nested}
    with pytest.raises(PersistenceError) as caught:
        bounded_json(nested)
    assert caught.value.status == 413


@pytest.fixture
def publication(api, postgres_database):
    project = create(api, 'Portable source')
    service = ProjectService(postgres_database)
    first = seed_historical_revision(service, project['id'], {'num_feeders': 4}, project['lock_version'])
    second = service.restore(project['id'], first['revision_id'], first['lock_version'])
    return service, project, first, second


def test_package_preserves_frozen_outputs_in_an_isolated_installation(publication, api, postgres_database, tmp_path, monkeypatch):
    service, project, first, second = publication
    lifecycle = ProjectLifecycle(service)
    package = lifecycle.export(project['id'])
    assert package['version'] == 2 and package['sha256'] == package_hash(package)
    assert len(package['revisions']) == 2 and package['assets']
    originals = {a['sha256']: api.get(a['url']).content for a in first['artifacts']}
    disable_generators(monkeypatch)
    # Provision only another fixture-owned database; never the configured DB.
    with isolated_database(replace(postgres_database.settings, asset_root=tmp_path / 'destination-assets')) as destination:
        initialize(destination)
        import_legacy(destination)
        with TestClient(create_app(destination)) as target:
            imported = ok(target.post('/api/projects/import', json=package), 201)
            assert imported['id'] != project['id']
            copied_history = ok(target.get('/api/projects/' + imported['id'] + '/revisions'))
            assert len(copied_history) == 2
            copied_ids = {r['id'] for r in copied_history}
            assert not copied_ids & {first['revision_id'], second['revision_id']}
            for summary, source in zip(reversed(copied_history), package['revisions']):
                copied = ok(target.get('/api/projects/' + imported['id'] + '/revisions/' + summary['id']))
                assert copied['cem']['project_id'] == copied['pdm']['project_id'] == imported['id']
                assert copied['cem']['components'] == source['cem']['components']
                if 'restored_from_revision_id' in source['manifest']:
                    assert copied['manifest']['restored_from_revision_id'] in copied_ids
                    assert copied['manifest']['restored_from_revision_id'] != source['manifest']['restored_from_revision_id']
                for key in ('SCHEMATIC', 'CAD', 'BOM', 'VALIDATION'):
                    assert copied['output_manifest']['outputs'][key] == source['output_manifest']['outputs'][key]
                for artifact in copied['artifacts']:
                    assert target.get(artifact['url']).content == originals[artifact['sha256']]
                    assert artifact['id'] not in {a['id'] for a in first['artifacts'] + second['artifacts']}
                _, snapshots, _ = read_bundle(destination, identifier(summary['id']))
                retained = snapshots['DOCUMENT']['snapshot']['portable_source']
                assert canonical_json(retained) == canonical_json(source)
                assert all(content_hash(row['snapshot']) == row['sha256'] for row in retained['outputs'].values())
            # Export/duplicate continue working after import; no source filesystem
            # is needed and provenance/output hashes remain independently verifiable.
            exported_again = ok(target.get('/api/projects/' + imported['id'] + '/export'))
            ok(target.post('/api/projects/import', json=exported_again), 201)
            duplicate = ok(target.post('/api/projects/' + imported['id'] + '/duplicate', json={
                'expected_version': imported['lock_version'], 'name': 'Portable duplicate'}), 201)
            before = read_bundle(destination, identifier(imported['current_revision_id']))
            assert target.request('DELETE', '/api/projects/' + imported['id'],
                json={'expected_version': imported['lock_version']}).status_code == 204
            assert read_bundle(destination, identifier(imported['current_revision_id'])) == before
            design = ok(target.get('/api/projects/' + duplicate['id'] + '/design'))
            assert all(target.get(a['url']).content == originals[a['sha256']] for a in design['artifacts'])


def test_invalid_packages_leave_no_project_or_asset_writes(publication, api, postgres_database, monkeypatch):
    service, project, _, _ = publication
    package = ProjectLifecycle(service).export(project['id'])

    def state():
        with postgres_database.sessions() as session:
            return tuple(session.scalar(select(func.count()).select_from(table)) for table in
                (m.projects, m.project_revisions, m.generated_artifacts, m.design_documents))

    before = state()
    written = []
    monkeypatch.setattr(AssetStore, 'put', lambda *args, **kwargs: written.append(args) or pytest.fail('Unverified input wrote an asset'))
    cases = []
    for change in ('corrupt', 'missing', 'path', 'version', 'pin', 'output', 'source', 'reference', 'format', 'document', 'shape'):
        bad = deepcopy(package)
        if change == 'corrupt':
            bad['assets'][0]['data_base64'] = base64.b64encode(b'corrupt').decode('ascii')
        elif change == 'missing':
            bad['assets'] = []
        elif change == 'path':
            bad['assets'][0]['storage_key'] = '../../private/secrets.py'
        elif change == 'version':
            bad['version'] = 987
        elif change == 'pin':
            bad['revisions'][-1]['manifest']['hardware_component_versions']['missing'] = str(uuid4())
            source = bad['revisions'][-1]
            source['sha256'] = content_hash({k: source[k] for k in ('cem', 'pdm', 'manifest')})
            source['revision_sha256'] = content_hash(dict(cem=source['cem_sha256'], pdm=source['pdm_sha256'], manifest=source['manifest']))
        elif change == 'output':
            bad['revisions'][-1]['outputs']['CAD']['snapshot'] = {'tampered': True}
        elif change == 'source':
            bad['source_project_id'] = str(uuid4())
        elif change == 'reference':
            bad['revisions'][-1]['artifacts'][0]['project_revision_id'] = str(uuid4())
        elif change == 'format':
            bad['revisions'][-1]['artifacts'][-1]['file_format'] = 'EXE'
        elif change == 'document':
            bad['working_document']['content_sha256'] = '0'*64
        elif change == 'shape':
            bad['working_document']['snapshots'] = 'hostile nested shape'
        bad['sha256'] = package_hash(bad)
        cases.append(bad)
    cases.append({**package, 'sha256': '0'*64})
    for bad in cases:
        response = api.post('/api/projects/import', json=bad)
        assert response.status_code in (409, 422), response.text
        assert set(response.json()) == {'error'}
        assert not any(secret in response.text for secret in ('secrets.py', '/home/', 'SELECT ', 'postgresql'))
        assert state() == before
    assert not written


def test_import_database_failure_rolls_back_the_entire_project(publication, api, postgres_database):
    service, project, _, _ = publication
    package = ProjectImport(**ProjectLifecycle(service).export(project['id']))
    with postgres_database.sessions() as session:
        before = {table.name: session.scalar(select(func.count()).select_from(table))
            for table in m.metadata.sorted_tables}

    def fail(conn, cursor, statement, parameters, context, executemany):
        if context.isinsert and context.compiled.statement.table is m.generated_artifacts:
            raise RuntimeError('injected after artifact insert')

    event.listen(postgres_database.engine, 'after_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            ProjectLifecycle(service).import_project(package)
    finally:
        event.remove(postgres_database.engine, 'after_cursor_execute', fail)
    with postgres_database.sessions() as session:
        assert {table.name: session.scalar(select(func.count()).select_from(table))
            for table in m.metadata.sorted_tables} == before


def test_v1_import_is_explicitly_incomplete_and_never_regenerates(publication, api, monkeypatch):
    service, project, first, _ = publication
    package = ProjectLifecycle(service).export(project['id'])
    legacy = {k: v for k, v in package.items() if k not in ('assets', 'working_document', 'sha256', 'source_database_id')}
    legacy['version'] = 1
    legacy['revisions'] = [{k: source[k] for k in ('cem', 'pdm', 'manifest', 'sha256')} for source in package['revisions']]
    disable_generators(monkeypatch)
    imported = ok(api.post('/api/projects/import', json=legacy), 201)
    design = ok(api.get('/api/projects/' + imported['id'] + '/design'))
    assert design['output_status'] == 'MISSING_OUTPUTS'
    assert design['cad'] is design['schematic'] is design['bom'] is None
    assert not design['artifacts']
    assert design['manifest']['legacy_package_limitations']
    assert design['cem']['components'] == first['cem']['components']
    # Legacy absence survives v2 transport as absence, never synthesized output.
    exported = ok(api.get('/api/projects/' + imported['id'] + '/export'))
    again = ok(api.post('/api/projects/import', json=exported), 201)
    assert ok(api.get('/api/projects/' + again['id'] + '/design'))['output_status'] == 'MISSING_OUTPUTS'


def test_import_errors_are_redacted_and_cors_rejects_unknown_origin(api):
    for body in (b'{', b'{"private-secret":123}', b'NaN'):
        response = api.post('/api/projects/import', content=body, headers={'Content-Type': 'application/json'})
        assert response.status_code == 422 and 'private-secret' not in response.text
    response = api.options('/api/projects/import', headers={'Origin': 'https://untrusted.invalid',
        'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Content-Type'})
    assert response.status_code == 400 and 'access-control-allow-origin' not in response.headers


def test_package_preserves_unpublished_working_requirements(api, monkeypatch):
    from tests.test_documents_api import request_for
    project = create(api, 'Unpublished input')
    path = '/api/v1/projects/' + project['id'] + '/document'
    saved = ok(api.put(path, json=request_for(ok(api.get(path)), 230)))
    disable_generators(monkeypatch)
    package = ok(api.get('/api/projects/' + project['id'] + '/export'))
    imported = ok(api.post('/api/projects/import', json=package), 201)
    copy = ok(api.get('/api/v1/projects/' + imported['id'] + '/document'))
    assert copy['snapshots']['requirements']['items'] == saved['snapshots']['requirements']['items']
    assert copy['snapshots']['requirements']['project_id'] == imported['id']
    assert copy['document']['document_id'] != saved['document']['document_id']
    assert copy['document']['panel_id'] != saved['document']['panel_id']
    assert copy['document']['document_sequence'] == 0
    assert imported['current_revision_id'] is None


def test_export_refuses_missing_original_assets(publication, monkeypatch):
    service, project, _, _ = publication

    def unavailable(*args, **kwargs):
        raise AssetUnavailable('/private/details must not escape')

    monkeypatch.setattr(AssetStore, 'verified_path', unavailable)
    with pytest.raises(PersistenceError) as caught:
        ProjectLifecycle(service).export(project['id'])
    assert caught.value.code == 'PACKAGE_ASSET_UNAVAILABLE'
    assert '/private/' not in caught.value.message


def test_package_openapi_retains_a_typed_request_body():
    schema = create_app().openapi()
    request = schema['paths']['/api/projects/import']['post']['requestBody']
    assert request['required']
    assert request['content']['application/json']['schema']['$ref'].endswith('/ProjectImport')
    assert 'assets' in schema['components']['schemas']['ProjectImport']['properties']
