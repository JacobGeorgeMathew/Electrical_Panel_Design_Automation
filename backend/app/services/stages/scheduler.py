"""Explicit, detached dirty-closure execution. Save never calls this module.

The full DesignOrchestrator remains an independent oracle. This scheduler owns
candidate retry and projection only; adapters own engineering and the caller
owns catalog materialization, cache I/O and reviewed operation acceptance.
"""
from dataclasses import dataclass
from typing import Any
from time import perf_counter
from typing import Literal

from pydantic import Field

from app.models.cem import CanonicalEngineeringModel, CEMState
from app.models.document import (GenerationIntent, ResolvedDocument, SnapshotReference,
                                 snapshot_sha256)
from app.services.design_errors import DesignError
from app.services.stages import artifacts as a, electrical as e, physical as p
from app.services.stages.cache import ADAPTERS, make_signature
from app.services.stages.contracts import FrozenContract, STAGE_REGISTRY
from app.observability import traced, emit


def snapshot(value):
    """Capture JSON; the receiving typed boundary validates its exact schema."""
    return e.Snapshot[Any].capture(value)


class StageExecution(FrozenContract):
    stage_id: str
    adapter: str
    status: Literal['EXECUTED', 'CACHED', 'FAILED', 'RETAINED']
    executions: int = Field(ge=0)
    elapsed_ms: float = Field(ge=0)
    input_signature: str | None = None
    failure_code: str | None = None


@dataclass(frozen=True)
class SchedulerInputs:
    requirements: e.RequirementsInput
    components: e.PinnedComponents
    enclosures: p.PinnedEnclosures
    hardware: p.PinnedHardware
    layout: p.LayoutSnapshot
    previews: e.Snapshot[dict] | None = None


@dataclass(frozen=True)
class ScheduledResult:
    candidate: ResolvedDocument
    records: tuple[StageExecution, ...]
    cad: dict | None
    bom: list | None


def dirty_closure(document):
    """Dirty stage IDs are server-owned; a missing snapshot establishes its root."""
    dirty = set(document.document.dirty_stages)
    snapshots = document.snapshots
    if snapshots.cem is None:
        dirty.add('requirements')
    if snapshots.pdm is None:
        dirty.add('placement')
    if snapshots.schematic is None:
        dirty.add('schematic')
    for stage in STAGE_REGISTRY.ordered_ids():
        if stage in dirty or dirty.intersection(STAGE_REGISTRY.by_id[stage].prerequisites):
            dirty.add(stage)
    return tuple(s for s in STAGE_REGISTRY.ordered_ids() if s in dirty)


