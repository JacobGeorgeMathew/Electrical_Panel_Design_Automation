"""Server-owned deterministic generation proposals over the shared operation boundary.

Clients submit inputs and a reviewed digest, never authoritative output snapshots.
Acceptance uses the exact server-retained preview outside database transactions.
No artifacts or revisions are published here; the accepted batch is one undo group.
"""
from collections import OrderedDict
from threading import RLock
from time import monotonic
from weakref import WeakKeyDictionary
from uuid import uuid4

from app.models.document import (ResolvedDocument, DocumentSnapshots, SnapshotReference,
                                 PinnedVersions, EnclosureInterface, GenerationIntent, snapshot_sha256)
from app.models.operations import OperationPreviewRequest
from app.models.schematic import SchematicPresentation, SchematicSymbol, SchematicPin, SchematicWire
from app.persistence.assets import content_hash
from app.persistence.documents import document_hash
from app.persistence.repositories import PersistenceError


KINDS = ('requirements', 'cem', 'pdm', 'schematic')
_proposals = WeakKeyDictionary()
_proposal_lock = RLock()
PROPOSAL_TTL_SECONDS = 900
MAX_PROPOSALS = 32


def remember_proposal(database, base, request, candidate):
    """Bounded, process-local review state; restart/expiry requires new preview."""
    with _proposal_lock:
        entries = _proposals.setdefault(database, OrderedDict())
        entries[str(request.batch_id)] = (monotonic() + PROPOSAL_TTL_SECONDS,
            content_hash(request.model_dump(mode='json')), document_hash(base.document),
            candidate.model_dump(mode='json', include={'document', 'snapshots'}))
        while len(entries) > MAX_PROPOSALS:
            entries.popitem(last=False)


def digest(candidate):
    return content_hash(dict(models=candidate.document.models.model_dump(mode='json'),
        pins=candidate.document.pins.model_dump(mode='json'),
        interfaces=[i.model_dump(mode='json') for i in candidate.document.enclosure_interfaces]))


def conflicts(base, candidate):
    result = []
    # Conservatively protect all manually edited engineering models. Explicit
    # placement locks are useful for imported documents without operation history.
    intent = base.document.generation_intent
    # Old/imported engineering snapshots lack operation-owned intent metadata.
    # Treat changes as conflicts rather than assume their geometry is disposable.
    protected = intent.manual_models if intent else (('cem', 'pdm', 'schematic') if base.snapshots.cem else ())
    for kind in protected:
        if kind in KINDS and getattr(base.document.models, kind) != getattr(candidate.document.models, kind):
            result.append(dict(target=kind, reason='Generation would replace manual engineering intent.'))
    old = {c.cem_component_id: c for c in base.snapshots.pdm.components} if base.snapshots.pdm else {}
    new = {c.cem_component_id: c for c in candidate.snapshots.pdm.components}
    for key in intent.locked_placements if intent else []:
        a, b = old.get(key), new.get(key)
        if a is None or b is None or any(getattr(a, f) != getattr(b, f) for f in (
                'position', 'rotation_deg', 'rail_id', 'zone_name', 'width', 'height', 'depth')):
            result.append(dict(target=key, reason='Generation would overwrite a locked placement.'))
    return result


