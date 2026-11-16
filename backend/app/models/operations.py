"""Allowlisted preview contracts. Preview is never an approval or a commit."""
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.models.document import DirtyStage, SHA256, ResolvedDocument
from app.models.identity import ContractModel, StableID, unique_ids
from app.models.schematic import SchematicPoint

ModelKind = Literal['requirements', 'cem', 'pdm', 'schematic']


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
    # Multi-model commands fence every affected snapshot, including absence.
    model_sha256: dict[ModelKind, SHA256 | None] = Field(default_factory=dict, exclude_if=lambda value: not value)


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


class PanelTarget(ContractModel):
    panel_id: StableID


class PlacementIntent(ContractModel):
    position_mm: PositionMM
    zone_name: StableID
    rail_id: StableID | None


class AddParameters(CatalogChoice):
    product_version_id: StableID | None
    terminal_intent: Literal['UNCONNECTED']
    terminal_ids: list[StableID] = Field(min_length=1)
    placement: PlacementIntent


class AddComponent(OperationBase):
    type: Literal['AddComponent']
    target: PanelTarget
    parameters: AddParameters
    affected_models: tuple[Literal['cem'], Literal['pdm']] = ('cem', 'pdm')


class CascadeConfirmation(ContractModel):
    dependencies: dict[StableID, list[StableID]]
    sha256: SHA256


class RemoveParameters(ContractModel):
    confirmed_cascade: CascadeConfirmation | None = None


class RemoveComponent(OperationBase):
    type: Literal['RemoveComponent']
    target: ComponentTarget
    parameters: RemoveParameters
    affected_models: tuple[Literal['cem'], Literal['pdm'], Literal['schematic']] = ('cem', 'pdm', 'schematic')


class SymbolTarget(ContractModel):
    symbol_id: StableID


class SymbolPosition(ContractModel):
    position_mm: SchematicPoint


class MoveSymbol(OperationBase):
    type: Literal['MoveSymbol']
    target: SymbolTarget
    parameters: SymbolPosition
    affected_models: tuple[Literal['schematic']] = ('schematic',)


class LabelTarget(ContractModel):
    kind: Literal['symbol', 'wire', 'pin']
    id: StableID


class LabelParameters(ContractModel):
    label: str = Field(max_length=1000)


class UpdateSchematicLabel(OperationBase):
    type: Literal['UpdateSchematicLabel']
    target: LabelTarget
    parameters: LabelParameters
    affected_models: tuple[Literal['schematic']] = ('schematic',)


class PinTarget(ContractModel):
    pin_id: StableID


class JunctionParameters(LabelParameters):
    visible: bool


class UpdateJunctionPresentation(OperationBase):
    type: Literal['UpdateJunctionPresentation']
    target: PinTarget
    parameters: JunctionParameters
    affected_models: tuple[Literal['schematic']] = ('schematic',)


class ConnectionTarget(ContractModel):
    connection_id: StableID | None


class ConductorIntent(ContractModel):
    from_component: StableID
    from_terminal: StableID
    to_component: StableID
    to_terminal: StableID
    net_id: StableID
    wire_class: Literal['POWER', 'CONTROL', 'SIGNAL', 'PE', 'NEUTRAL']
    conductor_material: Literal['COPPER', 'ALUMINIUM']
    cross_section_mm2: float = Field(gt=0, strict=True)
    insulation_diameter_mm: float = Field(gt=0, strict=True)
    insulation_type: StableID
    minimum_bend_radius_mm: float = Field(gt=0, strict=True)


class ConnectionParameters(ContractModel):
    action: Literal['CREATE', 'REPLACE', 'DELETE']
    conductor: ConductorIntent | None
    invalidated_route_ids: list[StableID]
    removed_net_ids: list[StableID] = Field(default_factory=list)


class ModifyElectricalConnection(OperationBase):
    type: Literal['ModifyElectricalConnection']
    target: ConnectionTarget
    parameters: ConnectionParameters
    affected_models: tuple[Literal['cem'], Literal['pdm'], Literal['schematic']] = ('cem', 'pdm', 'schematic')


class SchematicTarget(ContractModel):
    schematic_id: StableID


class RegenerateParameters(ContractModel):
    replace_manual_positions: bool = False


class RegenerateSchematic(OperationBase):
    type: Literal['RegenerateSchematic']
    target: SchematicTarget
    parameters: RegenerateParameters
    affected_models: tuple[Literal['schematic']] = ('schematic',)


class GenerationParameters(ContractModel):
    overrides: dict[str, Any] = Field(default_factory=dict)
    candidate_sha256: SHA256


class ApplyGeneration(OperationBase):
    type: Literal['ApplyGeneration']
    target: PanelTarget
    parameters: GenerationParameters
    affected_models: tuple[Literal['requirements'], Literal['cem'], Literal['pdm'], Literal['schematic']] = ('requirements', 'cem', 'pdm', 'schematic')


Operation = Annotated[ApplyGeneration | MoveComponent | RotateComponent | UpdateRequirement | ChangeComponentRating | ResizeEnclosure | AddComponent | RemoveComponent | MoveSymbol | UpdateSchematicLabel | UpdateJunctionPresentation | ModifyElectricalConnection | RegenerateSchematic,
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


class HistoryRequest(ContractModel):
    """Undo/redo identifies retained history; clients cannot supply inverses."""
    schema_version: Literal['1.0.0'] = '1.0.0'
    batch_id: UUID
    operation_id: UUID
    document_id: StableID
    base_sequence: int = Field(ge=0, strict=True)
    expected_version: int = Field(ge=1, strict=True)
    base_revision_id: StableID | None
    before_content_sha256: SHA256
    action: Literal['UNDO', 'REDO']
    target_batch_id: UUID
    origin: OperationOrigin

    @model_validator(mode='after')
    def accepted_origin(self):
        if self.origin.kind == 'AI_PROPOSAL' or self.origin.proposal_id is not None:
            raise ValueError('History application cannot accept a proposal.')
        return self


class OperationHistory(ContractModel):
    document_id: StableID
    document_sequence: int
    lock_version: int
    content_sha256: SHA256
    # Oldest to newest; last item is the only eligible next target.
    undo_batch_ids: list[UUID]
    redo_batch_ids: list[UUID]


class OperationChange(ContractModel):
    operation_id: UUID
    model: ModelKind
    target_id: StableID
    before_sha256: SHA256 | None
    after_sha256: SHA256 | None
    changed_fields: list[Literal['position_mm', 'terminals_mm', 'rotation_deg', 'value', 'state', 'source',
                                 'message', 'validation', 'component_catalog', 'enclosure_catalog', 'components', 'cascade',
                                 'presentation', 'connections']]


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
    consequences: dict[str, CascadeConfirmation] = Field(default_factory=dict)


class GenerationConflict(ContractModel):
    target: StableID
    reason: str


class GenerationProposal(ContractModel):
    status: Literal['REVIEW_REQUIRED', 'CONFLICT']
    persisted: Literal[False] = False
    conflicts: list[GenerationConflict]
    batch: OperationPreviewRequest | None
    preview: OperationPreview | None = None
