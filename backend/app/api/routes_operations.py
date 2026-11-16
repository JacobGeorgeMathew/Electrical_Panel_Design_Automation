"""Read-only operation previews; the client never supplies authoritative snapshots."""
from fastapi import APIRouter, Depends

from app.api.dependencies import get_document_service
from app.models.identity import StableID
from app.models.operations import OperationPreview, OperationPreviewRequest, OperationHistory

router = APIRouter(prefix='/api/v1/projects/{project_id}/document/operations', tags=['operations'])


@router.post('/preview', response_model=OperationPreview)
def preview(project_id: StableID, data: OperationPreviewRequest, service=Depends(get_document_service)):
    return service.preview_operations(project_id, data)


@router.get('/history', response_model=OperationHistory)
def history(project_id: StableID, service=Depends(get_document_service)):
    return service.operation_history(project_id)