def generated_document(base, requirements, result, manifest):
    """Bind the pipeline's deterministic logical identities to this document."""
    candidate = ResolvedDocument.model_validate(base.model_dump(mode='json', include={'document', 'snapshots'}))
    doc = candidate.document
    doc.generation_intent = doc.generation_intent or GenerationIntent()
    cem, pdm = result['cem'].copy(), result['pdm'].copy()
    for value in (cem, pdm):
        value.update(project_id=doc.project_id, panel_id=doc.panel_id)
    if cem.get('electrical_graph'):
        cem['electrical_graph'] = {**cem['electrical_graph'], 'project_id': doc.project_id}
    if base.snapshots.pdm:
        pdm['id'] = base.snapshots.pdm.id
        old = {c.cem_component_id: c.id for c in base.snapshots.pdm.components}
        rebound = {c['id']: old.get(c['cem_component_id'], c['id']) for c in pdm['components']}
        pdm['components'] = [{**c, 'id': old.get(c['cem_component_id'], c['id'])} for c in pdm['components']]
        pdm['accessories'] = [{**a, 'parent_id': rebound.get(a['parent_id'], a['parent_id'])}
                              for a in pdm.get('accessories', [])]
    cem['physical_design_id'] = pdm['id']
    requirements = requirements.model_copy(update={'project_id': doc.project_id}, deep=True)
    # Preserve source/confirmation metadata for unchanged input intent.
    old_requirements = {r.id: r for r in base.snapshots.requirements.items}
    requirements.items = [old_requirements[r.id].model_copy(deep=True)
        if r.id in old_requirements and old_requirements[r.id].value == r.value else r for r in requirements.items]
    cem['requirements'] = [r.model_dump(mode='json') for r in requirements.items]
    legacy = result['schematic']
    previous = base.snapshots.schematic
    old_symbols = {s.component_id: s for s in previous.symbols} if previous else {}
    symbols = []
    for s in legacy['symbols']:
        old = old_symbols.get(s['id'])
        pins = {p.terminal_id: p for p in old.pins} if old else {}
        symbols.append(SchematicSymbol(id=old.id if old else 'symbol:' + s['id'], component_id=s['id'],
            position=dict(x=s['x'], y=s['y']), width_mm=s['width'], height_mm=s['height'], label=s['label'],
            pins=[SchematicPin(id=pins[t['id']].id if t['id'] in pins else 'pin:' + t['port_id'],
                terminal_id=t['id'], position=dict(x=t['x'], y=t['y']), direction=t['direction']) for t in s['terminals']]))
    pins = {(s.component_id, p.terminal_id): p.id for s in symbols for p in s.pins}
    old_wires = {w.conductor_id: w.id for w in previous.wires} if previous else {}
    page = SchematicPresentation(id=previous.id if previous else 'schematic:' + doc.panel_id,
        project_id=doc.project_id, panel_id=doc.panel_id, page_id=previous.page_id if previous else 'page:' + doc.panel_id,
        width_mm=legacy['width'], height_mm=legacy['height'], symbols=symbols,
        wires=[SchematicWire(id=old_wires.get(w['id'], 'wire:' + w['id']), conductor_id=w['id'],
            source_pin_id=pins[w['from'], w['from_terminal']], target_pin_id=pins[w['to'], w['to_terminal']],
            waypoints=w['waypoints']) for w in legacy['wires']])
    root = next((i for i in doc.enclosure_interfaces if i.component_id == 'PANEL_ROOT'), None)
    if root is None:
        doc.enclosure_interfaces.append(EnclosureInterface(component_id='PANEL_ROOT', terminal_ids=['EARTH_STUD']))
    elif 'EARTH_STUD' not in root.terminal_ids:
        root.terminal_ids.append('EARTH_STUD')
    doc.pins = PinnedVersions(engine_version=manifest['engine_version'], generator=manifest['generator'],
        catalog_manifest_sha256=content_hash(manifest), validation_policy_version=manifest['validation_policy_version'],
        catalog_versions={'archetype': manifest['archetype_version_id'], 'rules': manifest['rule_set_version_id']},
        model_versions={k: v for k, v in manifest['cad_model_versions'].items() if v})
    candidate.snapshots = DocumentSnapshots(requirements=requirements, cem=cem, pdm=pdm, schematic=page)
    for kind in KINDS:
        setattr(doc.models, kind, SnapshotReference(sha256=snapshot_sha256(getattr(candidate.snapshots, kind))))
    # Derived data is computed, but publication/artifact generation is separate.
    doc.dirty_stages = ['cad']
    return ResolvedDocument.model_validate(candidate.model_dump(mode='json'))


