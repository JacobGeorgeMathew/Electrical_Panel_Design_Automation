from fastapi import APIRouter,Depends
from sqlalchemy import select
from app.api.dependencies import get_service,get_session
from app.persistence import models as m
from app.persistence.repositories import serial,identifier
router=APIRouter(prefix='/api/projects/{project_id}/validation',tags=['validation'])
@router.get('')
def get_validation_report(project_id:str,service=Depends(get_service),session=Depends(get_session)):
    design=service.load_revision(project_id)
    rows=session.execute(select(m.validation_results).join(m.validation_runs,m.validation_runs.c.id==m.validation_results.c.validation_run_id)
        .where(m.validation_runs.c.project_revision_id==identifier(design['revision_id']))).mappings()
    return {'project_id':project_id,'revision_id':design['revision_id'],'violations':design['validation_errors'],
        'results':serial([dict(r) for r in rows]),'thermal_density_index':design['pdm']['thermal_density_index'],
        'total_heat_loss_watts':design['pdm']['total_heat_loss_watts']}
