"""Project lifecycle integration against an isolated PostgreSQL database."""
from uuid import UUID
from fastapi.testclient import TestClient
from app.main import create_app


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def create(api, name='Factory board'):
    return ok(api.post('/api/projects', json={'name': name, 'description': 'Workshop supply',
        'location': 'Kochi', 'archetype': 'DB'}), 201)


def test_create_empty_save_reopen_after_backend_restart(api, postgres_database):
    p = create(api)
    UUID(p['id'])
    assert p['description'] == 'Workshop supply' and p['location'] == 'Kochi'
    assert p['current_revision_id'] is None
    assert ok(api.get(f"/api/projects/{p['id']}/revisions")) == []
    assert api.get(f"/api/projects/{p['id']}/design").status_code == 404
    saved = ok(api.patch(f"/api/projects/{p['id']}", json={'expected_version': p['lock_version'],
        'name': 'Renamed', 'requirements': {'num_feeders': 16}, 'workspace': {'editorTransforms': {}}}))
    with TestClient(create_app(postgres_database)) as restarted:
        reopened = ok(restarted.post(f"/api/projects/{p['id']}/open"))
        assert reopened['name'] == 'Renamed' and reopened['requirements']['num_feeders'] == 16
        assert reopened['lock_version'] == saved['lock_version']
        assert reopened['last_opened_at']
        assert p['id'] in [r['id'] for r in ok(restarted.get('/api/projects?recent=true&q=Workshop'))]
    assert api.patch(f"/api/projects/{p['id']}", json={'expected_version': p['lock_version'], 'name': 'Stale'}).status_code == 409


def test_duplicate_delete_and_package_roundtrip(api):
    p = create(api)
    duplicate = ok(api.post(f"/api/projects/{p['id']}/duplicate", json={'expected_version': p['lock_version'], 'name': 'Copy'}), 201)
    assert duplicate['id'] != p['id'] and duplicate['description'] == p['description']
    assert duplicate['current_revision_id'] is None
    exported = ok(api.get(f"/api/projects/{p['id']}/export"))
    imported = ok(api.post('/api/projects/import', json=exported), 201)
    assert imported['id'] not in {p['id'], duplicate['id']}
    assert imported['requirements'] == p['requirements']
    path = f"/api/projects/{duplicate['id']}"
    assert api.request('DELETE', path, json={'expected_version': duplicate['lock_version']+1}).status_code == 409
    assert api.request('DELETE', path, json={'expected_version': duplicate['lock_version']}).status_code == 204
    assert api.get(path).status_code == 404
    assert duplicate['id'] not in [r['id'] for r in ok(api.get('/api/projects'))]
    assert api.get(f"/api/projects/{p['id']}").status_code == 200


def test_recovery_is_durable_and_conflicting_tabs_cannot_overwrite(api, postgres_database):
    p = create(api)
    document = {'requirements': {'num_feeders': 'unfinished'}, 'configuration': {}, 'workspace': {'editorTransforms': {}, 'schematicData': None}, 'baseRevisionId': None}
    path = f"/api/projects/{p['id']}/recovery"
    request = {'expected_version': p['lock_version'], 'expected_recovery_version': 0, 'document': document}
    checkpoint = ok(api.put(path, json=request))
    assert checkpoint['lock_version'] == p['lock_version']
    assert api.put(path, json=request).status_code == 409
    assert api.patch(f"/api/projects/{p['id']}", json={'expected_version': p['lock_version'], 'expected_recovery_version': 0, 'requirements': {'num_feeders': 16}}).status_code == 409
    with TestClient(create_app(postgres_database)) as restarted:
        assert ok(restarted.get(f"/api/projects/{p['id']}"))['recovery']['document'] == document
    saved = ok(api.patch(f"/api/projects/{p['id']}", json={'expected_version': p['lock_version'], 'requirements': {'num_feeders': 16}}))
    assert saved['recovery'] is None
    assert api.put(path, json={**request, 'expected_recovery_version': checkpoint['recovery_version']}).status_code == 409


def test_duplicate_and_import_preserve_generated_history(api):
    p = create(api)
    design = ok(api.post(f"/api/projects/{p['id']}/revisions", json={'expected_version': p['lock_version'], 'requirements': {}}), 201)
    duplicate = ok(api.post(f"/api/projects/{p['id']}/duplicate", json={'expected_version': design['lock_version'], 'name': 'Engineered copy'}), 201)
    copied = ok(api.get(f"/api/projects/{duplicate['id']}/design"))
    assert copied['cem']['project_id'] == duplicate['id']
    assert copied['pdm']['project_id'] == duplicate['id']
    assert copied['cem']['components'] == design['cem']['components']
    assert copied['revision_id'] != design['revision_id'] and copied['artifacts']
    package = ok(api.get(f"/api/projects/{p['id']}/export"))
    imported = ok(api.post('/api/projects/import', json=package), 201)
    assert ok(api.get(f"/api/projects/{imported['id']}/design"))['pdm']['project_id'] == imported['id']
    package['revisions'][0]['cem']['panel_id'] = 'tampered'
    assert api.post('/api/projects/import', json=package).status_code == 422
    assert api.request('DELETE', f"/api/projects/{duplicate['id']}", json={'expected_version': copied['lock_version']}).status_code == 204
    assert api.get(f"/api/projects/{p['id']}/design").status_code == 200


def test_rename_preserves_recovery_and_invalid_packages_are_atomic(api):
    p=create(api)
    checkpoint=ok(api.put(f"/api/projects/{p['id']}/recovery",json={'expected_version':p['lock_version'],
        'expected_recovery_version':0,'document':{'requirements':{'num_feeders':16},'configuration':{},'workspace':{},'baseRevisionId':None}}))
    renamed=ok(api.patch(f"/api/projects/{p['id']}",json={'expected_version':p['lock_version'],'name':'Renamed with draft'}))
    assert renamed['recovery']==checkpoint['recovery']
    before={r['id'] for r in ok(api.get('/api/projects'))}
    package=ok(api.get(f"/api/projects/{p['id']}/export"))
    package['revisions']=[{'invalid':True}]
    assert api.post('/api/projects/import',json=package).status_code==422
    assert {r['id'] for r in ok(api.get('/api/projects'))}==before
    assert api.post(f"/api/projects/{p['id']}/duplicate",json={'expected_version':renamed['lock_version'],'name':'   '}).status_code==422
