"""Thin command HTTP bindings delegate validation/persistence to the service."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_document_service
from app.api.routes_operations import router
from app.persistence.documents import document_hash
from tests.test_document_contract import document_fixture
from tests.test_operations import request_for


def test_commit_and_history_transport_require_key_and_delegate_typed_intents():
    calls = []

    class Service:
        def commit_operations(self, project, request, key):
            calls.append((project, request, key))
            return {'status': 'COMMITTED'}

        def apply_history(self, project, request, key):
            calls.append((project, request, key))
            return {'status': 'COMMITTED'}

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_document_service] = Service
    base = document_fixture()
    body = request_for(base)
    root = '/api/v1/projects/project-1/document/operations'
    with TestClient(app) as client:
        assert client.post(root + '/commit', json=body).status_code == 422
        assert not calls
        result = client.post(root + '/commit', json=body, headers={'Idempotency-Key': 'retry-key'})
        assert result.status_code == 200
        assert calls[-1][0] == 'project-1'
        assert calls[-1][1].document_id == base.document.document_id
        assert calls[-1][2] == 'retry-key'
        history = {key: value for key, value in body.items() if key != 'operations'}
        history.update(operation_id='66666666-6666-4666-8666-666666666666',
                       before_content_sha256=document_hash(base.document), action='UNDO',
                       target_batch_id=body['batch_id'], origin={'kind': 'MANUAL', 'actor_id': 'local-user'})
        result = client.post(root + '/history', json=history, headers={'Idempotency-Key': 'undo-key'})
        assert result.status_code == 200
        assert calls[-1][1].action == 'UNDO'
        assert calls[-1][2] == 'undo-key'