class IncrementalScheduler:
    def __init__(self, cache=None, execute_adapter=None, progress=None):
        self.cache = cache
        self.execute_adapter = execute_adapter
        self.records = []
        self.progress = progress

    def record(self, execution):
        self.records.append(execution)
        emit('stage', stage_id=execution.stage_id, status={
            'EXECUTED': 'succeeded', 'CACHED': 'cached', 'FAILED': 'failed',
            'RETAINED': 'retained'}[execution.status], elapsed_ms=execution.elapsed_ms,
            code=execution.failure_code)
        if self.progress:
            self.progress(None, self.records)

    def run(self, base: ResolvedDocument, inputs: SchedulerInputs, *, force_full=False):
        self.records = []
        candidate = ResolvedDocument.model_validate(base.model_dump(mode='json', include={'document', 'snapshots'}))
        doc, snapshots = candidate.document, candidate.snapshots
        context = inputs.requirements.context
        if (context.project_id, context.panel_id, context.engine_version) != (
                doc.project_id, doc.panel_id, doc.pins.engine_version):
            raise DesignError('STAGE_IDENTITY_MISMATCH', 'Scheduler context differs from the document.')
        dirty = set(STAGE_REGISTRY.ordered_ids() if force_full else dirty_closure(candidate))
        if not dirty:
            return ScheduledResult(candidate, (), None, None)
        intent = doc.generation_intent or GenerationIntent(
            manual_models=['cem', 'pdm', 'schematic'] if snapshots.cem else [])
        cem = snapshots.cem.model_copy(deep=True) if snapshots.cem else CanonicalEngineeringModel(
            project_id=doc.project_id, panel_id=doc.panel_id, panel_type='DB')
        policy = snapshots.pdm.validation_policy if snapshots.pdm else None

        @traced('stage', lambda name, value: dict(project_id=doc.project_id,
            document_id=doc.document_id, stage_id=ADAPTERS[name].stage_id))
        def execute(name, value):
            if self.progress:
                self.progress(name, self.records)
            started = perf_counter()
            signature = make_signature(name, value, doc.pins, policy=policy, context=context)
            binding = ADAPTERS[name]
            try:
                if self.cache:
                    self.cache.observe(doc.document_id, doc.document_sequence, signature)
                    hit = self.cache.lookup(signature)
                    if hit.integrity == 'VALID':
                        self.cache.accept_cached(doc.document_id, doc.document_sequence, signature)
                        self.record(StageExecution(stage_id=binding.stage_id, adapter=name,
                            status='CACHED', executions=0, elapsed_ms=(perf_counter()-started)*1000,
                            input_signature=signature.key))
                        return hit.output
                output = (self.execute_adapter(name, value, signature) if self.execute_adapter
                          else binding.execute(value))
            except DesignError as exc:
                if self.cache:
                    self.cache.record_failure(doc.document_id, doc.document_sequence, signature, exc.code)
                self.record(StageExecution(stage_id=binding.stage_id, adapter=name,
                    status='FAILED', executions=1, elapsed_ms=(perf_counter()-started)*1000,
                    input_signature=signature.key, failure_code=exc.code))
                raise
            if self.cache:
                self.cache.record_success(doc.document_id, doc.document_sequence, signature, output)
            self.record(StageExecution(stage_id=binding.stage_id, adapter=name,
                status='EXECUTED', executions=1, elapsed_ms=(perf_counter()-started)*1000,
                input_signature=signature.key))
            return output

        requirements = e.RequirementsOutput(validated_requirements=snapshot(snapshots.requirements),
            modules=snapshot(cem.modules))
        if 'requirements' in dirty:
            requirements = execute('requirements', inputs.requirements)
            old = {r.id: r for r in snapshots.requirements.items}
            snapshots.requirements = requirements.validated_requirements.read()
            snapshots.requirements.items = [old[r.id].model_copy(deep=True)
                if r.id in old and old[r.id].value == r.value else r for r in snapshots.requirements.items]
        cem.requirements = snapshots.requirements.items
        calculations = e.CalculationsOutput(calculations=snapshot(cem.calculations))
        if 'calculations' in dirty:
            calculations = execute('calculations', e.CalculationsInput(context=context, requirements=requirements))
            cem.calculations = calculations.calculations.read()
        selection = e.SelectionOutput(components=snapshot(cem.components), modules=snapshot(cem.modules))
        if 'selection' in dirty:
            selection = execute('selection', e.SelectionInput(context=context, requirements=requirements,
                calculations=calculations, catalog=inputs.components,
                accepted_components=snapshot(cem.components) if 'cem' in intent.manual_models else None))
            cem.components, cem.modules = selection.components.read(), selection.modules.read()
        connectivity = None
        if cem.electrical_graph is not None:
            connectivity = e.ConnectivityOutput(electrical_graph=snapshot(cem.electrical_graph),
                nets=snapshot(cem.nets), connections=snapshot(cem.connections))
        if 'connectivity' in dirty:
            connectivity = execute('connectivity', e.ConnectivityInput(context=context, requirements=requirements,
                selection=selection, intent=connectivity if 'cem' in intent.manual_models else None))
            cem.electrical_graph = connectivity.electrical_graph.read()
            cem.nets, cem.connections = connectivity.nets.read(), connectivity.connections.read()
        legacy_schematic = None
        if 'schematic' in dirty:
            if snapshots.schematic and 'schematic' in intent.manual_models:
                # Reference integrity is checked on the complete candidate below.
                self.record(StageExecution(stage_id='schematic', adapter='schematic',
                    status='RETAINED', executions=0, elapsed_ms=0))
            else:
                legacy_schematic = execute('schematic', e.SchematicInput(context=context,
                    selection=selection, connectivity=connectivity)).schematic.read()
        snapshots.cem = cem

        def cem_snapshot():
            return e.Snapshot[CanonicalEngineeringModel].capture(cem)

        def route_and_validate(pdm, layout):
            if 'routes' in dirty:
                pdm = execute('routes', p.RoutesInput(context=context, cem=cem_snapshot(), pdm=pdm, layout=layout)).pdm
            if 'physical_validation' in dirty:
                pdm = execute('physical_validation', p.PhysicalValidationInput(
                    context=context, cem=cem_snapshot(), pdm=pdm)).pdm
            return pdm

        if 'placement' in dirty:
            # Match the oracle's enclosure retry scope: routing/validation may
            # reject a candidate even when placement alone is feasible.
            selected = doc.configuration.get('enclosure_id')
            if snapshots.pdm and ('pdm' in intent.manual_models or intent.locked_placements):
                selected = selected or snapshots.pdm.enclosure_id
            # First-candidate signatures need the policy even before a PDM exists.
            from app.models.pdm import DesignValidationPolicy
            policy = policy or DesignValidationPolicy.from_layout(inputs.layout.read())
            enclosures = execute('enclosure', p.EnclosureInput(context=context, cem=cem_snapshot(),
                catalog=inputs.enclosures, layout=inputs.layout,
                ip_rating=requirements.values()['ip_rating'], enclosure_id=selected))
            last_error = None
            attempted = []
            for enclosure in enclosures.candidates.read():
                attempted.append(enclosure.id)
                try:
                    zoning = execute('zoning', p.ZoningInput(enclosure=snapshot(enclosure),
                        layout=inputs.layout, hardware=inputs.hardware))
                    placed = execute('placement', p.PlacementInput(context=context, cem=cem_snapshot(), zoning=zoning,
                        intent=snapshot(intent), accepted_layout=p.PhysicalSnapshot.capture(snapshots.pdm)
                        if snapshots.pdm and ('pdm' in intent.manual_models or intent.locked_placements) else None))
                    ducts = execute('ducts', p.DuctsInput(placement=placed))
                    pdm = route_and_validate(ducts.pdm, zoning.layout)
                    break
                except DesignError as exc:
                    if exc.code not in {'PLACEMENT_INFEASIBLE', 'PLACEMENT_INVALID', 'ROUTING_INFEASIBLE',
                                        'PHYSICAL_VALIDATION_FAILED', 'DUCT_SPACE_INFEASIBLE'}:
                        raise
                    last_error = exc
            else:
                last_error.details['attempted_enclosure_ids'] = attempted
                raise last_error
        else:
            pdm = route_and_validate(p.PhysicalSnapshot.capture(snapshots.pdm), inputs.layout)
        snapshots.pdm = pdm.read()
        # Physical identities belong to the accepted document, not the solver.
        if base.snapshots.pdm:
            snapshots.pdm.id = base.snapshots.pdm.id
            previous = {c.cem_component_id: c.id for c in base.snapshots.pdm.components}
            rebound = {c.id: previous.get(c.cem_component_id, c.id) for c in snapshots.pdm.components}
            for part in snapshots.pdm.components:
                part.id = rebound[part.id]
            for accessory in snapshots.pdm.accessories:
                accessory.parent_id = rebound.get(accessory.parent_id, accessory.parent_id)
        cem.physical_design_id = snapshots.pdm.id
        cem.state = CEMState.FINAL_VALIDATED
        if 'selection' in dirty:
            doc.pins.model_versions = {c.id: c.cad_model_version_id for c in cem.components if c.cad_model_version_id}
        if 'placement' in dirty:
            components = {c.id: c for c in cem.components}
            previews = inputs.previews.read() if inputs.previews else {}
            for part in snapshots.pdm.components:
                part.cad_model_version_id = components[part.cem_component_id].cad_model_version_id
                if inputs.previews:
                    part.preview_asset = previews.get(components[part.cem_component_id].catalog_id)
        if legacy_schematic is not None:
            from app.services.generation_proposals import schematic_presentation
            snapshots.schematic = schematic_presentation(doc, snapshots.schematic, legacy_schematic)
        if not any(i.component_id == 'PANEL_ROOT' for i in doc.enclosure_interfaces):
            from app.models.document import EnclosureInterface
            doc.enclosure_interfaces.append(EnclosureInterface(component_id='PANEL_ROOT', terminal_ids=['EARTH_STUD']))
        pdm = p.PhysicalSnapshot.capture(snapshots.pdm)
        bom = execute('bom', a.BOMInput(context=context, cem=cem_snapshot(), pdm=pdm)).bom.read() if 'bom' in dirty else None
        cad = execute('cad', a.CADInput(context=context, cem=cem_snapshot(), pdm=pdm,
            schematic=snapshot(snapshots.schematic.model_dump(mode='json')),
            generator_version=doc.pins.generator.version,
            model_versions=snapshot(doc.pins.model_versions))).cad.read() if 'cad' in dirty else None
        doc.generation_intent = intent
        doc.dirty_stages = []
        for kind in ('requirements', 'cem', 'pdm', 'schematic'):
            setattr(doc.models, kind, SnapshotReference(sha256=snapshot_sha256(getattr(snapshots, kind))))
        from pydantic import ValidationError
        try:
            candidate = ResolvedDocument.model_validate(candidate.model_dump(mode='json'))
        except ValidationError:
            raise DesignError('STAGE_INTENT_CONFLICT',
                'Recomputed outputs conflict with retained document references. Review manual intent.') from None
        return ScheduledResult(candidate, tuple(self.records), cad, bom)
