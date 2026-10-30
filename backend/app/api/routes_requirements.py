from typing import Any
from fastapi import APIRouter,Depends
from app.api.dependencies import get_session,get_service
from app.persistence.repositories import ProjectRepository,CatalogRepository
from app.services.requirement_engine import RequirementEngine

router=APIRouter(prefix='/api/projects/{project_id}/requirements',tags=['requirements'])

def template_for(project_id,session,service):
    p=ProjectRepository(session).get(project_id)
    return CatalogRepository(session,service.assets).template(p['archetype'],p['archetype_version_id'])

@router.get('/questions')
def get_questionnaire(project_id:str,session=Depends(get_session),service=Depends(get_service)):
    return template_for(project_id,session,service)['questions']

@router.post('/suggestions')
def suggestions(project_id:str,values:dict[str,Any],session=Depends(get_session),service=Depends(get_service)):
    from app.services.questionnaire_choices import suggest_requirements
    template=template_for(project_id,session,service)
    return suggest_requirements(template,CatalogRepository(session,service.assets).engine_catalog(),values)

@router.post('/validate')
def validate_requirements(project_id:str,values:dict[str,Any],session=Depends(get_session),service=Depends(get_service)):
    template=template_for(project_id,session,service)
    return RequirementEngine(templates={template['archetype']:template}).validate_requirements(project_id,template['archetype'],values).model_dump()
