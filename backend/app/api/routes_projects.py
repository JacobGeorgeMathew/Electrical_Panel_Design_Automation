from fastapi import APIRouter, Depends, Query
from app.api.dependencies import get_service, get_session
from app.models.api import ProjectCreate, ProjectUpdate, ProjectView, ExpectedVersion, AnswerSave, DesignPackage, RevisionCreate, RecoverySave, ProjectDuplicate, ProjectImport
from app.persistence.repositories import ProjectRepository
from app.persistence.repositories import identifier,serial
from app.persistence import models as m
from sqlalchemy import select
from fastapi import Response
from app.services.project_lifecycle import ProjectLifecycle

router=APIRouter(prefix='/api/projects',tags=['projects'])

@router.get('',response_model=list[ProjectView])
def list_projects(page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),q:str=Query('',max_length=200),recent:bool=False,session=Depends(get_session)):
    return ProjectRepository(session).list(page,page_size,q,recent)

@router.post('',response_model=ProjectView,status_code=201)
def create_project(data:ProjectCreate,service=Depends(get_service)):
    return service.create(data)

@router.post('/import',response_model=ProjectView,status_code=201)
def import_project(data:ProjectImport,service=Depends(get_service)):
    return ProjectLifecycle(service).import_project(data)

@router.post('/{project_id}/open',response_model=ProjectView)
def opened(project_id:str,service=Depends(get_service)):
    return ProjectLifecycle(service).opened(project_id)

@router.delete('/{project_id}',status_code=204)
def delete_project(project_id:str,data:ExpectedVersion,service=Depends(get_service)):
    ProjectLifecycle(service).delete(project_id,data.expected_version)
    return Response(status_code=204)

@router.post('/{project_id}/duplicate',response_model=ProjectView,status_code=201)
def duplicate_project(project_id:str,data:ProjectDuplicate,service=Depends(get_service)):
    return ProjectLifecycle(service).duplicate(project_id,data)

@router.get('/{project_id}/export')
def export_project(project_id:str,service=Depends(get_service)):
    return ProjectLifecycle(service).export(project_id)

@router.put('/{project_id}/recovery',response_model=ProjectView)
def recovery(project_id:str,data:RecoverySave,service=Depends(get_service)):
    return ProjectLifecycle(service).recovery(project_id,data)

@router.get('/{project_id}',response_model=ProjectView)
def get_project(project_id:str,session=Depends(get_session)):
    return ProjectRepository(session).get(project_id)

@router.patch('/{project_id}',response_model=ProjectView)
def update_project(project_id:str,data:ProjectUpdate,service=Depends(get_service)):
    return service.update(project_id,data)

@router.get('/{project_id}/answers')
def get_answers(project_id:str,session=Depends(get_session)):
    project=ProjectRepository(session).get(project_id)
    return {'answers':project['requirements'],'lock_version':project['lock_version'],'archetype_version_id':project['archetype_version_id']}

@router.get('/{project_id}/requirements')
def get_requirements(project_id:str,session=Depends(get_session)):
    project=ProjectRepository(session).row(project_id)
    rows=session.execute(select(m.project_requirements).where(m.project_requirements.c.project_id==project['id'],m.project_requirements.c.project_revision_id.is_(None))).mappings()
    return {'requirements':serial([dict(r) for r in rows]),'lock_version':project['lock_version']}

@router.put('/{project_id}/answers',response_model=ProjectView)
def save_answers(project_id:str,data:AnswerSave,service=Depends(get_service)):
    return service.update(project_id,ProjectUpdate(expected_version=data.expected_version,requirements=data.answers))

@router.get('/{project_id}/revisions')
def revisions(project_id:str,session=Depends(get_session)):
    return ProjectRepository(session).revisions(project_id)

@router.post('/{project_id}/revisions',response_model=DesignPackage,status_code=201)
def create_revision(project_id:str,data:RevisionCreate,service=Depends(get_service)):
    return service.generate(project_id,data.requirements,data.expected_version,data.configuration)

@router.get('/{project_id}/revisions/{revision_id}',response_model=DesignPackage)
def get_revision(project_id:str,revision_id:str,service=Depends(get_service)):
    return service.load_revision(project_id,revision_id)

@router.post('/{project_id}/revisions/{revision_id}/restore',response_model=DesignPackage,status_code=201)
def restore_revision(project_id:str,revision_id:str,data:ExpectedVersion,service=Depends(get_service)):
    return service.restore(project_id,revision_id,data.expected_version)
