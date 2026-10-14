from fastapi import APIRouter
from app.services.orchestrator import DesignOrchestrator

router = APIRouter(prefix="/api/projects/{project_id}/layout", tags=["layout"])
orchestrator = DesignOrchestrator()


@router.get("")
def get_layout(project_id: str):
    design = orchestrator.generate_design(project_id)
    return design["pdm"]
