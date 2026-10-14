from fastapi import APIRouter
from app.services.orchestrator import DesignOrchestrator

router = APIRouter(prefix="/api/projects/{project_id}/validation", tags=["validation"])
orchestrator = DesignOrchestrator()


@router.get("")
def get_validation_report(project_id: str):
    design = orchestrator.generate_design(project_id)
    return {
        "project_id": project_id,
        "violations": design["validation_errors"],
        "thermal_density_index": design["pdm"]["thermal_density_index"],
        "total_heat_loss_watts": design["pdm"]["total_heat_loss_watts"]
    }
