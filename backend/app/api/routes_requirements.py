from typing import Any, Dict
from fastapi import APIRouter
from app.services.requirement_engine import RequirementEngine

router = APIRouter(prefix="/api/projects/{project_id}/requirements", tags=["requirements"])
req_engine = RequirementEngine()


@router.get("/questions")
def get_questionnaire(project_id: str, archetype: str = "DB"):
    questions = req_engine.get_questions(archetype)
    return [q.model_dump() for q in questions]


@router.post("/validate")
def validate_requirements(project_id: str, values: Dict[str, Any], archetype: str = "DB"):
    req_set = req_engine.validate_requirements(project_id, archetype, values)
    return req_set.model_dump()
