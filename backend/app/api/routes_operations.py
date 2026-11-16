"""Operation transport; clients supply intents, never authoritative snapshots."""
from fastapi import APIRouter, Depends, Header

from app.api.dependencies import get_document_service
from app.models.identity import StableID
from app.models.operations import OperationPreview, OperationPreviewRequest, OperationHistory, HistoryRequest

router = APIRouter(prefix='/api/v1/projects/{project_id}/document/operations', tags=['operations'])


@router.post('/preview', response_model=OperationPreview)
def preview(project_id: StableID, data: OperationPreviewRequest, service=Depends(get_document_service)):
    return service.preview_operations(project_id, data)


@router.get('/history', response_model=OperationHistory)
def history(project_id: StableID, service=Depends(get_document_service)):
    return service.operation_history(project_id)


@router.post('/commit')
def commit(project_id: StableID, data: OperationPreviewRequest,
           idempotency_key: str = Header(alias='Idempotency-Key'), service=Depends(get_document_service)):
    return service.commit_operations(project_id, data, idempotency_key)


@router.post('/history')
def apply_history(project_id: StableID, data: HistoryRequest,
                  idempotency_key: str = Header(alias='Idempotency-Key'), service=Depends(get_document_service)):
    return service.apply_history(project_id, data, idempotency_key)
