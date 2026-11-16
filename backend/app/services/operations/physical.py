"""Authoritative, bounded physical draft edits over server-owned snapshots.

Coordinates are absolute enclosure millimetres, including mounting offsets.
Check known placement constraints without evaluating obsolete routes. Successful
edits still need explicit Recompute: the registry invalidates routing, physical
validation and CAD. No optimization, routing or publication occurs here.
"""
from math import isfinite

from app.models.pdm import Position3D, ValidationViolation
from app.services.design_errors import DesignError
from app.services.validation_engine import ValidationEngine


def reject(op, code, message, **details):
    raise DesignError(code, message, {'operation_id': str(op.operation_id), **details})


def physical_target(candidate, op):
    pdm = candidate.snapshots.pdm
    component = next((c for c in pdm.components if c.id == op.target.pdm_component_id), None)
    if component is None or component.cem_component_id != op.target.cem_component_id:
        reject(op, 'OPERATION_TARGET', 'Physical and electrical target IDs must match an existing component.')
    # Axis-aligned placement checks cannot establish validity for rotated bodies.
    # Do not normalize full turns or reset imported rotations: terminal anchors
    # and obstacles need the shared oriented geometry work reserved for P4-T10.
    if any(c.rotation_deg != 0 for c in pdm.components):
        reject(op, 'UNSUPPORTED_ROTATION', 'Physical edits of rotated layouts are not supported.')
    return component


def validate_placement(pdm, op):
    dimensions = [pdm.enclosure_width, pdm.enclosure_height, pdm.enclosure_depth]
    dimensions += [value for c in pdm.components for value in (c.width, c.height, c.depth)]
    dimensions += [value for value in (pdm.mounting_plate_width, pdm.mounting_plate_height)
                   if value is not None]
    if any(value <= 0 or not isfinite(value) for value in dimensions):
        reject(op, 'OPERATION_GEOMETRY', 'Positive finite server-owned physical dimensions are required.')
    # The existing validator checks backplate XY offsets/extents, cabinet depth,
    # overlap, saved-policy clearances, thermal density and duct/device collision.
    # Use a copy: validate_pdm updates thermal metadata. Routes are stale after a
    # move, so route/terminal/fill checks remain unresolved until Recompute.
    placement = pdm.model_copy(deep=True)
    placement.routes = []
    violations = ValidationEngine().validate_pdm(placement)
    # A prior enclosure edit can leave stale plate extents. Containment in that
    # plate must never grant permission to leave the actual cabinet in XY.
    for component in placement.components:
        if (component.position.x < 0 or component.position.y < 0
                or component.position.x + component.width > placement.enclosure_width
                or component.position.y + component.height > placement.enclosure_height):
            violations.append(ValidationViolation(type='BOUNDARY', severity='CRITICAL',
                object_a=component.id, required_value=0, actual_value=-1, unit='mm',
                message='Component envelope leaves the enclosure.'))
    if violations:
        reject(op, 'OPERATION_PHYSICAL_CONSTRAINT', 'Physical edit violates known placement constraints.',
               violations=[v.model_dump(mode='json') for v in violations])


def move_component(candidate, op):
    component = physical_target(candidate, op)
    before = component.position.model_dump()
    after = op.parameters.position_mm.model_dump()
    # Terminal dictionaries contain absolute enclosure coordinates; local solid
    # geometry and catalog dimensions remain unchanged.
    terminals = [dict(terminal) for terminal in component.terminals]
    for terminal in terminals:
        for axis in ('x', 'y', 'z'):
            value = terminal.get(axis)
            if type(value) not in (int, float) or not isfinite(value):
                reject(op, 'OPERATION_GEOMETRY', 'Physical terminal coordinates are required for movement.')
            terminal[axis] = value + (after[axis] - before[axis])
            if not isfinite(terminal[axis]):
                reject(op, 'OPERATION_GEOMETRY', 'Moved terminal coordinates must remain finite.')
    # Validate the full candidate placement before installing even a single field.
    placement = candidate.snapshots.pdm.model_copy(deep=True)
    moved = next(c for c in placement.components if c.id == component.id)
    moved.position = Position3D(**after)
    moved.terminals = terminals
    validate_placement(placement, op)
    if before == after:
        return []
    component.position = moved.position
    component.terminals = terminals
    return ['position_mm', 'terminals_mm'] if terminals else ['position_mm']


def rotate_component(candidate, op):
    physical_target(candidate, op)
    if op.parameters.rotation_deg != 0:
        reject(op, 'UNSUPPORTED_ROTATION', 'Only zero rotation is supported until oriented geometry and routing are validated.')
    validate_placement(candidate.snapshots.pdm, op)
    # Zero on a zero-rotation layout is a validated no-op, never a route refresh.
    return []
