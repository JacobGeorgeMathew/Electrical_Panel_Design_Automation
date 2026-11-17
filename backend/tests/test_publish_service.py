"""Hostile placement fields and publication fences on an isolated database."""
from copy import deepcopy

import pytest
from sqlalchemy import update

from app.persistence import models as m
from app.services.document_service import DocumentService
from tests.test_postgres import checked, create
from tests.test_recompute_api import request_for


@pytest.fixture
def working(api, postgres_database):
    key = create(api)['id']
    path = f'/api/projects/{key}/design'
    base = DocumentService(postgres_database).load(key)
    proposal = checked(api.post(path+'/recompute', json=request_for(base)))
    checked(api.post(path+'/generation-proposal/accept', json=proposal['batch'],
        headers={'Idempotency-Key': 'publish-fixture'}))
    return key, path, DocumentService(postgres_database).load(key)


@pytest.mark.parametrize('route', ['validate-placement', 'reroute-placement'])
def test_placement_restores_dimensions_terminals_policy_and_hardware(api, working, route):
    key, path, base = working
    original = base.snapshots.pdm.model_dump(mode='json')
    hostile = deepcopy(original)
    hostile['components'][0].update(width=0, height=0, depth=0, heat_loss_watts=0,
        terminals=[], cad_model_version_id='foreign', rail_id='invented')
    hostile.update(validation_policy={'din_clearance_mm': 0, 'plate_clearance_mm': 0,
        'wire_clearance_mm': 0, 'thermal_density_limit_w_per_l': 999},
        enclosure_width=99999, total_heat_loss_watts=0, ducts=[], accessories=[])
    result = checked(api.post(path+'/'+route, json=hostile))
    restored = result['pdm']
    assert restored['components'] == original['components']
    for field in ('enclosure_width', 'total_heat_loss_watts', 'validation_policy', 'accessories'):
        assert restored[field] == original[field]
    assert not result['persisted']


@pytest.mark.parametrize('attack', ['foreign', 'duplicate', 'owner', 'shrink-boundary', 'erase-clearance'])
def test_hostile_placement_cannot_pass(api, working, attack):
    key, path, base = working
    hostile = base.snapshots.pdm.model_dump(mode='json')
    if attack == 'foreign':
        hostile['components'][0]['cem_component_id'] = 'FOREIGN'
    elif attack == 'duplicate':
        hostile['components'].append(deepcopy(hostile['components'][0]))
    elif attack == 'owner':
        hostile['project_id'] = 'FOREIGN'
    elif attack == 'shrink-boundary':
        c = hostile['components'][0]
        c['position']['x'] = hostile['enclosure_width'] - 1
        c['width'] = 0.01
        hostile['enclosure_width'] *= 100
    else:
        a, b = hostile['components'][:2]
        a['position'] = deepcopy(b['position'])
        a['width'] = a['height'] = 0
        hostile['validation_policy'] = {'din_clearance_mm': 0, 'plate_clearance_mm': 0}
    response = api.post(path+'/validate-placement', json=hostile)
    if attack in {'foreign', 'duplicate', 'owner'}:
        assert response.status_code == 409
        assert response.json()['error']['code'] in {'PROJECT_MISMATCH', 'COMPONENT_MISMATCH'}
    else:
        assert not checked(response)['is_valid']


def test_publish_stale_report_missing_outputs_and_legacy_bypass(api, postgres_database, working):
    from app.persistence.repositories import PersistenceError, ProjectRepository
    from app.services.publish_service import PublicationCache
    key, path, base = working
    evidence = checked(api.get(f'/api/projects/{key}/validation/working'))
    request = dict(**request_for(base), report_signature=evidence['report_signature'])
    for change, code in [({'expected_document_sequence': 0}, 'DOCUMENT_CONFLICT'),
                         ({'report_signature': '0'*64}, 'PUBLISH_REPORT_CONFLICT')]:
        response = api.post(path+'/publish', json={**request, **change})
        assert response.status_code == 409
        assert response.json()['error']['code'] == code
    cache = PublicationCache(postgres_database, base)
    with postgres_database.sessions.begin() as session:
        ProjectRepository(session).check_version(key, base.document.lock_version)
        cache.check_current(session, base.document.document_id)
        session.execute(update(m.document_stage_states).where(
            m.document_stage_states.c.document_id == base.document.document_id,
            m.document_stage_states.c.adapter == 'requirements').values(status='DIRTY'))
        with pytest.raises(PersistenceError) as conflict:
            cache.check_current(session, base.document.document_id)
        assert conflict.value.code == 'PUBLISH_STAGE_CONFLICT'
    response = api.post(path+'/publish', json=request)
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'PUBLISH_STAGE_STALE'
    with postgres_database.sessions.begin() as session:
        session.execute(update(m.document_stage_states).where(
            m.document_stage_states.c.document_id == base.document.document_id,
            m.document_stage_states.c.adapter == 'requirements').values(
                status='DIRTY', integrity='MISSING', result_id=None, output_signature=None, output_version=0))
    missing = api.post(path+'/publish', json=request)
    assert missing.status_code == 409
    assert missing.json()['error']['code'] == 'PUBLISH_STAGE_STALE'
    assert api.post(path+'/generate').status_code == 409
    assert DocumentService(postgres_database).load(key) == base
    assert checked(api.get(f'/api/projects/{key}/revisions')) == []
    saved = checked(api.put(f'/api/v1/projects/{key}/document', json=dict(**request_for(base),
        requirements=base.snapshots.requirements.model_dump(mode='json'), configuration=base.document.configuration)))
    assert saved['document']['document_sequence'] == base.document.document_sequence


