from typing import Any, Dict, Optional
from fastapi import APIRouter
from app.services.change_propagation import ChangePropagationEngine
from app.services.orchestrator import DesignOrchestrator
from app.repositories.project_repository import ProjectRepository
from app.services.requirement_engine import RequirementEngine
from app.models.pdm import PhysicalDesignModel
from app.services.validation_engine import ValidationEngine

router = APIRouter(prefix="/api/projects/{project_id}/design", tags=["design"])
orchestrator = DesignOrchestrator()
change_engine = ChangePropagationEngine()
project_repo = ProjectRepository()
requirement_engine = RequirementEngine()
validation_engine = ValidationEngine()


@router.post("/generate")
def generate_design(project_id: str, overrides: Optional[Dict[str, Any]] = None):
    result = orchestrator.generate_design(project_id, overrides)
    return result


@router.post("/propagate-change")
def propagate_change(project_id: str, payload: Dict[str, Any]):
    modified_field = payload.get("modified_field")
    if not isinstance(modified_field, str) or not modified_field:
        from app.services.design_errors import DesignError
        raise DesignError("INVALID_CHANGE", "'modified_field' must name a DB requirement.")
    if modified_field not in {q.id for q in requirement_engine.get_questions("DB")}:
        from app.services.design_errors import DesignError
        raise DesignError("INVALID_CHANGE", f"'{modified_field}' is not a DB requirement.", {"modified_field": modified_field})
    if "new_value" not in payload:
        from app.services.design_errors import DesignError
        raise DesignError("INVALID_CHANGE", "'new_value' is required.", {"modified_field": modified_field})

    project = project_repo.get_by_id(project_id)
    if not project:
        from app.services.design_errors import DesignError
        raise DesignError("PROJECT_NOT_FOUND", f"Project '{project_id}' was not found.")
    old_values = dict(project.get("requirements", {}))
    old_design = orchestrator.generate_design(project_id)
    new_values = {**old_values, modified_field: payload["new_value"]}
    new_design = orchestrator.generate_design(project_id, {modified_field: payload["new_value"]},
                                              persist_requirements=False)

    # Compute diff
    diff_report = change_engine.compute_diff(
        old_cem=old_design["cem"],
        new_cem=new_design["cem"],
        old_pdm=old_design["pdm"],
        new_pdm=new_design["pdm"],
        modified_field=modified_field,
        old_values=old_values,
        new_values=new_values,
    )
    project_repo.save({**project, "requirements": new_values})

    return {
        "new_design": new_design,
        "diff_report": diff_report
    }


@router.post("/validate-placement")
def validate_placement(project_id: str, pdm: PhysicalDesignModel):
    """Validate a caller's editable PDM with the same prototype constraints as generation."""
    from app.services.design_errors import DesignError

    if pdm.project_id != project_id:
        raise DesignError("PROJECT_MISMATCH", "The placement model does not belong to this project.",
                          {"project_id": project_id, "pdm_project_id": pdm.project_id})
    violations = validation_engine.validate_pdm(pdm)
    pdm.validation_results = violations
    dump_model = getattr(pdm, "model_dump", None)
    serialize = dump_model if callable(dump_model) else pdm.dict
    def serialize_violation(violation):
        dump_violation = getattr(violation, "model_dump", None)
        return dump_violation() if callable(dump_violation) else violation.dict()
    return {
        "pdm": serialize(),
        "validation_results": [serialize_violation(violation) for violation in violations],
        "is_valid": not any(violation.severity == "CRITICAL" for violation in violations),
    }
