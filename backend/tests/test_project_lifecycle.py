"""Project lifecycle integration against an isolated PostgreSQL database."""
from tests.historical_publication import seed_historical_revision, historical_design
from uuid import UUID
from tests.local_client import LocalClient as TestClient
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


def test_versioned_recovery_has_independent_clock_and_retains_old_base(api, postgres_database, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from app.services.project_service import ProjectService
    from app.services.orchestrator import DesignOrchestrator
    from app.services.cad_engine import CADEngine
    from app.services.schematic_engine import SchematicEngine
    from app.services.physical_routing import DuctRouter
    from tests.test_documents_api import request_for

    def forbidden(*args, **kwargs):
        raise AssertionError('Recovery invoked generation')

    for cls in (DesignOrchestrator, CADEngine, SchematicEngine, DuctRouter):
        monkeypatch.setattr(cls, '__init__', forbidden)
    monkeypatch.setattr(ProjectService, 'generate', forbidden)
    p = create(api)
    root = f"/api/projects/{p['id']}"
    document_path = f"/api/v1/projects/{p['id']}/document"
    base = ok(api.get(document_path))
    d = base['document']
    draft = {'schema_version': 2, 'baseDocument': {k: d[k] for k in
        ('document_id', 'document_sequence', 'schema_version')},
        'baseRevisionId': None, 'requirements': {'unfinished': '-'},
        'configuration': {}, 'workspace': {'editorTransforms': {}, 'schematicData': None}}
    body = {'expected_version': p['lock_version'], 'expected_recovery_version': 0, 'document': draft}
    # Save changes L/S first. Recovery still accepts and retains the older base.
    saved = ok(api.put(document_path, json=request_for(base)))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: api.put(root + '/recovery', json=body), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 409]
    winner = next(r.json() for r in responses if r.status_code == 200)
    assert next(r.json() for r in responses if r.status_code == 409)['error']['code'] == 'RECOVERY_CONFLICT'
    assert winner['lock_version'] == saved['document']['lock_version']
    assert winner['recovery'] == {**winner['recovery'], 'schema_version': 2,
        'recovery_sequence': 1, 'base_version': p['lock_version'], 'document': draft}
    assert ok(api.get(document_path)) == saved
    with TestClient(create_app(postgres_database)) as restarted:
        assert ok(restarted.get(root))['recovery'] == winner['recovery']
    # Another document Save leaves R and the raw incompatible draft unchanged.
    ok(api.put(document_path, json=request_for(saved, 230)))
    assert ok(api.get(root))['recovery'] == winner['recovery']
    cleared = ok(api.put(root + '/recovery', json={**body, 'expected_recovery_version': 1, 'document': None}))
    assert cleared['recovery_version'] == 2 and cleared['recovery'] is None
    assert ok(api.get(root + '/revisions')) == []
    for invalid in ({**draft, 'schema_version': 99},
                    {**draft, 'baseDocument': {**draft['baseDocument'], 'document_sequence': -1}}):
        assert api.put(root + '/recovery', json={**body, 'document': invalid}).status_code == 422


def test_duplicate_and_import_preserve_generated_history(api):
    p = create(api)
    design = historical_design(api, p['id'], expected_version=p['lock_version'])
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


