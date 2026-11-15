from fastapi import APIRouter,Depends
from app.api.dependencies import get_service
from app.persistence.repositories import PersistenceError
router=APIRouter(prefix='/api/projects/{project_id}/schematic',tags=['schematic'])
@router.get('')
def get_schematic(project_id:str,revision_id:str|None=None,service=Depends(get_service)):
    design=service.load_revision(project_id,revision_id)
    if design['schematic'] is None:
        raise PersistenceError('REVISION_OUTPUT_MISSING','This legacy revision has no saved schematic. Explicitly convert it to a new revision.',409)
    return design['schematic']