def resolve_generation(database, key, base, overrides):
    from app.services.project_service import ProjectService
    source, requirements, result, manifest = ProjectService(database).generate(
        key, overrides, base.document.lock_version, propose=True)
    if document_hash(ResolvedDocument.model_validate({k: source[k] for k in ('document', 'snapshots')}).document) != document_hash(base.document):
        raise PersistenceError('DOCUMENT_CONFLICT', 'Generation base changed. Preview again.', 409)
    return generated_document(base, requirements, result, manifest)


def apply_generation(candidate, op, choices):
    generated = choices.generation
    if generated is None or op.target.panel_id != candidate.document.panel_id:
        raise PersistenceError('GENERATION_CONTEXT', 'Server generation context is required.', 409)
    if (op.origin.kind != 'AUTOMATIC' or op.proposal_status != 'PROPOSED'
            or digest(generated) != op.parameters.candidate_sha256):
        raise PersistenceError('GENERATION_PROPOSAL_CHANGED', 'Generation differs from the reviewed proposal. Preview again.', 409)
    blocked = conflicts(candidate, generated)
    if blocked:
        raise PersistenceError('GENERATION_INTENT_CONFLICT', 'Generation would replace manual intent. Review conflicts.', 409)
    candidate.snapshots = generated.snapshots.model_copy(deep=True)
    candidate.document.pins = generated.document.pins.model_copy(deep=True)
    candidate.document.enclosure_interfaces = generated.document.enclosure_interfaces
    candidate.document.generation_intent = generated.document.generation_intent
    candidate.document.dirty_stages = generated.document.dirty_stages.copy()
    return ['components', 'connections', 'presentation', 'value']


def generation_choices(database, key, base, request, choices):
    from dataclasses import replace
    operations = [op for op in request.operations if op.type == 'ApplyGeneration']
    if not operations:
        return choices
    if len(request.operations) != 1:
        raise PersistenceError('GENERATION_BATCH', 'Generation must be reviewed as one standalone batch.', 409)
    with _proposal_lock:
        entries = _proposals.get(database, {})
        stored = entries.get(str(request.batch_id))
        if stored is None or stored[0] <= monotonic():
            raise PersistenceError('GENERATION_PROPOSAL_EXPIRED', 'Generation preview expired or server restarted. Preview again.', 409)
        if stored[1] != content_hash(request.model_dump(mode='json')) or stored[2] != document_hash(base.document):
            raise PersistenceError('GENERATION_PROPOSAL_CHANGED', 'Proposal or document base changed. Preview again.', 409)
        generated = ResolvedDocument.model_validate(stored[3])
    return replace(choices, generation=generated)


def propose_generation(database, key, overrides=None):
    from app.services.document_service import DocumentService
    from app.services.operations.engineering import EngineeringChoices
    from app.services.operations.registry import preview_operations
    base = DocumentService(database).load(key)
    generated = resolve_generation(database, key, base, overrides or {})
    blocked = conflicts(base, generated)
    if blocked:
        return dict(status='CONFLICT', persisted=False, conflicts=blocked, batch=None)
    doc = base.document
    proposal_id = str(uuid4())
    batch = OperationPreviewRequest.model_validate(dict(batch_id=proposal_id, document_id=doc.document_id,
        base_sequence=doc.document_sequence, expected_version=doc.lock_version, base_revision_id=doc.base_revision_id,
        operations=[dict(type='ApplyGeneration', operation_id=str(uuid4()), proposal_status='PROPOSED',
            origin=dict(kind='AUTOMATIC', actor_id='local-user', proposal_id=proposal_id),
            target=dict(panel_id=doc.panel_id), parameters=dict(overrides=overrides or {}, candidate_sha256=digest(generated)),
            preconditions=dict(snapshot_sha256=doc.models.requirements.sha256,
                model_sha256={k: getattr(doc.models, k).sha256 if getattr(doc.models, k) else None for k in KINDS}))]))
    preview = preview_operations(base, batch, EngineeringChoices(generation=generated))
    remember_proposal(database, base, batch, generated)
    return dict(status='REVIEW_REQUIRED', persisted=False, conflicts=[], batch=batch, preview=preview)
