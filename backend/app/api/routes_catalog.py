from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from app.api.dependencies import get_service,get_session
from app.persistence.repositories import CatalogRepository,PersistenceError,serial
from app.persistence import models as m
from app.models.api import CatalogPageView,CatalogComponentView,ArchetypeView

router=APIRouter(prefix='/api',tags=['catalog'])

@router.get('/components',response_model=CatalogPageView)
def components(q:str=Query('',max_length=200),category:str|None=None,manufacturer:str|None=None,
               page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),sort:Literal['code','name','current_rating']='code',
               session=Depends(get_session),service=Depends(get_service)):
    return CatalogRepository(session,service.assets).search(q,category,manufacturer,page,page_size,sort)

@router.get('/catalog/filters')
def catalog_filters(session=Depends(get_session)):
    return {'categories':list(session.scalars(select(m.components.c.category_code).distinct().order_by(m.components.c.category_code))),
        'manufacturers':serial([dict(r) for r in session.execute(select(m.manufacturers.c.id,m.manufacturers.c.code,m.manufacturers.c.name).order_by(m.manufacturers.c.name)).mappings()])}

@router.get('/enclosures')
def enclosures(session=Depends(get_session),service=Depends(get_service)):
    return CatalogRepository(session,service.assets).enclosures()

@router.get('/components/{component_id}',response_model=CatalogComponentView)
def component(component_id:str,session=Depends(get_session),service=Depends(get_service)):
    result=CatalogRepository(session,service.assets).get_component(component_id)
    if not result: raise PersistenceError('COMPONENT_NOT_FOUND','Component was not found.',404)
    return result

@router.get('/components/{component_id}/versions')
def versions(component_id:str,session=Depends(get_session),service=Depends(get_service)):
    return CatalogRepository(session,service.assets).versions(component_id)

@router.get('/components/{component_id}/cad-models')
def cad_models(component_id:str,session=Depends(get_session),service=Depends(get_service)):
    result=CatalogRepository(session,service.assets).get_component(component_id)
    if not result: raise PersistenceError('COMPONENT_NOT_FOUND','Component was not found.',404)
    return result['cad_models']

@router.get('/components/{component_id}/accessories',response_model=list[CatalogComponentView])
def accessories(component_id:str,session=Depends(get_session),service=Depends(get_service)):
    return CatalogRepository(session,service.assets).accessories(component_id)

@router.get('/archetypes',response_model=list[ArchetypeView])
def archetypes(session=Depends(get_session),service=Depends(get_service)):
    return CatalogRepository(session,service.assets).archetypes()

@router.get('/archetypes/{archetype_id}')
@router.get('/archetypes/{archetype_id}/questionnaire')
def archetype(archetype_id:str,version_id:str|None=None,session=Depends(get_session),service=Depends(get_service)):
    return CatalogRepository(session,service.assets).template(archetype_id,version_id)

@router.post('/archetypes/{archetype_id}/suggestions')
def archetype_suggestions(archetype_id:str,values:dict,session=Depends(get_session),service=Depends(get_service)):
    from app.services.questionnaire_choices import suggest_requirements
    catalog=CatalogRepository(session,service.assets)
    template=catalog.template(archetype_id)
    if template['archetype']!='DB':raise PersistenceError('UNSUPPORTED_ARCHETYPE','Only DB suggestions are supported.')
    return suggest_requirements(template,catalog.engine_catalog(),values)

@router.get('/archetypes/{archetype_id}/electrical-templates')
def electrical_templates(archetype_id:str,version_id:str|None=None,session=Depends(get_session),service=Depends(get_service)):
    catalog=CatalogRepository(session,service.assets)
    template=catalog.template(archetype_id,version_id)
    return catalog.electrical_templates(template['archetype_version_id'])

@router.get('/rules')
def rules(session=Depends(get_session),service=Depends(get_service)):
    return CatalogRepository(session,service.assets).rules()
