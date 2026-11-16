"""Shared TS/Pydantic command fixtures, strict units and HTTP read contract."""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models.document_api import DocumentSave
from app.models.operations import OperationPreviewRequest, HistoryRequest
from app.main import create_app
from app.api.dependencies import get_document_service
from app.services.operations.history import history_view
from tests.test_document_contract import document_fixture

FIXTURE = Path(__file__).resolve().parents[2] / 'frontend/src/types/fixtures/operation-commands-v1.json'


def test_shared_fixture_and_discriminated_openapi():
    fixture = json.loads(FIXTURE.read_text())
    request = OperationPreviewRequest.model_validate(fixture['preview'])
    history = HistoryRequest.model_validate(fixture['history'])
    assert len(request.operations) == 7 and history.action == 'UNDO'
    assert request.operations[0].parameters.placement.position_mm.y == 200.25
    assert request.operations[5].parameters.conductor.cross_section_mm2 == 2.5
    assert request.operations[6].proposal_status == 'PROPOSED'
    app = FastAPI()

    @app.post('/history-contract')
    def contract(data: HistoryRequest):
        return data

    assert TestClient(app).post('/history-contract', json=fixture['history']).status_code == 200
    assert app.openapi()['components']['schemas']['HistoryRequest']['additionalProperties'] is False
    schema = create_app().openapi()['components']['schemas']
    variants = schema['OperationPreviewRequest']['properties']['operations']['items']['discriminator']['mapping']
    assert {op.type for op in request.operations} <= set(variants)
    assert schema['SnapshotPrecondition']['properties']['model_sha256']['additionalProperties']['anyOf'][1]['type'] == 'null'


@pytest.mark.parametrize('field,value', [('cross_section_mm2', 0), ('minimum_bend_radius_mm', float('nan')),
                                      ('insulation_diameter_mm', '4'), ('wire_class', 'L1')])
def test_conductor_contract_rejects_invalid_units_and_classes(field, value):
    body = json.loads(FIXTURE.read_text())['preview']
    body['operations'][5]['parameters']['conductor'][field] = value
    with pytest.raises(ValidationError):
        OperationPreviewRequest.model_validate(body)


def test_history_http_read_and_typed_topology_save():
    base = document_fixture()
    app = create_app()

    class Service:
        def operation_history(self, key):
            assert key == 'project-1'
            return history_view(base, [])

    app.dependency_overrides[get_document_service] = lambda: Service()
    response = TestClient(app).get('/api/v1/projects/project-1/document/operations/history')
    assert response.status_code == 200 and response.json()['undo_batch_ids'] == []
    body = dict(document_id=base.document.document_id, expected_version=3, expected_document_sequence=7,
        requirements=base.snapshots.requirements.model_dump(), configuration=dict(electrical_topology=dict(domains=[
            dict(component_id='QF001', terminal_id='OUT', supply_id='supply-1', role='L1')])))
    assert DocumentSave.model_validate(body).configuration == body['configuration']
    body['configuration']['electrical_topology']['domains'][0]['role'] = 'UNKNOWN'
    with pytest.raises(ValidationError):
        DocumentSave.model_validate(body)
