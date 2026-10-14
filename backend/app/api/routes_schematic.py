from fastapi import APIRouter
from app.services.orchestrator import DesignOrchestrator

router = APIRouter(prefix="/api/projects/{project_id}/schematic", tags=["schematic"])
orchestrator = DesignOrchestrator()


@router.get("")
def get_schematic(project_id: str):
    design = orchestrator.generate_design(project_id)
    return design["schematic"]
