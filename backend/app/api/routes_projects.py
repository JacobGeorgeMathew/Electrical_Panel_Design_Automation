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
    project_id = data.get("id", f"PROJ_{len(repo.get_all()) + 1:03d}")
    data["id"] = project_id
    saved = repo.save(data)
    return saved
