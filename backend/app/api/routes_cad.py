from fastapi import APIRouter
from app.services.cad_engine import CADEngine
from app.services.orchestrator import DesignOrchestrator

router = APIRouter(prefix="/api/projects/{project_id}/cad", tags=["cad"])
orchestrator = DesignOrchestrator()
cad_engine = CADEngine()


@router.get("")
def get_cad_geometry(project_id: str):
    design = orchestrator.generate_design(project_id)
    return design["cad"]


@router.get("/freecad-script")
def get_freecad_script(project_id: str):
    design = orchestrator.generate_design(project_id)
    # Reconstruct PDM object
    pdm_data = design["pdm"]
    from app.models.pdm import PhysicalDesignModel
    pdm = PhysicalDesignModel(**pdm_data)
    script = cad_engine.export_freecad_script(pdm)
    return {"script": script}
