from fastapi import APIRouter,Depends
from sqlalchemy import select
from app.api.dependencies import get_service,get_session
from app.persistence import models as m
from app.persistence.repositories import serial,identifier
from app.models.cem import CanonicalEngineeringModel
from app.models.pdm import PhysicalDesignModel
from app.models.validation import ProjectValidationResponse
from app.services.validation_report import build_validation_report
router=APIRouter(prefix='/api/projects/{project_id}/validation',tags=['validation'])
@router.get('', response_model=ProjectValidationResponse)
def get_validation_report(project_id:str,service=Depends(get_service),session=Depends(get_session)):
    design=service.load_revision(project_id)
    rows=session.execute(select(m.validation_results).join(m.validation_runs,m.validation_runs.c.id==m.validation_results.c.validation_run_id)
        .where(m.validation_runs.c.project_revision_id==identifier(design['revision_id']))).mappings()
    results=serial([dict(r) for r in rows])
    aggregate=build_validation_report(CanonicalEngineeringModel.model_validate(design['cem']),
        PhysicalDesignModel.model_validate(design['pdm']), revision_id=design['revision_id'],
        physical_evaluated='validation_results' in design['pdm'] and design.get('output_status')=='COMPLETE',
        current=not design.get('is_stale',True),
        rule_versions=design['manifest'].get('validation_rule_versions',{}))
    return {'project_id':project_id,'revision_id':design['revision_id'],'violations':design['validation_errors'],
        'results':results,'thermal_density_index':design['pdm']['thermal_density_index'],
        'total_heat_loss_watts':design['pdm']['total_heat_loss_watts'],'aggregate':aggregate}
