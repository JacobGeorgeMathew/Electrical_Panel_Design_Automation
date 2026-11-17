"""Server-owned placement inputs and fenced, evidence-only publication.

Publication never executes a missing stage or substitutes client output. Current
prototype reports retain unresolved engineering obligations and therefore block
publication until independently supported evidence is available.
"""
from sqlalchemy import select
from pydantic import Field

from app.models.recompute import RecomputeRequest
from app.persistence import models as m
from app.persistence.assets import content_hash
from app.persistence.documents import document_hash
from app.persistence.repositories import PersistenceError, ProjectRepository
from app.services.document_service import DocumentService
from app.services.recompute import check_base, materialize
from app.services.stages.cache import StageCache
from app.services.stages.scheduler import IncrementalScheduler
from app.services.validation_report import build_validation_report


class PublishRequest(RecomputeRequest):
    report_signature: str = Field(pattern=r'^[a-f0-9]{64}$')


def reject(code, message):
    raise PersistenceError(code, message, 409)


def placement_inputs(service, key, submitted):
    """Only transforms are editable; catalog geometry/policy remain server-owned."""
    base = DocumentService(service.db).load(key)
    cem, saved = base.snapshots.cem, base.snapshots.pdm
    if cem is None or saved is None:
        reject('PLACEMENT_BASE_REQUIRED', 'Accept server-generated working geometry before placement validation.')
    if (submitted.project_id, submitted.panel_id, submitted.id) != (saved.project_id, saved.panel_id, saved.id):
        reject('PROJECT_MISMATCH', 'Placement ownership differs from the saved document.')
    expected = {c.id: c for c in saved.components}
    if (len(submitted.components) != len(expected)
            or {c.id for c in submitted.components} != set(expected)
            or any(c.cem_component_id != expected[c.id].cem_component_id for c in submitted.components)):
        reject('COMPONENT_MISMATCH', 'Placement components must match the saved document.')
    # Materialization checks exact catalog/model pins without optimization or writes.
    _, inputs = materialize(service, base)
    catalog = {row['id']: row for row in inputs.components.rows.read()}
    devices = {c.id: c for c in cem.components}
    if {c.cem_component_id for c in saved.components} != set(devices):
        reject('COMPONENT_MISMATCH', 'Recompute the changed working component inventory before validation.')
    result = saved.model_copy(deep=True)
    edits = {c.id: c for c in submitted.components}
    for component in result.components:
        edit = edits[component.id]
        device = devices[component.cem_component_id]
        row = catalog[device.catalog_id]
        for field in ('width', 'height', 'depth', 'category', 'terminals', 'cad_model'):
            setattr(component, field, row[field])
        component.heat_loss_watts = row['heat_loss']
        component.cad_model_version_id = row['cad_model_version_id']
        if edit.rotation_deg != component.rotation_deg or edit.rotation_deg % 360:
            reject('PLACEMENT_ROTATION_UNSUPPORTED', 'Rotated placement requires supported routing geometry.')
        # Terminal anchors are catalog-local; routing applies the transform.
        component.position = edit.position.model_copy(deep=True)
        # Rail/zone affiliation also comes from the saved model; callers cannot
        # lower clearance requirements by assigning devices to a fabricated rail.
    result.total_heat_loss_watts = sum(c.heat_loss_watts for c in result.components)
    result.validation_results = []
    return result, cem


def validation_evidence(base):
    if base.snapshots.cem is None or base.snapshots.pdm is None:
        reject('PUBLISH_OUTPUTS_REQUIRED', 'Working engineering snapshots are missing. Recompute and accept them.')
    report = build_validation_report(base.snapshots.cem, base.snapshots.pdm,
        physical_evaluated=not base.document.dirty_stages,
        current=not base.document.dirty_stages)
    signature = content_hash(dict(document_id=base.document.document_id,
        sequence=base.document.document_sequence, content_sha256=document_hash(base.document),
        report=report.model_dump(mode='json')))
    return dict(document_id=base.document.document_id,
        document_sequence=base.document.document_sequence,
        report_signature=signature, aggregate=report)


