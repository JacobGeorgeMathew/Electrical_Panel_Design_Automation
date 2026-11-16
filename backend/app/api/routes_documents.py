from fastapi import APIRouter, Depends

from app.api.dependencies import get_document_service
from app.models.document_api import DocumentSave, DocumentView

router = APIRouter(prefix='/api/v1/projects/{project_id}/document', tags=['documents'])


@router.get('', response_model=DocumentView)
def load_document(project_id: str, service=Depends(get_document_service)):
    return service.load(project_id)


@router.put('', response_model=DocumentView)
def save_document(project_id: str, data: DocumentSave, service=Depends(get_document_service)):
    return service.save(project_id, data)
