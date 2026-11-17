from typing import Any
from fastapi import APIRouter, Depends, Query, Header
from app.api.dependencies import get_service
from app.models.api import ChangeInput, DesignPackage
from app.models.pdm import PhysicalDesignModel
from app.models.operations import OperationPreviewRequest, GenerationProposal
from app.models.recompute import RecomputeRequest, RecomputeResponse
from app.services.validation_engine import ValidationEngine
from app.services.design_errors import DesignError

router=APIRouter(prefix='/api/projects/{project_id}/design',tags=['design'])


@router.post('/recompute', response_model=RecomputeResponse)
def recompute_design(project_id: str, data: RecomputeRequest, service=Depends(get_service)):
    from app.services.recompute import recompute
    return recompute(service, project_id, data)


@router.post('/generation-proposal', response_model=GenerationProposal)
def generation_proposal(project_id:str,overrides:dict[str,Any]|None=None,service=Depends(get_service)):
    from app.services.generation_proposals import propose_generation
    return propose_generation(service.db, project_id, overrides)


@router.post('/generation-proposal/accept')
def accept_generation_proposal(project_id:str, data:OperationPreviewRequest,
        idempotency_key:str=Header(alias='Idempotency-Key'), service=Depends(get_service)):
    from app.persistence.operations import OperationBatchRepository
    return OperationBatchRepository(service.db).accept_generation(project_id, data, idempotency_key)

@router.get('',response_model=DesignPackage)
def get_design(project_id:str,service=Depends(get_service)):
    return service.load_revision(project_id)

@router.post('/generate',response_model=DesignPackage)
def generate_design(project_id:str,overrides:dict[str,Any]|None=None,expected_version:int|None=Query(None,ge=1),service=Depends(get_service)):
    return service.generate(project_id,overrides,expected_version)

@router.post('/propagate-change')
def propagate_change(project_id:str,payload:ChangeInput,service=Depends(get_service)):
    return service.propagate(project_id,payload.modified_field,payload.new_value,payload.expected_version)

@router.post('/validate-placement')
def validate_placement(project_id:str,pdm:PhysicalDesignModel):
    if pdm.project_id!=project_id:
        raise DesignError('PROJECT_MISMATCH','The placement model does not belong to this project.')
    violations=ValidationEngine().validate_pdm(pdm)
    pdm.validation_results=violations
    return {'pdm':pdm.model_dump(),'validation_results':[v.model_dump() for v in violations],
            'is_valid':not violations}

@router.post('/reroute-placement')
def reroute_edited_placement(project_id:str,pdm:PhysicalDesignModel,service=Depends(get_service)):
    from app.models.cem import CanonicalEngineeringModel
    from app.services.physical_routing import reroute_placement
    if pdm.project_id!=project_id:
        raise DesignError('PROJECT_MISMATCH','The placement model does not belong to this project.')
    saved=service.load_revision(project_id)
    cem=CanonicalEngineeringModel(**saved['cem'])
    if {c.cem_component_id for c in pdm.components}!={c.id for c in cem.components}:
        raise DesignError('COMPONENT_MISMATCH','Draft component IDs must match the saved CEM.')
    pdm=reroute_placement(pdm,cem)
    return {'pdm':pdm.model_dump(),'validation_results':[v.model_dump() for v in pdm.validation_results],
        'is_valid':not pdm.validation_results,'persisted':False}