class PublicationCache:
    """Read the attached result only; never repair state or execute on a miss."""
    def __init__(self, database, base):
        self.cache = StageCache(database)
        with database.sessions() as session:
            rows = session.execute(select(m.document_stage_states, m.stage_results.c.signature,
                m.stage_results.c.result, m.stage_results.c.assets, m.stage_results.c.result_sha256,
                m.stage_results.c.id.label('cache_id'),
                m.stage_results.c.adapter.label('cache_adapter'),
                m.stage_results.c.stage_id.label('cache_stage_id'),
                m.stage_results.c.input_signature.label('cache_input_signature')).outerjoin(m.stage_results,
                m.stage_results.c.id == m.document_stage_states.c.result_id).where(
                m.document_stage_states.c.document_id == base.document.document_id)).mappings().all()
            self.rows = {row['adapter']: dict(row) for row in rows}
            self.states = {row['adapter']: {field: row[field] for field in m.document_stage_states.c.keys()}
                for row in rows}

    def check_current(self, session, document_id):
        # StageCache mutations acquire the same project lock as publication.
        # The caller holds it before this read, fencing status-only changes too.
        rows = session.execute(select(m.document_stage_states).where(
            m.document_stage_states.c.document_id == document_id)).mappings()
        if {row['adapter']: dict(row) for row in rows} != self.states:
            reject('PUBLISH_STAGE_CONFLICT', 'Stage evidence changed during publication. Review current outputs.')

    def observe(self, document_id, sequence, signature):
        row = self.rows.get(signature.manifest['adapter'])
        if (row is None or row['status'] != 'VALID' or row['integrity'] != 'VALID'
                or row['blocked_by'] or row['input_signature'] != signature.key
                or row['output_signature'] != signature.key or not row['result_id']):
            reject('PUBLISH_STAGE_STALE', 'Required stage output is missing or stale. Recompute and accept outputs.')

    def lookup(self, signature):
        row = self.rows[signature.manifest['adapter']].copy()
        row['id'] = row['cache_id']
        row['adapter'] = row['cache_adapter']
        row['stage_id'] = row['cache_stage_id']
        row['input_signature'] = row['cache_input_signature']
        hit = self.cache._verify(row, signature)
        if hit.integrity != 'VALID':
            reject('PUBLISH_STAGE_INTEGRITY', 'Required stage evidence is unavailable or incompatible.')
        return hit

    def accept_cached(self, *args):
        pass


