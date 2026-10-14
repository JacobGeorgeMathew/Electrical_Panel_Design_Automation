from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field


class RequirementState(str, Enum):
    MISSING = "MISSING"
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    VALIDATED = "VALIDATED"
    DERIVED = "DERIVED"
    CALCULATED = "CALCULATED"
    ASSUMED = "ASSUMED"
    CONFLICTING = "CONFLICTING"


class DependencyRule(BaseModel):
    field: str
    operator: str  # "equals", "greater_than", "less_than", "in"
    value: Any


class QuestionValidation(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class QuestionSchema(BaseModel):
    id: str
    label: str
    type: str  # "number", "select", "boolean", "text"
    unit: Optional[str] = None
    default: Any = None
    options: Optional[List[Any]] = None
    required: bool = True
    depends_on: List[DependencyRule] = Field(default_factory=list)
    validation: Optional[QuestionValidation] = None


class RequirementItem(BaseModel):
    id: str
    label: str
    value: Any
    unit: Optional[str] = None
    state: RequirementState = RequirementState.PROPOSED
    source: str = "USER"  # "USER", "DEFAULT", "DERIVED"
    message: Optional[str] = None


class RequirementSet(BaseModel):
    project_id: str
    archetype: str
    items: List[RequirementItem] = Field(default_factory=list)
    is_valid: bool = False
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)
