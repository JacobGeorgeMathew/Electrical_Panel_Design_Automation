"""Pure preview, request validation and isolated persistence invariants."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.dependencies import get_document_service
from app.main import create_app
from app.models.document import snapshot_sha256
from app.models.operations import OperationPreviewRequest
from app.persistence import models as m
from app.persistence.repositories import PersistenceError
from app.services.design_errors import DesignError
from app.services.operations.registry import preview_operations
from tests.test_document_contract import document_fixture
from app.models.requirements import QuestionSchema
from app.services.operations.engineering import EngineeringChoices


def fixture_choices(base):
    return EngineeringChoices(questions=(QuestionSchema(id=base.snapshots.requirements.items[0].id,
        label='Voltage', type='number', options=[230, 400, 415, 690]),))


def request_for(base, kind='MoveComponent'):
    model = 'pdm' if kind == 'MoveComponent' else 'requirements'
    return dict(batch_id='55555555-5555-4555-8555-555555555555',
        document_id=base.document.document_id, base_sequence=base.document.document_sequence,
        expected_version=base.document.lock_version, base_revision_id=base.document.base_revision_id,
        operations=[dict(operation_id='44444444-4444-4444-8444-444444444444', type=kind,
            origin=dict(kind='MANUAL', actor_id='local-user'), affected_models=[model],
            preconditions=dict(snapshot_sha256=getattr(base.document.models, model).sha256),
            target=(dict(cem_component_id='QF001', pdm_component_id='PDM-QF001') if model == 'pdm'
                    else dict(requirement_id=base.snapshots.requirements.items[0].id)),
            parameters=(dict(position_mm=dict(x=140, y=200.25, z=37.5)) if model == 'pdm'
                        else dict(value=230)))])


@pytest.mark.parametrize('kind', ['MoveComponent', 'UpdateRequirement'])
def test_pure_reproducible_preview(kind):
    base = document_fixture()
    before = base.model_dump(mode='json')
    request = OperationPreviewRequest.model_validate(request_for(base, kind))
    result = preview_operations(base, request, fixture_choices(base))
    assert result == preview_operations(base, request, fixture_choices(base))
    assert base.model_dump(mode='json') == before
    assert result.status == 'PREVIEW' and result.persisted is False
    assert result.before_content_sha256 != result.after_content_sha256
    assert len(result.changes) == 1
    assert all(check.status == 'UNRESOLVED' for check in result.required_checks)
    assert result.candidate.document.document_sequence == base.document.document_sequence
    assert result.candidate.document.lock_version == base.document.lock_version
    assert result.candidate.document.pins == base.document.pins
    assert result.candidate.snapshots.cem == base.snapshots.cem
    if kind == 'MoveComponent':
        assert result.candidate.snapshots.pdm.components[0].terminals[0]['x'] == 149
        assert result.candidate.snapshots.pdm.routes == base.snapshots.pdm.routes
    else:
        assert result.candidate.snapshots.requirements.items[0].state == 'PROPOSED'
        assert result.candidate.snapshots.pdm == base.snapshots.pdm


@pytest.mark.parametrize('change', ['type', 'id', 'uuid', 'extra', 'models', 'nan', 'string', 'rotation', 'proposal', 'duplicate', 'sequence'])
def test_malformed_requests(change):
    body = request_for(document_fixture())
    op = body['operations'][0]
    if change == 'type': op['type'] = 'ArbitraryPatch'
    elif change == 'id': op['target']['pdm_component_id'] = ' bad '
    elif change == 'uuid': op['operation_id'] = 'bad'
    elif change == 'extra': op['parameters']['raw_snapshot'] = {}
    elif change == 'models': op['affected_models'] = ['requirements']
    elif change == 'nan': op['parameters']['position_mm']['x'] = float('nan')
    elif change == 'string': op['parameters']['position_mm']['x'] = '10'
    elif change == 'rotation': op['parameters']['rotation_deg'] = 90
    elif change == 'proposal': op['origin']['kind'] = 'AI_PROPOSAL'
    elif change == 'duplicate': body['operations'] *= 2
    else: body['base_sequence'] = True
    with pytest.raises(ValidationError):
        OperationPreviewRequest.model_validate(body)


@pytest.mark.parametrize('field,value', [('document_id', 'other'), ('base_sequence', 8),
    ('expected_version', 4), ('base_revision_id', 'other')])
def test_stale_base(field, value):
    base = document_fixture()
    body = request_for(base)
    body[field] = value
    with pytest.raises(PersistenceError, match='Preview base changed'):
        preview_operations(base, OperationPreviewRequest.model_validate(body))


def test_ordered_preconditions_and_atomic_failure():
    base = document_fixture()
    before = deepcopy(base)
    body = request_for(base)
    first = preview_operations(base, OperationPreviewRequest.model_validate(body))
    second = deepcopy(body['operations'][0])
    second['operation_id'] = '66666666-6666-4666-8666-666666666666'
    second['parameters']['position_mm']['x'] = 150
    body['operations'].append(second)
    with pytest.raises(PersistenceError):
        preview_operations(base, OperationPreviewRequest.model_validate(body))
    assert base == before
    second['preconditions']['snapshot_sha256'] = first.changes[0].after_sha256
    result = preview_operations(base, OperationPreviewRequest.model_validate(body))
    assert len(result.changes) == 2
    second['target']['cem_component_id'] = 'missing'
    with pytest.raises(DesignError):
        preview_operations(base, OperationPreviewRequest.model_validate(body))
    assert base == before


def test_noop_and_uncomputed_target():
    base = document_fixture()
    body = request_for(base)
    body['operations'][0]['parameters']['position_mm'] = base.snapshots.pdm.components[0].position.model_dump()
    result = preview_operations(base, OperationPreviewRequest.model_validate(body))
    assert result.before_content_sha256 == result.after_content_sha256
    assert result.changes == result.required_checks == []
    body['operations'][0]['target']['pdm_component_id'] = 'missing'
    with pytest.raises(DesignError):
        preview_operations(base, OperationPreviewRequest.model_validate(body))


def test_http_contract_and_no_write_capability():
    base = document_fixture()
    app = create_app()

    class ReadOnlyService:
        def preview_operations(self, key, request):
            assert key == 'project-1'
            return preview_operations(base, request, fixture_choices(base))

    app.dependency_overrides[get_document_service] = ReadOnlyService
    client = TestClient(app)
    path = '/api/v1/projects/project-1/document/operations/preview'
    body = request_for(base)
    response = client.post(path, json=body)
    assert response.status_code == 200, response.text
    assert response.json() == client.post(path, json=body).json()
    body['operations'][0]['type'] = 'Unsupported'
    assert client.post(path, json=body).status_code == 422
    schema = app.openapi()
    request = schema['components']['schemas']['OperationPreviewRequest']
    assert request['additionalProperties'] is False
    assert request['properties']['operations']['items']['discriminator']['propertyName'] == 'type'


def test_shared_typescript_fixture():
    path = Path(__file__).resolve().parents[2] / 'frontend/src/types/fixtures/operation-preview-v1.json'
    body = json.loads(path.read_text())
    parsed = OperationPreviewRequest.model_validate(body)
    assert parsed.operations[0].parameters.position_mm.y == 200.25
    assert parsed.model_dump(mode='json', exclude_unset=True) == body


def test_preview_database_is_unchanged(api, postgres_database):
    project = api.post('/api/projects', json={'name': 'Preview only'}).json()
    path = f"/api/v1/projects/{project['id']}/document"
    base = api.get(path).json()
    requirements = deepcopy(base['snapshots']['requirements'])
    requirements['items'] = [dict(id='supply_voltage', label='Voltage', value=415, unit='V', state='PROPOSED', source='USER')]
    response = api.put(path, json=dict(document_id=base['document']['document_id'],
        expected_version=base['document']['lock_version'], expected_document_sequence=0,
        requirements=requirements, configuration={}))
    assert response.status_code == 200, response.text
    from app.models.document_api import DocumentView
    view = DocumentView.model_validate(response.json())
    body = request_for(view, 'UpdateRequirement')

    def counts():
        with postgres_database.sessions() as session:
            return [session.scalar(select(func.count()).select_from(table)) for table in
                    (m.design_documents, m.design_document_snapshots, m.project_revisions, m.generated_artifacts)]

    def stored_values():
        with postgres_database.sessions() as session:
            return [list(session.execute(select(table).order_by(*table.primary_key.columns)))
                    for table in (m.design_documents, m.design_document_snapshots,
                                  m.project_revisions, m.generated_artifacts)]

    before_counts = counts()
    before_values = stored_values()
    before_project = api.get(f"/api/projects/{project['id']}").json()
    first = api.post(path + '/operations/preview', json=body)
    assert first.status_code == 200, first.text
    assert first.json() == api.post(path + '/operations/preview', json=body).json()
    body['operations'][0]['target']['requirement_id'] = 'missing'
    assert api.post(path + '/operations/preview', json=body).status_code == 422
    assert api.get(path).json() == response.json()
    assert api.get(f"/api/projects/{project['id']}").json() == before_project
    assert counts() == before_counts
    assert stored_values() == before_values
    assert snapshot_sha256(view.snapshots.requirements) == view.document.models.requirements.sha256
