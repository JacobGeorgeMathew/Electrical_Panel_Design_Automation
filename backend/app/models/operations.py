"""Allowlisted preview contracts. Preview is never an approval or a commit."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.models.document import DirtyStage, SHA256, ResolvedDocument
from app.models.identity import ContractModel, StableID, unique_ids

ModelKind = Literal['requirements', 'cem', 'pdm']


class OperationOrigin(ContractModel):
    kind: Literal['MANUAL', 'AUTOMATIC', 'IMPORT', 'RESTORE', 'COMPATIBILITY', 'AI_PROPOSAL']
    actor_id: StableID
    proposal_id: StableID | None = None
    job_id: StableID | None = None


class PositionMM(ContractModel):
    x: float = Field(strict=True)
    y: float = Field(strict=True)
    z: float = Field(strict=True)


class SnapshotPrecondition(ContractModel):
    # Evaluated against the candidate at this operation's execution point.
    snapshot_sha256: SHA256


class MoveTarget(ContractModel):
    cem_component_id: StableID
    pdm_component_id: StableID


class MoveParameters(ContractModel):
    position_mm: PositionMM


class RequirementParameters(ContractModel):
    # Questionnaire-specific ranges/units require subsequent engineering checks.
    value: Annotated[float, Field(strict=True)] | str | bool | None


class OperationBase(ContractModel):
    operation_id: UUID
    origin: OperationOrigin
    proposal_status: Literal['NOT_PROPOSED', 'PROPOSED'] = 'NOT_PROPOSED'
    preconditions: SnapshotPrecondition

    @model_validator(mode='after')
    def proposal_consistency(self):
        proposed = self.origin.kind == 'AI_PROPOSAL' or self.origin.proposal_id is not None
        if proposed != (self.proposal_status == 'PROPOSED'):
            raise ValueError('Proposal origin requires PROPOSED status and proposal_id.')
        if proposed and self.origin.proposal_id is None:
            raise ValueError('Proposal ID is required.')
        return self


class MoveComponent(OperationBase):
    type: Literal['MoveComponent']
    target: MoveTarget
    parameters: MoveParameters
    affected_models: tuple[Literal['pdm']] = ('pdm',)


class RotationParameters(ContractModel):
    # Absolute degrees about the existing Z axis; nonzero values are rejected by
    # the physical handler until oriented geometry/routing support is validated.
    rotation_deg: float = Field(strict=True)


class RotateComponent(OperationBase):
    type: Literal['RotateComponent']
    target: MoveTarget
    parameters: RotationParameters
    affected_models: tuple[Literal['pdm']] = ('pdm',)


class RequirementTarget(ContractModel):
    requirement_id: StableID


class UpdateRequirement(OperationBase):
    type: Literal['UpdateRequirement']
    target: RequirementTarget
    parameters: RequirementParameters
    affected_models: tuple[Literal['requirements']] = ('requirements',)


class ComponentTarget(ContractModel):
    cem_component_id: StableID


class CatalogChoice(ContractModel):
    catalog_id: StableID
    component_version_id: StableID


class RatingParameters(CatalogChoice):
    current_rating: float = Field(strict=True, gt=0)


class ChangeComponentRating(OperationBase):
    type: Literal['ChangeComponentRating']
    target: ComponentTarget
    parameters: RatingParameters
    affected_models: tuple[Literal['cem']] = ('cem',)


class EnclosureTarget(ContractModel):
    enclosure_id: StableID


class EnclosureParameters(CatalogChoice):
    width: float = Field(strict=True, gt=0)
    height: float = Field(strict=True, gt=0)
    depth: float = Field(strict=True, gt=0)


class ResizeEnclosure(OperationBase):
    type: Literal['ResizeEnclosure']
    target: EnclosureTarget
    parameters: EnclosureParameters
    affected_models: tuple[Literal['pdm']] = ('pdm',)


Operation = Annotated[MoveComponent | RotateComponent | UpdateRequirement | ChangeComponentRating | ResizeEnclosure,
                      Field(discriminator='type')]


class OperationPreviewRequest(ContractModel):
    schema_version: Literal['1.0.0'] = '1.0.0'
    batch_id: UUID
    document_id: StableID
    base_sequence: int = Field(ge=0, strict=True)
    expected_version: int = Field(ge=1, strict=True)
    base_revision_id: StableID | None
    operations: list[Operation] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def operation_ids_unique(self):
        unique_ids((str(op.operation_id) for op in self.operations), 'operations')
        return self


class OperationChange(ContractModel):
    operation_id: UUID
    model: ModelKind
    target_id: StableID
    before_sha256: SHA256
    after_sha256: SHA256
    changed_fields: list[Literal['position_mm', 'terminals_mm', 'rotation_deg', 'value', 'state', 'source',
                                 'message', 'validation', 'component_catalog', 'enclosure_catalog']]


class RequiredCheck(ContractModel):
    code: Literal['requirement_rules', 'physical_constraints', 'routing', 'physical_validation']
    status: Literal['UNRESOLVED'] = 'UNRESOLVED'


class OperationPreview(ContractModel):
    batch_id: UUID
    status: Literal['PREVIEW'] = 'PREVIEW'
    persisted: Literal[False] = False
    base_sequence: int
    before_content_sha256: SHA256
    after_content_sha256: SHA256
    changes: list[OperationChange]
    required_checks: list[RequiredCheck]
    dirty_stages: list[DirtyStage]
    candidate: ResolvedDocument
