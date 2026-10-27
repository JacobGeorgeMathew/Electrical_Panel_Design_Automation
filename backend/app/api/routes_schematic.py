from fastapi import APIRouter,Depends
from app.api.dependencies import get_service
router=APIRouter(prefix='/api/projects/{project_id}/schematic',tags=['schematic'])
@router.get('')
def get_schematic(project_id:str,service=Depends(get_service)):
    return service.load_revision(project_id)['schematic']
