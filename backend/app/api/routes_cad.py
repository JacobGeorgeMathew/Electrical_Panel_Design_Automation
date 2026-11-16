from fastapi import APIRouter,Depends
from app.api.dependencies import get_service,get_session
from app.api.routes_assets import asset_row
from app.models.api import CadJobInput,ArtifactView
from app.persistence.repositories import CatalogRepository,ProjectRepository,PersistenceError,identifier
from app.services.revision_reader import RevisionReader
from app.services.project_service import ENGINE_VERSION
from app.persistence import models as m
from sqlalchemy import select

router=APIRouter(prefix='/api/projects/{project_id}',tags=['cad'])

@router.get('/cad')
def get_cad_geometry(project_id:str,revision_id:str|None=None,service=Depends(get_service)):
    design=service.load_revision(project_id,revision_id)
    if design['cad'] is None:
        raise PersistenceError('REVISION_OUTPUT_MISSING','This legacy revision has no saved CAD output. Explicitly convert it to a new revision.',409)
    return design['cad']

@router.get('/cad/freecad-script')
def get_freecad_script(project_id:str,revision_id:str|None=None,service=Depends(get_service)):
    return RevisionReader(service.db,service.assets,ENGINE_VERSION).freecad_script(project_id,revision_id)

@router.get('/artifacts',response_model=list[ArtifactView])
def artifacts(project_id:str,service=Depends(get_service)):
    return service.list_artifacts(project_id)

@router.post('/cad-generation',status_code=202)
def queue_generation(project_id:str,data:CadJobInput,service=Depends(get_service)):
    return service.queue_artifact(project_id,data.file_format,data.expected_version)

@router.get('/cad-generation/{job_id}',response_model=ArtifactView)
def generation_status(project_id:str,job_id:str,service=Depends(get_service),session=Depends(get_session)):
    project=ProjectRepository(session).row(project_id)
    row=asset_row(session,job_id,True)
    belongs=session.scalar(select(m.project_revisions.c.id).where(m.project_revisions.c.id==row['project_revision_id'],m.project_revisions.c.project_id==project['id']))
    if not belongs: raise PersistenceError('ASSET_NOT_FOUND','Job was not found in this project.',404)
    return CatalogRepository(session,service.assets).asset_dto(row,True)
