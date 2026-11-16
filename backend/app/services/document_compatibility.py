"""Detached legacy overlay proposals. Reading/proposing never changes engineering state."""
from copy import deepcopy
import math

from app.persistence.assets import content_hash


def overlay_proposal(revision, overlay, base):
    """Require explicit base evidence; the current head is never an inferred base.

    A proposal is review data, not an accepted operation batch or validated PDM.
    Unsupported data is retained verbatim for explicit resolution by the user.
    """
    blocked, operations = [], []
    evidence = {
        'revision_id': revision['revision_id'],
        'revision_sha256': revision['snapshot_sha256'],
        'cem_sha256': content_hash(revision['cem']),
        'pdm_sha256': content_hash(revision['pdm']),
        'manifest': revision['manifest'],
        'coordinate_frame': 'enclosure-mm',
    }
    for key, value in evidence.items():
        if base.get(key) != value:
            blocked.append({'item': 'base.' + key, 'reason':
                'Missing or mismatched base evidence. Explicitly select and review the original base before conversion.'})
    if not isinstance(overlay, dict):
        blocked.append({'item': 'workspace', 'reason': 'Unsupported legacy workspace shape.'})
        overlay = deepcopy(overlay)
    else:
        for key in overlay.keys() - {'editorTransforms', 'schematicData'}:
            blocked.append({'item': key, 'reason': 'Unsupported legacy field; retained for manual review.'})
        if overlay.get('schematicData') is not None:
            blocked.append({'item': 'schematicData', 'reason':
                'Legacy schematic data requires explicit stable-reference and connectivity review.'})
        transforms = overlay.get('editorTransforms', {})
        if not isinstance(transforms, dict):
            blocked.append({'item': 'editorTransforms', 'reason': 'Transforms must be keyed by CEM component ID.'})
        else:
            cem_ids = {c['id'] for c in revision['cem']['components']}
            parts = {}
            for part in revision['pdm']['components']:
                parts.setdefault(part['cem_component_id'], []).append(part)
            for component_id, target in transforms.items():
                reason = None
                matches = parts.get(component_id, [])
                if component_id not in cem_ids or len(matches) != 1:
                    reason = 'Component has no unique matching CEM/PDM identity in the selected base.'
                elif (not isinstance(target, dict) or set(target) - {'x', 'y', 'z', 'rotation_deg'}
                      or not {'x', 'y', 'z'} <= target.keys()
                      or any(type(v) not in (int, float) or not math.isfinite(v) for v in target.values())):
                    reason = 'Transform must contain finite absolute enclosure millimetres and a supported rotation.'
                elif target.get('rotation_deg', 0) != 0 or matches[0].get('rotation_deg', 0) != 0:
                    reason = 'Nonzero rotations require explicit review and are not supported for conversion.'
                if reason:
                    blocked.append({'item': component_id, 'reason': reason})
                elif not any(item['item'].startswith('base.') for item in blocked):
                    part = matches[0]
                    before = {axis: part['position'][axis] for axis in ('x', 'y', 'z')}
                    after = {axis: target[axis] for axis in ('x', 'y', 'z')}
                    if before != after:
                        operations.append({'type': 'MoveComponent', 'component_id': component_id,
                            'pdm_component_id': part['id'], 'before': before, 'after': after})
    return dict(status='BLOCKED' if blocked else 'REVIEW_REQUIRED',
        requires_explicit_acceptance=True, base=deepcopy(evidence),
        legacy_overlay=deepcopy(overlay), operations=operations, blocked=blocked,
        dirty_stages=['placement', 'routes', 'physical_validation', 'bom', 'cad'],
        explanation='Review the entire proposal before explicit application to a working draft. '
                    'No transforms, routing, validation or publication have been applied.')
