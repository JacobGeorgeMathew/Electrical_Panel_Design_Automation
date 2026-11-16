"""Version fences, immutable values and generator-free document persistence."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from sqlalchemy import func, select, update

from app.persistence import models as m


def create(api):
    response = api.post('/api/projects', json={'name': 'Working document'})
    assert response.status_code == 201, response.text
    return response.json()


def request_for(view, value=415):
    requirements = deepcopy(view['snapshots']['requirements'])
    requirements['items'] = [{'id': 'voltage', 'label': 'Voltage', 'value': value,
                              'unit': 'V', 'state': 'PROPOSED', 'source': 'USER'}]
    return dict(document_id=view['document']['document_id'],
                expected_version=view['document']['lock_version'],
                expected_document_sequence=view['document']['document_sequence'],
                requirements=requirements, configuration={})


def test_save_open_conflict_and_no_engines(api, postgres_database, monkeypatch):
    project = create(api)
    path = f"/api/v1/projects/{project['id']}/document"
    from app.services.project_service import ProjectService
    from app.services.orchestrator import DesignOrchestrator
    from app.services.cad_engine import CADEngine
    from app.services.schematic_engine import SchematicEngine
    from app.services.physical_routing import DuctRouter

    def forbidden(*args, **kwargs):
        raise AssertionError('Open/Save invoked an engineering engine')

    for cls in (DesignOrchestrator, CADEngine, SchematicEngine, DuctRouter):
        monkeypatch.setattr(cls, '__init__', forbidden)
    monkeypatch.setattr(ProjectService, 'generate', forbidden)
    monkeypatch.setattr(ProjectService, 'load_revision', forbidden)
    base = api.get(path).json()
    payload = request_for(base)
    losing = request_for(base, 230)
    losing_copy = deepcopy(losing)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda body: api.put(path, json=body), [payload, losing]))
    assert sorted(result.status_code for result in results) == [200, 409]
    winner = next(result.json() for result in results if result.status_code == 200)
    conflict = next(result.json() for result in results if result.status_code == 409)
    assert conflict['error']['code'] in {'REVISION_CONFLICT', 'DOCUMENT_CONFLICT'}
    assert losing == losing_copy
    assert api.get(path).json() == winner
    assert winner['document']['document_sequence'] == 1
    assert winner['document']['lock_version'] == project['lock_version'] + 1
    assert winner['document']['dirty_stages'] == base['document']['dirty_stages']
    unchanged = request_for(winner, winner['snapshots']['requirements']['items'][0]['value'])
    assert api.put(path, json=unchanged).json() == winner
    assert api.get(f"/api/projects/{project['id']}/revisions").json() == []
    with postgres_database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(m.design_document_snapshots).where(
            m.design_document_snapshots.c.document_id == base['document']['document_id'])) == 2


def test_document_errors_and_independent_state(api, postgres_database):
    project = create(api)
    key = project['id']
    path = f'/api/v1/projects/{key}/document'
    base = api.get(path).json()
    payload = request_for(base)
    for field, value in [('expected_document_sequence', 2), ('document_id', 'wrong-document')]:
        assert api.put(path, json={**payload, field: value}).status_code == 409
    for field, value in [('expected_version', 0), ('expected_document_sequence', True),
                         ('schema_version', '2.0.0'), ('snapshots', {}), ('display', {})]:
        assert api.put(path, json={**payload, field: value}).status_code == 422
    foreign = deepcopy(payload)
    foreign['requirements']['project_id'] = 'another-project'
    assert api.put(path, json=foreign).json()['error']['code'] == 'DOCUMENT_IDENTITY_MISMATCH'
    duplicate = deepcopy(payload)
    duplicate['requirements']['items'] *= 2
    assert api.put(path, json=duplicate).status_code == 422
    checkpoint = api.put(f'/api/projects/{key}/recovery', json={
        'expected_version': project['lock_version'], 'expected_recovery_version': 0,
        'document': {'requirements': {'unfinished': '-'}, 'configuration': {},
                     'workspace': {}, 'baseRevisionId': None}}).json()
    # Project metadata writes can advance L independently; reads return current L.
    renamed = api.patch(f'/api/projects/{key}', json={
        'expected_version': project['lock_version'], 'name': 'Renamed'}).json()
    assert api.get(path).json()['document']['lock_version'] == renamed['lock_version']
    assert api.put(path, json=payload).status_code == 409
    payload['expected_version'] = renamed['lock_version']
    assert api.put(path, json=payload).status_code == 200
    after = api.get(f'/api/projects/{key}').json()
    assert after['recovery'] == checkpoint['recovery']
    assert after['recovery_version'] == checkpoint['recovery_version']
    assert after['workspace'] == project['workspace']
    # Integrity errors are structured and disclose no internal data.
    with postgres_database.sessions.begin() as session:
        session.execute(update(m.design_documents).where(
            m.design_documents.c.id == base['document']['document_id']).values(content_sha256='0' * 64))
    assert api.get(path).json()['error']['code'] == 'DOCUMENT_INTEGRITY'
    assert api.get('/api/v1/projects/missing/document').status_code == 404


def test_versioned_document_openapi():
    from app.main import create_app
    schema = create_app().openapi()
    path = schema['paths']['/api/v1/projects/{project_id}/document']
    assert set(path) == {'get', 'put'}
    save = schema['components']['schemas']['DocumentSave']
    assert {'document_id', 'expected_version', 'expected_document_sequence', 'requirements'} <= set(save['required'])
    assert save['additionalProperties'] is False