def test_unresolved_report_never_authorizes_publish(api, working):
    key, path, base = working
    report = checked(api.get(f'/api/projects/{key}/validation/working'))
    assert report['aggregate']['required_status'] == 'UNRESOLVED'
    response = api.post(path+'/publish', json=dict(**request_for(base), report_signature=report['report_signature']))
    assert response.status_code == 409
    assert response.json()['error']['code'] in {'PUBLISH_VALIDATION_REQUIRED', 'PUBLISH_OUTPUTS_CHANGED', 'PUBLISH_STAGE_STALE'}
    assert checked(api.get(f'/api/projects/{key}/revisions')) == []


def test_empty_document_cannot_use_legacy_publication(api):
    key = create(api)['id']
    response = api.post(f'/api/projects/{key}/design/generate')
    assert response.status_code == 409
    assert response.json()['error']['code'] == 'GENERATION_PROPOSAL_REQUIRED'
    response = api.post(f'/api/projects/{key}/revisions', json=dict(expected_version=1, requirements={}))
    assert response.status_code == 409
    assert api.request('DELETE', f'/api/projects/{key}', json=dict(expected_version=1)).status_code == 204
    assert api.post(f'/api/projects/{key}/design/generate').status_code == 404


@pytest.mark.parametrize('changes', [dict(pdm={}), dict(report_signature=None),
    dict(expected_document_sequence=True), dict(expected_version=0)])
def test_publish_rejects_client_outputs_and_invalid_fences(api, postgres_database, changes):
    key = create(api)['id']
    base = DocumentService(postgres_database).load(key)
    body = dict(**request_for(base), report_signature='0'*64)
    response = api.post(f'/api/projects/{key}/design/publish', json={**body, **changes})
    assert response.status_code == 422
    assert DocumentService(postgres_database).load(key) == base


def test_failed_publish_preserves_a_prior_historical_revision(api, postgres_database, working):
    """Seed old history through the low-level writer, never a runtime bypass."""
    from app.services.project_service import ProjectService
    from app.persistence.revision_outputs import prepare_outputs
    from app.persistence.revisions import write_revision
    key, path, base = working
    service = ProjectService(postgres_database)
    source, requirements, result, manifest = service.generate(key, propose=True)
    project, template, *_ = service._inputs(key)
    answers = {r.id: r.value for r in requirements.items if r.value is not None}
    files = service.generate_files(result)
    outputs = prepare_outputs(project, requirements, answers, result, manifest, files,
        source, service.assets, base.document.lock_version)
    with postgres_database.sessions.begin() as session:
        saved = write_revision(session, project, template, requirements, answers, result, manifest,
            files, base.document.lock_version, outputs=outputs)
    before = checked(api.get(path))
    base = DocumentService(postgres_database).load(key)
    report = checked(api.get(f'/api/projects/{key}/validation/working'))
    response = api.post(path+'/publish', json=dict(**request_for(base), report_signature=report['report_signature']))
    assert response.status_code == 409
    after = checked(api.get(path))
    assert after['revision_id'] == saved['revision_id']
    assert after['snapshot_sha256'] == before['snapshot_sha256']
    assert len(checked(api.get(f'/api/projects/{key}/revisions'))) == 1
    unfinished = base.snapshots.requirements.model_dump(mode='json')
    unfinished['items'][0].update(value=None, state='MISSING')
    unfinished['is_valid'] = False
    draft = checked(api.put(f'/api/v1/projects/{key}/document', json=dict(**request_for(base),
        requirements=unfinished, configuration=base.document.configuration)))
    assert draft['document']['document_sequence'] == base.document.document_sequence + 1
    assert draft['document']['dirty_stages']
    assert not draft['snapshots']['requirements']['is_valid']
    assert checked(api.get(path))['revision_id'] == saved['revision_id']
