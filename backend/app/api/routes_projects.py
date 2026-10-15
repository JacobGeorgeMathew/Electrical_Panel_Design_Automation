from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from app.repositories.project_repository import ProjectRepository

router = APIRouter(prefix="/api/projects", tags=["projects"])
repo = ProjectRepository()


@router.get("")
def list_projects():
    return repo.get_all()


@router.get("/{project_id}")
def get_project(project_id: str):
    p = repo.get_by_id(project_id)
    if not p:
        # Create default demo project
        p = {
            "id": project_id,
            "name": f"Distribution Board {project_id}",
            "archetype": "DB",
            "requirements": {
                "supply_voltage": 415,
                "phases": 3,
                "frequency": 50,
                "incomer_rating": 250,
                "num_feeders": 12,
                "ip_rating": "IP54",
                "spare_capacity_pct": 20,
                "neutral_required": True
            }
        }
        repo.save(p)
    return p


@router.post("")
def create_project(data: Dict[str, Any]):
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_PROJECT", "message": "Project name is required."})
    archetype = data.get("archetype", "DB")
    if archetype != "DB":
        raise HTTPException(status_code=422, detail={"code": "UNSUPPORTED_ARCHETYPE", "message": "Only DB projects are currently supported."})
    if "requirements" in data and not isinstance(data["requirements"], dict):
        raise HTTPException(status_code=422, detail={"code": "INVALID_PROJECT", "message": "Project requirements must be an object."})
    project_id = data.get("id", f"PROJ_{len(repo.get_all()) + 1:03d}")
    if not isinstance(project_id, str) or not project_id.strip():
        raise HTTPException(status_code=422, detail={"code": "INVALID_PROJECT", "message": "Project ID must be a non-empty string."})
    if repo.get_by_id(project_id):
        raise HTTPException(status_code=409, detail={"code": "PROJECT_EXISTS", "message": f"Project '{project_id}' already exists."})
    data["id"] = project_id
    data["archetype"] = archetype
    data.setdefault("requirements", {})
    saved = repo.save(data)
    return saved
