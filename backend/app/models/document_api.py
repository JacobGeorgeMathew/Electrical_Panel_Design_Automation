"""Bounded v1 Save contract; generated snapshots are never client writable."""
from typing import Any

from pydantic import Field, field_validator

from app.models.api import ProjectUpdate
from app.models.document import ResolvedDocument
from app.models.identity import ContractModel, StableID, unique_ids
from app.models.requirements import RequirementSet
from app.models.electrical_topology import ElectricalTopologyEvidence


class DocumentSave(ContractModel):
    schema_version: str = Field(default='1.0.0', pattern=r'^1\.0\.0$')
    document_id: StableID
    expected_version: int = Field(ge=1, strict=True)
    expected_document_sequence: int = Field(ge=0, strict=True)
    requirements: RequirementSet
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator('requirements')
    @classmethod
    def requirement_ids(cls, value):
        unique_ids((item.id for item in value.items), 'requirements.items')
        return value

    @field_validator('configuration')
    @classmethod
    def configuration_shape(cls, value):
        ProjectUpdate.configuration_shape({k: v for k, v in value.items() if k != 'electrical_topology'})
        if 'electrical_topology' in value:
            ElectricalTopologyEvidence.model_validate(value['electrical_topology'])
        return value


class DocumentView(ResolvedDocument):
    content_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
