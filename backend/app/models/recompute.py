"""Explicit execution is separate from accepting a draft or publishing a revision."""
from pydantic import Field

from app.models.identity import ContractModel, StableID
from app.models.operations import GenerationProposal
from app.services.stages.scheduler import StageExecution


class RecomputeRequest(ContractModel):
    document_id: StableID
    expected_document_sequence: int = Field(ge=0, strict=True)
    expected_version: int = Field(ge=1, strict=True)


class RecomputeResponse(GenerationProposal):
    scheduled_stages: list[str]
    stage_executions: list[StageExecution]

