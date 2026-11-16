"""Pure, ordered preview over a detached, integrity-checked document copy.

No repositories, engines, catalog lookups, asset writes or operation receipts are
available to handlers. Derived outputs remain stale and checks unresolved.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable

from app.models.document import ResolvedDocument, SnapshotReference, snapshot_sha256
from app.models.operations import OperationPreview, OperationPreviewRequest, OperationChange, RequiredCheck
from app.models.requirements import RequirementState
from app.persistence.documents import document_hash
from app.persistence.repositories import PersistenceError
from app.services.design_errors import DesignError


def reject(operation, code, message):
    raise DesignError(code, message, {'operation_id': str(operation.operation_id)})


def move_component(candidate, op):
    pdm = candidate.snapshots.pdm
    component = next((c for c in pdm.components if c.id == op.target.pdm_component_id), None)
    if component is None or component.cem_component_id != op.target.cem_component_id:
        reject(op, 'OPERATION_TARGET', 'Physical and electrical target IDs must match an existing component.')
    if component.rotation_deg != 0:
        reject(op, 'UNSUPPORTED_ROTATION', 'Moving rotated components is not supported.')
    before = component.position.model_dump()
    after = op.parameters.position_mm.model_dump()
    if before == after:
        return []
    # Physical terminal dictionaries contain absolute enclosure millimetres.
    for terminal in component.terminals:
        for axis in ('x', 'y', 'z'):
            if type(terminal.get(axis)) not in (int, float):
                reject(op, 'OPERATION_GEOMETRY', 'Physical terminal coordinates are required for movement preview.')
            terminal[axis] += after[axis] - before[axis]
    component.position = type(component.position)(**after)
    return ['position_mm', 'terminals_mm'] if component.terminals else ['position_mm']


def update_requirement(candidate, op):
    requirements = candidate.snapshots.requirements
    item = next((r for r in requirements.items if r.id == op.target.requirement_id), None)
    if item is None:
        reject(op, 'OPERATION_TARGET', 'Requirement target must already exist.')
    # Do not preserve a validated/derived claim after changing a user value.
    desired = dict(value=op.parameters.value, state=RequirementState.PROPOSED, source='USER', message=None)
    fields = [key for key, value in desired.items() if getattr(item, key) != value
              or (key == 'value' and type(item.value) is not type(value))]
    if not fields:
        return []
    for key, value in desired.items():
        setattr(item, key, value)
    requirements.is_valid = False
    requirements.validation_errors = []
    requirements.validation_warnings = []
    return fields + ['validation']


@dataclass(frozen=True)
class OperationDefinition:
    model: str
    handler: Callable
    dirty_stages: tuple[str, ...]
    checks: tuple[str, ...]


REGISTRY = MappingProxyType({
    'MoveComponent': OperationDefinition('pdm', move_component,
        ('routes', 'physical_validation', 'cad'), ('physical_constraints', 'routing', 'physical_validation')),
    'UpdateRequirement': OperationDefinition('requirements', update_requirement,
        ('requirements', 'calculations', 'selection', 'connectivity', 'schematic',
         'placement', 'routes', 'physical_validation', 'bom', 'cad'), ('requirement_rules',)),
})


def preview_operations(resolved: ResolvedDocument, request: OperationPreviewRequest) -> OperationPreview:
    # Revalidate at this service boundary, including non-HTTP/internal callers.
    request = OperationPreviewRequest.model_validate(request.model_dump(mode='json'))
    candidate = ResolvedDocument.model_validate(resolved.model_dump(mode='json', include={'document', 'snapshots'}))
    doc = candidate.document
    if (request.document_id != doc.document_id or request.base_sequence != doc.document_sequence
            or request.expected_version != doc.lock_version or request.base_revision_id != doc.base_revision_id):
        raise PersistenceError('DOCUMENT_CONFLICT', 'Preview base changed. Retain edits and reload for comparison.', 409)
    before_hash = document_hash(doc)
    changes, checks = [], []
    for op in request.operations:
        definition = REGISTRY[op.type]
        if tuple(op.affected_models) != (definition.model,):
            reject(op, 'OPERATION_MODELS', 'Affected models differ from the operation registry.')
        snapshot = getattr(candidate.snapshots, definition.model)
        if snapshot is None:
            reject(op, 'OPERATION_TARGET', 'The target model has not been computed.')
        before = snapshot_sha256(snapshot)
        if before != op.preconditions.snapshot_sha256:
            raise PersistenceError('OPERATION_PRECONDITION', 'Target snapshot changed. Repreview against current inputs.', 409)
        fields = definition.handler(candidate, op)
        after = snapshot_sha256(snapshot)
        if before == after:
            continue
        setattr(doc.models, definition.model, SnapshotReference(sha256=after))
        changes.append(OperationChange(operation_id=op.operation_id, model=definition.model,
            target_id=(op.target.pdm_component_id if op.type == 'MoveComponent' else op.target.requirement_id),
            before_sha256=before, after_sha256=after, changed_fields=fields))
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
        dirty_stages=doc.dirty_stages, candidate=candidate)
