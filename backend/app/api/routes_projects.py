from fastapi import APIRouter, Depends, Query
from app.api.dependencies import get_service, get_session
from app.models.api import ProjectCreate, ProjectUpdate, ProjectView, ExpectedVersion, AnswerSave, DesignPackage, RevisionCreate
from app.persistence.repositories import ProjectRepository
from app.persistence.repositories import identifier,serial
from app.persistence import models as m
from sqlalchemy import select

router=APIRouter(prefix='/api/projects',tags=['projects'])

@router.get('',response_model=list[ProjectView])
def list_projects(page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),session=Depends(get_session)):
    return ProjectRepository(session).list(page,page_size)

@router.post('',response_model=ProjectView,status_code=201)
def create_project(data:ProjectCreate,service=Depends(get_service)):
    return service.create(data)

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