def publish(service, key, request):
    source = DocumentService(service.db).load(key)
    check_base(source, request)
    if source.document.dirty_stages:
        reject('PUBLISH_STAGE_STALE', 'Dirty working outputs cannot be published. Recompute and accept outputs.')
    evidence = validation_evidence(source)
    if request.report_signature != evidence['report_signature']:
        reject('PUBLISH_REPORT_CONFLICT', 'Validation report changed. Review the current report.')
    base, inputs = materialize(service, source)
    # Replay the dependency plan from exact cached inputs, without engineering
    # execution, cache writes, implicit acceptance or generating missing outputs.
    def missing(*args):
        reject('PUBLISH_OUTPUTS_REQUIRED', 'Required stage evidence is missing.')
    cache = PublicationCache(service.db, base)
    result = IncrementalScheduler(cache, execute_adapter=missing).run(
        base, inputs, force_full=True)
    required = {'requirements', 'calculations', 'selection', 'connectivity', 'schematic',
        'enclosure', 'zoning', 'placement', 'ducts', 'routes', 'physical_validation', 'bom', 'cad'}
    if {r.adapter for r in result.records if r.status == 'CACHED'} != required:
        reject('PUBLISH_OUTPUTS_REQUIRED', 'All required outputs need current stage evidence, including retained manual outputs.')
    if result.candidate.snapshots != source.snapshots or result.candidate.document.pins != source.document.pins:
        reject('PUBLISH_OUTPUTS_CHANGED', 'Stage outputs differ from the accepted working document.')
    report = evidence['aggregate']
    if report.required_status != 'PASS' or not report.engineering_release_eligible:
        reject('PUBLISH_VALIDATION_REQUIRED', 'Required validation is failed, unresolved or unreviewed. Draft Save remains available.')
    # All catalog reads and stage verification have ended before artifact I/O.
    project, template, rows, enclosures, models, templates, rules, rsv, layout, hardware = service._inputs(key)
    observed_pins = dict(archetype=template['archetype_version_id'], rules=rsv,
        components=content_hash(rows), enclosures=content_hash(enclosures), hardware=content_hash(hardware))
    if any(source.document.pins.catalog_versions.get(k) != v for k, v in observed_pins.items()):
        reject('PUBLISH_CATALOG_CONFLICT', 'Catalog inputs changed during publication.')
    current = DocumentService(service.db).load(key)
    check_base(current, request)
    if document_hash(current.document) != document_hash(source.document):
        reject('DOCUMENT_CONFLICT', 'Document changed during publication.')
    cem, pdm = source.snapshots.cem, source.snapshots.pdm
    enclosures, _ = service.configure_enclosures(enclosures, source.document.configuration)
    enclosure = next((e for e in enclosures if e['id'] == pdm.enclosure_id), None)
    if enclosure is None:
        reject('PUBLISH_CATALOG_CONFLICT', 'Saved enclosure version is unavailable.')
    enc_model = next(iter(enclosure['parameters']), None)
    manifest = dict(engine_version=source.document.pins.engine_version,
        archetype_version_id=template['archetype_version_id'], questionnaire_version_id=template['questionnaire_version_id'],
        electrical_templates=templates, rule_set_version_id=rsv, rule_versions=[r['id'] for r in rules],
        validation_rule_versions={r['code'].removeprefix('VALIDATION_'): r['id'] for r in rules if r['code'].startswith('VALIDATION_')},
        component_versions={c.id: c.component_version_id for c in cem.components},
        product_versions={c.id: c.product_version_id for c in cem.components},
        cad_model_versions={c.id: c.cad_model_version_id for c in cem.components},
        enclosure_component_version_id=enclosure['component_version_id'],
        enclosure_cad_model_version_id=enc_model['id'] if enc_model else None,
        hardware_component_versions={h['code']: h['component_version_id'] for h in hardware},
        validation_policy_version=pdm.validation_policy.version,
        generator=source.document.pins.generator.model_dump(mode='json'),
        report_signature=evidence['report_signature'])
    answers = {r.id: r.value for r in source.snapshots.requirements.items if r.value is not None}
    from app.persistence.repositories import serial
    manifest['layout_config'] = serial({**layout.__dict__, 'weights': layout.weights.__dict__,
        'din_categories': sorted(layout.din_categories), 'plate_categories': sorted(layout.plate_categories)})
    manifest['input_sha256'] = content_hash(dict(requirements=answers, configuration=source.document.configuration))
    project['configuration'] = source.document.configuration
    outputs = dict(cem=cem.model_dump(mode='json'), pdm=pdm.model_dump(mode='json'),
        schematic=source.snapshots.schematic.model_dump(mode='json'), bom=result.bom, cad=result.cad,
        validation_errors=[v.model_dump(mode='json') for v in pdm.validation_results])
    files = service.generate_files(outputs)
    from app.persistence.revision_outputs import prepare_outputs
    from app.persistence.revisions import write_revision
    prepared = prepare_outputs(project, source.snapshots.requirements, answers, outputs, manifest,
        files, source.model_dump(mode='json'), service.assets, request.expected_version)
    with service.db.sessions.begin() as session:
        ProjectRepository(session).check_version(key, request.expected_version)
        cache.check_current(session, source.document.document_id)
        saved = write_revision(session, project, template, source.snapshots.requirements, answers,
            outputs, manifest, files, request.expected_version, outputs=prepared)
    return service.load_revision(key, saved['revision_id'])