def test_restore_adds_one_revision_preserving_all_original_hashes(api, postgres_database, monkeypatch):
    from sqlalchemy import select
    from app.persistence import models as m
    from app.persistence.assets import canonical_json
    from app.persistence.repositories import identifier, serial
    from app.services.project_service import ProjectService
    from tests.test_revision_reader import disable_generators

    p = create(api)
    service = ProjectService(postgres_database)
    first = seed_historical_revision(service, p['id'], {'num_feeders': 4}, p['lock_version'],
                             configuration={'enclosure_id': None})
    second = seed_historical_revision(service, p['id'], {'num_feeders': 5}, first['lock_version'])
    root = '/api/projects/' + p['id']
    tables = [m.project_revisions, m.cem_snapshots, m.pdm_snapshots,
              m.revision_output_manifests, m.revision_output_snapshots, m.generated_artifacts]

    def original_rows():
        with postgres_database.sessions() as session:
            return [canonical_json(serial([dict(row) for row in session.execute(select(table).where(
                (table.c.id if table is m.project_revisions else table.c.project_revision_id).in_(
                    [identifier(first['revision_id']), identifier(second['revision_id'])]))).mappings()]))
                for table in tables]

    before = original_rows()
    artifact_bytes = {a['url']: api.get(a['url']).content for a in first['artifacts']}
    disable_generators(monkeypatch)
    restored = ok(api.post(root + '/revisions/' + first['revision_id'] + '/restore',
        json={'expected_version': second['lock_version']}), 201)
    assert restored['revision_no'] == second['revision_no'] + 1
    assert restored['revision_id'] not in {first['revision_id'], second['revision_id']}
    assert restored['manifest']['restored_from_revision_id'] == first['revision_id']
    for field in ('cem', 'pdm', 'schematic', 'bom', 'cad', 'validation_errors'):
        assert restored[field] == first[field]
    with postgres_database.sessions() as session:
        parent = session.scalar(select(m.project_revisions.c.parent_revision_id).where(
            m.project_revisions.c.id == identifier(restored['revision_id'])))
    assert str(parent) == second['revision_id']
    assert original_rows() == before
    assert len(ok(api.get(root + '/revisions'))) == 3
    assert all(api.get(url).content == data for url, data in artifact_bytes.items())
    assert api.post(root + '/revisions/' + first['revision_id'] + '/restore',
                    json={'expected_version': second['lock_version']}).status_code == 409
    assert len(ok(api.get(root + '/revisions'))) == 3


def test_overlay_proposals_retain_workspace_recovery_and_history(api, postgres_database, monkeypatch):
    from app.services.project_service import ProjectService
    from tests.test_revision_reader import disable_generators

    p = create(api)
    design = seed_historical_revision(ProjectService(postgres_database), p['id'], {}, p['lock_version'])
    root = '/api/projects/' + p['id']
    part = design['pdm']['components'][0]
    workspace = {'editorTransforms': {part['cem_component_id']:
        {**part['position'], 'x': part['position']['x'] + 1, 'rotation_deg': 0}}}
    saved = ok(api.patch(root, json={'expected_version': design['lock_version'], 'workspace': workspace}))
    saved = ok(api.put(root + '/recovery', json={'expected_version': saved['lock_version'],
        'expected_recovery_version': saved['recovery_version'], 'document': {
            'requirements': {}, 'configuration': {}, 'workspace': workspace,
            'baseRevisionId': design['revision_id']}}))
    disable_generators(monkeypatch)
    request = dict(expected_version=saved['lock_version'], revision_id=design['revision_id'])
    blocked = ok(api.post(root + '/compatibility-proposal', json=request))
    assert blocked['status'] == 'BLOCKED' and not blocked['operations']
    # Explicit base selection/evidence makes a reviewable proposal, never a commit.
    proposal = ok(api.post(root + '/compatibility-proposal', json={**request, 'base': blocked['base']}))
    assert proposal['status'] == 'REVIEW_REQUIRED' and len(proposal['operations']) == 1
    recovery = ok(api.post(root + '/compatibility-proposal', json={**request, 'source': 'recovery'}))
    assert recovery['status'] == 'BLOCKED'  # revision ID alone is insufficient
    matching_recovery = ok(api.post(root + '/compatibility-proposal', json={**request,
        'source': 'recovery', 'base': blocked['base']}))
    assert matching_recovery['status'] == 'REVIEW_REQUIRED'
    assert proposal['original_workspace'] == saved['workspace']
    assert proposal['original_recovery'] == saved['recovery']
    assert ok(api.get(root)) == saved
    assert len(ok(api.get(root + '/revisions'))) == 1
    assert ok(api.get(root + '/design'))['snapshot_sha256'] == design['snapshot_sha256']
    assert api.post(root + '/compatibility-proposal', json={**request,
        'expected_version': design['lock_version']}).status_code == 409
    different_base = {**saved['recovery']['document'], 'baseRevisionId': 'another-revision'}
    changed = ok(api.put(root + '/recovery', json={'expected_version': saved['lock_version'],
        'expected_recovery_version': saved['recovery_version'], 'document': different_base}))
    mismatch = ok(api.post(root + '/compatibility-proposal', json={**request,
        'source': 'recovery', 'base': blocked['base']}))
    assert mismatch['status'] == 'BLOCKED' and not mismatch['operations']
    assert any(item['item'] == 'recovery.baseRevisionId' for item in mismatch['blocked'])
    assert ok(api.get(root)) == changed
