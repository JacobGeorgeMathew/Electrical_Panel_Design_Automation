"""Read-only operation previews; the client never supplies authoritative snapshots."""
from fastapi import APIRouter, Depends

from app.api.dependencies import get_document_service
from app.models.identity import StableID
from app.models.operations import OperationPreview, OperationPreviewRequest
from app.services.operations.registry import preview_operations

router = APIRouter(prefix='/api/v1/projects/{project_id}/document/operations', tags=['operations'])


@router.post('/preview', response_model=OperationPreview)
def preview(project_id: StableID, data: OperationPreviewRequest, service=Depends(get_document_service)):
    # DocumentService.load closes the read transaction before preview begins.
    return preview_operations(service.load(project_id), data)
