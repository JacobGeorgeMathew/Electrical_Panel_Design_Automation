"""Materialize runtime catalogs, execute detached stages and retain a review batch."""
from uuid import uuid4

from app.models.document import ResolvedDocument
from app.models.operations import OperationPreviewRequest
from app.models.pdm import EnclosureSpec
from app.persistence.assets import content_hash
from app.persistence.documents import document_hash
from app.persistence.repositories import PersistenceError
from app.services.document_service import DocumentService
from app.services.generation_proposals import propose_candidate
from app.services.stages import electrical as e, physical as p
from app.services.stages.cache import StageCache
from app.services.stages.scheduler import IncrementalScheduler, SchedulerInputs, dirty_closure, snapshot


def check_base(base, request):
    doc = base.document
    if (doc.document_id, doc.document_sequence, doc.lock_version) != (
            request.document_id, request.expected_document_sequence, request.expected_version):
        raise PersistenceError('DOCUMENT_CONFLICT', 'Working document changed. Retain edits and reload.', 409)


def materialize(service, source):
    """Read catalog inputs once, close the transaction, then build typed inputs.

    Existing exact pins must match: this endpoint never silently upgrades a
    saved catalog. Older generation documents lack aggregate catalog pins; their
    per-component version references are checked before binding content hashes.
    """
    project, template, rows, enclosures, models, _, _, rules_version, layout, hardware = service._inputs(
        source.document.project_id, resolve_capabilities=False)
    observed = ResolvedDocument.model_validate({k: project['_source_document'][k] for k in ('document', 'snapshots')})
    if (document_hash(observed.document), observed.document.document_sequence, observed.document.lock_version) != (
            document_hash(source.document), source.document.document_sequence, source.document.lock_version):
        raise PersistenceError('DOCUMENT_CONFLICT', 'Document changed during input resolution.', 409)
    base = ResolvedDocument.model_validate(source.model_dump(mode='json', include={'document', 'snapshots'}))
    doc = base.document
    from app.services.project_service import ENGINE_VERSION
    if doc.pins.engine_version != ENGINE_VERSION or doc.pins.generator.model_dump() != dict(name='panelstudio-primitives', version='3'):
        raise PersistenceError('GENERATOR_VERSION_UNAVAILABLE', 'Working document requires another engine or generator.', 409)
    catalogs = dict(archetype=template['archetype_version_id'], rules=rules_version,
        components=content_hash(rows), enclosures=content_hash(enclosures), hardware=content_hash(hardware))
    mismatched = [key for key, value in catalogs.items() if doc.pins.catalog_versions.get(key, value) != value]
    if mismatched:
        raise PersistenceError('STAGE_CATALOG_CONFLICT',
            'Exact working catalog pins are unavailable: '+', '.join(mismatched)+'. Review a catalog upgrade.', 409)
    by_code = {r['id']: r for r in rows}
    if base.snapshots.cem:
        for component in base.snapshots.cem.components:
            row = by_code.get(component.catalog_id)
            if row is None or any(getattr(component, field) is not None and getattr(component, field) != row.get(field)
                    for field in ('component_version_id', 'product_version_id')):
                raise PersistenceError('STAGE_CATALOG_CONFLICT', 'A saved component version is unavailable.', 409)
            model = next(iter(models.get(component.catalog_id, [])), None)
            if component.cad_model_version_id and component.cad_model_version_id != (model['id'] if model else None):
                raise PersistenceError('STAGE_CATALOG_CONFLICT', 'A saved CAD model version is unavailable.', 409)
    # These are immutable content identities for the complete ordered catalog
    # inputs, alongside each row's published database version IDs.
    doc.pins.catalog_versions.update(catalogs)
    if 'requirements' in dirty_closure(base):
        # Questionnaire capability inference also exercises connectivity. Only
        # requirement changes need it, and all reads have already ended.
        from app.services.questionnaire_choices import resolve_choices
        template = resolve_choices(template, rows)
    for row in rows:
        model = next(iter(models.get(row['id'], [])), None)
        row['cad_model_version_id'] = model['id'] if model else None
    enclosures, _ = service.configure_enclosures(enclosures, doc.configuration)
    context = e.ElectricalContext(project_id=doc.project_id, panel_id=doc.panel_id,
                                  engine_version=doc.pins.engine_version)
    requirements = e.RequirementsInput(context=context,
        answers=snapshot({r.id: r.value for r in base.snapshots.requirements.items if r.value is not None}),
        rules=e.PinnedRules(archetype_version=catalogs['archetype'], rules_version=catalogs['rules'],
                            template=snapshot(template)))
    return base, SchedulerInputs(requirements=requirements,
        components=e.PinnedComponents(catalog_version=catalogs['components'], rows=snapshot(rows)),
        enclosures=p.PinnedEnclosures(catalog_version=catalogs['enclosures'],
            rows=e.Snapshot[list[EnclosureSpec]].capture(enclosures)),
        hardware=p.PinnedHardware(catalog_version=catalogs['hardware'], rows=snapshot(hardware)),
        layout=p.LayoutSnapshot.capture(layout), previews=snapshot({code: next(
            (a for model in entries[:1] for a in model['assets'] if a['file_format'] == 'GLB'), None)
            for code, entries in models.items()}))


def recompute(service, key, request):
    source = DocumentService(service.db).load(key)
    check_base(source, request)
    base, inputs = materialize(service, source)
    from app.jobs.runner import StageExecutor
    scheduler = IncrementalScheduler(StageCache(service.db),
                                     execute_adapter=StageExecutor(service.db, source))
    try:
        result = scheduler.run(base, inputs)
    except Exception as exc:
        # Keep the structured engineering error and include the actual attempted
        # executions. No document/revision/artifact is changed on failure.
        from app.services.design_errors import DesignError
        if isinstance(exc, DesignError):
            exc.details['stage_executions'] = [r.model_dump(mode='json') for r in scheduler.records]
        raise
    current = DocumentService(service.db).load(key)
    check_base(current, request)
    if document_hash(current.document) != document_hash(source.document):
        raise PersistenceError('DOCUMENT_CONFLICT', 'Document changed during recomputation.', 409)
    proposal = propose_candidate(service.db, source, result.candidate, recompute=True)
    return {**proposal, 'scheduled_stages': list(dirty_closure(base)),
            'stage_executions': list(result.records)}


def preview_change(service, key, field, value, expected_version=None):
    """Legacy change entry point now returns an ordinary operation preview."""
    base = DocumentService(service.db).load(key)
    doc = base.document
    if expected_version is not None and expected_version != doc.lock_version:
        raise PersistenceError('DOCUMENT_CONFLICT', 'Project changed. Reload before previewing.', 409)
    request = OperationPreviewRequest.model_validate(dict(batch_id=str(uuid4()), document_id=doc.document_id,
        base_sequence=doc.document_sequence, expected_version=doc.lock_version, base_revision_id=doc.base_revision_id,
        operations=[dict(type='UpdateRequirement', operation_id=str(uuid4()),
            origin=dict(kind='MANUAL', actor_id='local-user'), target=dict(requirement_id=field),
            parameters=dict(value=value), preconditions=dict(snapshot_sha256=doc.models.requirements.sha256))]))
    return dict(status='PREVIEW', persisted=False, batch=request,
                preview=DocumentService(service.db).preview_operations(key, request))
