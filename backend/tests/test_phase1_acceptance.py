"""Independent P1 lifecycle acceptance across working and published state."""
from copy import deepcopy
from hashlib import sha256

from app.persistence.repositories import identifier
from app.services import project_service
from app.services.orchestrator import DesignOrchestrator
from app.services.physical_routing import DuctRouter
from tests.test_project_lifecycle import create, ok
from tests.test_revision_outputs import read_bundle
from tests.test_revision_reader import disable_generators


def test_document_lifecycle_keeps_current_and_historical_outputs_frozen(
        api, postgres_database, monkeypatch):
    project = create(api, 'P1 acceptance')
    root = '/api/projects/' + project['id']
    document_path = '/api/v1/projects/' + project['id'] + '/document'
    initial = ok(api.get(document_path))
    assert project['current_revision_id'] is None
    assert ok(api.get(root + '/revisions')) == []

    first = ok(api.post(root + '/revisions', json={
        'expected_version': project['lock_version'], 'requirements': {'num_feeders': 4}}), 201)
    base = ok(api.get(document_path))
    draft = {'schema_version': 2,
             'baseDocument': {k: base['document'][k] for k in
                              ('document_id', 'document_sequence', 'schema_version')},
             'baseRevisionId': first['revision_id'], 'requirements': {'num_feeders': 'unfinished'},
             'configuration': {}, 'workspace': {'editorTransforms': {}}}

    def forbidden(*args, **kwargs):
        raise AssertionError('Save/recovery/read invoked generation or routing')

    with monkeypatch.context() as context:
        disable_generators(context)
        context.setattr(DesignOrchestrator, '__init__', forbidden)
        context.setattr(DuctRouter, '__init__', forbidden)
        context.setattr(project_service.ProjectService, 'generate', forbidden)
        p = ok(api.get(root))
        checkpoint_body = {'expected_version': p['lock_version'],
                           'expected_recovery_version': p['recovery_version'], 'document': draft}
        checkpoint = ok(api.put(root + '/recovery', json=checkpoint_body))
        assert api.put(root + '/recovery', json=checkpoint_body).status_code == 409
        assert ok(api.get(document_path)) == base
        assert ok(api.post(root + '/open'))['recovery'] == checkpoint['recovery']

        # Applying recovered inputs to a Save is explicit; incomplete raw inputs
        # stay in recovery until the caller supplies a supported document value.
        requirements = deepcopy(base['snapshots']['requirements'])
        requirements['items'] = [{'id': 'num_feeders', 'label': 'Feeders', 'value': 5,
                                  'state': 'PROPOSED', 'source': 'USER'}]
        save_body = {'document_id': base['document']['document_id'],
                     'expected_version': base['document']['lock_version'],
                     'expected_document_sequence': base['document']['document_sequence'],
                     'requirements': requirements, 'configuration': {}}
        saved = ok(api.put(document_path, json=save_body))
        assert api.put(document_path, json=save_body).status_code == 409
        assert saved['document']['document_id'] == initial['document']['document_id']
        assert saved['document']['panel_id'] == initial['document']['panel_id']
        assert saved['document']['document_sequence'] == base['document']['document_sequence'] + 1
        assert saved['content_sha256'] != base['content_sha256']
        assert ok(api.get(root))['recovery'] == checkpoint['recovery']
        assert ok(api.get(root + '/design'))['snapshot_sha256'] == first['snapshot_sha256']
        assert len(ok(api.get(root + '/revisions'))) == 1
        cleared = ok(api.put(root + '/recovery', json={**checkpoint_body,
            'expected_recovery_version': checkpoint['recovery_version'], 'document': None}))
        assert cleared['recovery'] is None

    # Publish with a changed installed engine pin, then make every computation
    # entry point unavailable before reading either publication.
    monkeypatch.setattr(project_service, 'ENGINE_VERSION', 'p1-acceptance-engine-change')
    second = ok(api.post(root + '/revisions', json={
        'expected_version': saved['document']['lock_version'],
        'requirements': {'num_feeders': 5}}), 201)
    assert second['manifest']['engine_version'] != first['manifest']['engine_version']
    assert second['revision_id'] != first['revision_id']
    assert second['revision_no'] == first['revision_no'] + 1
    assert second['output_manifest']['source_document']['sha256'] == saved['content_sha256']
    originals = {r['revision_id']: read_bundle(postgres_database, identifier(r['revision_id']))
                 for r in (first, second)}
    original_bytes = {}
    for revision in (first, second):
        for artifact in revision['artifacts']:
            response = api.get(artifact['url'])
            assert response.status_code == 200
            assert sha256(response.content).hexdigest() == artifact['sha256']
            original_bytes[artifact['sha256']] = response.content

    disable_generators(monkeypatch)
    monkeypatch.setattr(DesignOrchestrator, '__init__', forbidden)
    monkeypatch.setattr(DuctRouter, '__init__', forbidden)
    monkeypatch.setattr(project_service.ProjectService, 'generate', forbidden)
    for source, path, historical in ((second, '/design', False),
                                     (first, '/revisions/' + first['revision_id'], True)):
        frozen = ok(api.get(root + path))
        assert frozen['is_non_current'] is historical
        assert frozen['is_input_stale'] is historical
        assert frozen['is_version_incompatible']
        assert frozen['output_status'] == 'COMPLETE' and not frozen['missing_outputs']
        for field in ('cem', 'pdm', 'schematic', 'bom', 'cad', 'validation_errors',
                      'snapshot_sha256', 'output_manifest', 'output_manifest_sha256'):
            assert frozen[field] == source[field]
        for artifact in frozen['artifacts']:
            assert api.get(artifact['url']).content == original_bytes[artifact['sha256']]

    restored = ok(api.post(root + '/revisions/' + first['revision_id'] + '/restore', json={
        'expected_version': second['lock_version']}), 201)
    assert restored['revision_no'] == second['revision_no'] + 1
    assert restored['revision_id'] not in originals
    for field in ('cem', 'pdm', 'schematic', 'bom', 'cad', 'validation_errors'):
        assert restored[field] == first[field]
    assert api.post(root + '/revisions/' + first['revision_id'] + '/restore', json={
        'expected_version': second['lock_version']}).status_code == 409

    package = ok(api.get(root + '/export'))
    imported = ok(api.post('/api/projects/import', json=package), 201)
    duplicate = ok(api.post(root + '/duplicate', json={
        'expected_version': restored['lock_version'], 'name': 'P1 acceptance copy'}), 201)
    assert len({project['id'], imported['id'], duplicate['id']}) == 3
    source_revision_ids = {r['id'] for r in ok(api.get(root + '/revisions'))}
    source_artifact_ids = {a['id'] for r in package['revisions'] for a in r['artifacts']}
    destination_documents = []
    for destination in (imported, duplicate):
        target = '/api/projects/' + destination['id']
        history = ok(api.get(target + '/revisions'))
        assert len(history) == 3 and not source_revision_ids & {r['id'] for r in history}
        document = ok(api.get('/api/v1/projects/' + destination['id'] + '/document'))
        destination_documents.append(document['document']['document_id'])
        assert document['document']['panel_id'] != initial['document']['panel_id']
        copied = ok(api.get(target + '/design'))
        assert copied['cem']['project_id'] == copied['pdm']['project_id'] == destination['id']
        assert copied['cem']['components'] == first['cem']['components']
        assert copied['pdm']['routes'] == first['pdm']['routes']
        for kind in ('SCHEMATIC', 'BOM', 'CAD', 'VALIDATION'):
            assert copied['output_manifest']['outputs'][kind] == first['output_manifest']['outputs'][kind]
        for artifact in copied['artifacts']:
            assert artifact['id'] not in source_artifact_ids
            assert api.get(artifact['url']).content == original_bytes[artifact['sha256']]
    assert len({initial['document']['document_id'], *destination_documents}) == 3

    assert api.request('DELETE', root, json={
        'expected_version': second['lock_version']}).status_code == 409
    assert api.request('DELETE', root, json={
        'expected_version': restored['lock_version']}).status_code == 204
    assert api.get(root).status_code == 404
    assert project['id'] not in {r['id'] for r in ok(api.get('/api/projects'))}
    for rid, bundle in originals.items():
        assert read_bundle(postgres_database, identifier(rid)) == bundle
    assert all(api.get(a['url']).content == original_bytes[a['sha256']]
               for a in first['artifacts'])
    assert api.get('/api/projects/' + duplicate['id'] + '/design').status_code == 200
