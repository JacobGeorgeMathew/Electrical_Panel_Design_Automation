from fastapi import APIRouter,Depends
from app.api.dependencies import get_service
router=APIRouter(prefix='/api/projects/{project_id}/layout',tags=['layout'])
@router.get('')
def get_layout(project_id:str,service=Depends(get_service)):
    return service.load_revision(project_id)['pdm']
