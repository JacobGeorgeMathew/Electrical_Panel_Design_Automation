from typing import Any, Dict, Optional
from fastapi import APIRouter
from app.services.change_propagation import ChangePropagationEngine
from app.services.orchestrator import DesignOrchestrator

router = APIRouter(prefix="/api/projects/{project_id}/design", tags=["design"])
orchestrator = DesignOrchestrator()
change_engine = ChangePropagationEngine()


@router.post("/generate")
def generate_design(project_id: str, overrides: Optional[Dict[str, Any]] = None):
    result = orchestrator.generate_design(project_id, overrides)
    return result


@router.post("/propagate-change")
def propagate_change(project_id: str, payload: Dict[str, Any]):
    modified_field = payload.get("modified_field", "num_feeders")
    new_value = payload.get("new_value", 16)

    # Fetch old design
    old_design = orchestrator.generate_design(project_id)

    # Run updated design
    overrides = {modified_field: new_value}
    new_design = orchestrator.generate_design(project_id, overrides)

    # Compute diff
    diff_report = change_engine.compute_diff(
        old_cem=old_design["cem"],
        new_cem=new_design["cem"],
        old_pdm=old_design["pdm"],
        new_pdm=new_design["pdm"]
    )

    return {
        "new_design": new_design,
        "diff_report": diff_report
    }
