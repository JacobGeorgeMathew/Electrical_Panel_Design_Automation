"""Pure, ordered preview over a detached, integrity-checked document copy.

Handlers receive detached server-owned catalog choices, never live repositories
or write capabilities. Derived outputs remain stale and checks unresolved.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

from app.models.document import ResolvedDocument, SnapshotReference, snapshot_sha256
from app.models.operations import OperationPreview, OperationPreviewRequest, OperationChange, RequiredCheck
from app.services.operations.engineering import (EngineeringChoices, update_requirement,
    change_component_rating, resize_enclosure)
from app.services.operations.physical import move_component, rotate_component
from app.services.operations.components import add_component, remove_component, removal_consequences
from app.services.operations.schematic import (move_symbol, update_label, update_junction,
                                              modify_connection, regenerate_schematic)
from app.persistence.documents import document_hash
from app.persistence.repositories import PersistenceError
from app.services.design_errors import DesignError


def reject(operation, code, message):
    raise DesignError(code, message, {'operation_id': str(operation.operation_id)})


@dataclass(frozen=True)
class OperationDefinition:
    model: str
    handler: Callable
    dirty_stages: tuple[str, ...]
    checks: tuple[str, ...]
    additional_models: tuple[str, ...] = ()

    @property
    def models(self):
        return (self.model, *self.additional_models)


REGISTRY = MappingProxyType({
    'MoveSymbol': OperationDefinition('schematic', move_symbol, ('cad',), ()),
    'UpdateSchematicLabel': OperationDefinition('schematic', update_label, ('cad',), ()),
    'UpdateJunctionPresentation': OperationDefinition('schematic', update_junction, ('cad',), ()),
    'RegenerateSchematic': OperationDefinition('schematic', regenerate_schematic, ('schematic', 'cad'), ()),
    'ModifyElectricalConnection': OperationDefinition('cem', modify_connection,
        ('connectivity', 'schematic', 'routes', 'physical_validation', 'bom', 'cad'),
        ('requirement_rules', 'routing', 'physical_validation'), ('pdm', 'schematic')),
    'AddComponent': OperationDefinition('cem', add_component,
        ('calculations', 'selection', 'connectivity', 'schematic', 'placement', 'routes', 'physical_validation', 'bom', 'cad'),
        ('requirement_rules', 'physical_constraints', 'routing', 'physical_validation'), ('pdm',)),
    'RemoveComponent': OperationDefinition('cem', remove_component,
        ('calculations', 'selection', 'connectivity', 'schematic', 'placement', 'routes', 'physical_validation', 'bom', 'cad'),
        ('requirement_rules', 'physical_constraints', 'routing', 'physical_validation'), ('pdm', 'schematic')),
    'MoveComponent': OperationDefinition('pdm', move_component,
        ('routes', 'physical_validation', 'cad'), ('physical_constraints', 'routing', 'physical_validation')),
    'RotateComponent': OperationDefinition('pdm', rotate_component,
        ('routes', 'physical_validation', 'cad'), ('physical_constraints', 'routing', 'physical_validation')),
    'UpdateRequirement': OperationDefinition('requirements', update_requirement,
        ('requirements', 'calculations', 'selection', 'connectivity', 'schematic',
         'placement', 'routes', 'physical_validation', 'bom', 'cad'), ('requirement_rules',)),
    'ChangeComponentRating': OperationDefinition('cem', change_component_rating,
        ('calculations', 'selection', 'connectivity', 'schematic', 'placement', 'routes',
         'physical_validation', 'bom', 'cad'), ('requirement_rules', 'physical_constraints', 'routing', 'physical_validation')),
    'ResizeEnclosure': OperationDefinition('pdm', resize_enclosure,
        ('placement', 'routes', 'physical_validation', 'bom', 'cad'),
        ('physical_constraints', 'routing', 'physical_validation')),
})


def preview_operations(resolved: ResolvedDocument, request: OperationPreviewRequest,
                       choices: EngineeringChoices | None = None) -> OperationPreview:
    # Revalidate at this service boundary, including non-HTTP/internal callers.
    request = OperationPreviewRequest.model_validate(request.model_dump(mode='json'))
    candidate = ResolvedDocument.model_validate(resolved.model_dump(mode='json', include={'document', 'snapshots'}))
    doc = candidate.document
    if (request.document_id != doc.document_id or request.base_sequence != doc.document_sequence
            or request.expected_version != doc.lock_version or request.base_revision_id != doc.base_revision_id):
        raise PersistenceError('DOCUMENT_CONFLICT', 'Preview base changed. Retain edits and reload for comparison.', 409)
    before_hash = document_hash(doc)
    changes, checks, consequences = [], [], {}
    for op in request.operations:
        definition = REGISTRY[op.type]
        if tuple(op.affected_models) != definition.models:
            reject(op, 'OPERATION_MODELS', 'Affected models differ from the operation registry.')
        snapshot = getattr(candidate.snapshots, definition.model)
        if snapshot is None:
            reject(op, 'OPERATION_TARGET', 'The target model has not been computed.')
        before = snapshot_sha256(snapshot)
        if before != op.preconditions.snapshot_sha256:
            raise PersistenceError('OPERATION_PRECONDITION', 'Target snapshot changed. Repreview against current inputs.', 409)
        before_refs = {kind: (getattr(doc.models, kind).sha256 if getattr(doc.models, kind) else None)
                       for kind in definition.models}
        if len(definition.models) > 1 and op.preconditions.model_sha256 != before_refs:
            raise PersistenceError('OPERATION_PRECONDITION', 'Every affected model requires its current snapshot precondition.', 409)
        if op.type == 'RemoveComponent':
            consequences[str(op.operation_id)] = removal_consequences(candidate, op)
        fields = (definition.handler(candidate, op) if op.type in ('MoveComponent', 'RotateComponent')
                  else definition.handler(candidate, op, choices or EngineeringChoices()))
        changed_models = []
        for kind in definition.models:
            value = getattr(candidate.snapshots, kind)
            after = snapshot_sha256(value) if value is not None else None
            if after == before_refs[kind]:
                continue
            setattr(doc.models, kind, SnapshotReference(sha256=after) if after else None)
            changed_models.append(kind)
            changes.append(OperationChange(operation_id=op.operation_id, model=kind,
                target_id=(op.target.model_dump().get('pdm_component_id')
                           or op.target.model_dump().get('id')
                           or next(iter(op.target.model_dump().values())) or str(op.operation_id)),
                before_sha256=before_refs[kind], after_sha256=after, changed_fields=fields))
        if not changed_models:
            continue
        for stage in definition.dirty_stages:
            if stage not in doc.dirty_stages:
                doc.dirty_stages.append(stage)
        for code in definition.checks:
            if code not in checks:
                checks.append(code)
    candidate = ResolvedDocument.model_validate(candidate.model_dump(mode='json'))
    return OperationPreview(batch_id=request.batch_id, base_sequence=request.base_sequence,
        before_content_sha256=before_hash, after_content_sha256=document_hash(doc), changes=changes,
        required_checks=[RequiredCheck(code=code) for code in checks],
        dirty_stages=doc.dirty_stages, candidate=candidate, consequences=consequences)
