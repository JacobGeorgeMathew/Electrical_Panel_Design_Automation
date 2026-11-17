"""Content signatures and explicit stage-result storage, without a scheduler.

Callers materialize typed inputs and exact pins before hashing. ``lookup`` never
executes engineering. After explicit detached execution, ``record_success`` (or
``accept_cached``) attaches only cache metadata, fenced by document sequence.
Working snapshots, revisions, project locks and recovery clocks are untouched.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from types import MappingProxyType
from typing import Callable, Literal
from uuid import UUID, uuid4

from pydantic import Field
from sqlalchemy import insert, select, update

from app.models.document import DirtyStage, PinnedVersions, SHA256
from app.models.identity import StableID
from app.models.pdm import DesignValidationPolicy
from app.persistence import models as m
from app.persistence.assets import AssetStore, AssetUnavailable, canonical_json, content_hash
from app.persistence.repositories import PersistenceError, ProjectRepository
from app.services.stages import artifacts as a, electrical as e, physical as p
from app.services.stages.contracts import FrozenContract, STAGE_REGISTRY


@dataclass(frozen=True)
class Adapter:
    stage_id: DirtyStage
    inputs: type[FrozenContract]
    outputs: type[FrozenContract]
    execute: Callable


# Placement has four serial boundaries. Keeping their names/types in signatures
# prevents an enclosure candidate from masquerading as a completed placement.
ADAPTERS = MappingProxyType({
    'requirements': Adapter('requirements', e.RequirementsInput, e.RequirementsOutput, e.requirements_stage),
    'calculations': Adapter('calculations', e.CalculationsInput, e.CalculationsOutput, e.calculations_stage),
    'selection': Adapter('selection', e.SelectionInput, e.SelectionOutput, e.selection_stage),
    'connectivity': Adapter('connectivity', e.ConnectivityInput, e.ConnectivityOutput, e.connectivity_stage),
    'schematic': Adapter('schematic', e.SchematicInput, e.SchematicOutput, e.schematic_stage),
    'enclosure': Adapter('placement', p.EnclosureInput, p.EnclosureOutput, p.enclosure_stage),
    'zoning': Adapter('placement', p.ZoningInput, p.ZoningOutput, p.zoning_stage),
    'placement': Adapter('placement', p.PlacementInput, p.PlacementOutput, p.placement_stage),
    'ducts': Adapter('placement', p.DuctsInput, p.PhysicalOutput, p.ducts_stage),
    'routes': Adapter('routes', p.RoutesInput, p.PhysicalOutput, p.routes_stage),
    'local_geometry': Adapter('physical_validation', p.GeometryInput, p.PhysicalOutput, p.local_geometry_stage),
    'physical_validation': Adapter('physical_validation', p.PhysicalValidationInput, p.PhysicalOutput,
                                   p.physical_validation_stage),
    'bom': Adapter('bom', a.BOMInput, a.BOMOutput, a.bom_stage),
    'cad': Adapter('cad', a.CADInput, a.CADOutput, a.cad_stage),
})


class StageSignature(FrozenContract):
    """Immutable canonical manifest; the key is always derived, never supplied."""
    manifest_json: str

    @property
    def manifest(self):
        return json.loads(self.manifest_json)

    @property
    def key(self):
        return content_hash(self.manifest)


class ManagedAsset(FrozenContract):
    storage_backend: Literal['LOCAL'] = 'LOCAL'
    storage_key: StableID
    sha256: SHA256
    byte_size: int = Field(ge=0, strict=True)


@dataclass(frozen=True)
class CacheLookup:
    integrity: Literal['MISSING', 'VALID', 'CORRUPT']
    result_id: UUID | None = None
    output: FrozenContract | None = None
    result_sha256: str | None = None


class StageState(FrozenContract):
    document_id: StableID
    adapter: StableID
    stage_id: DirtyStage
    document_sequence: int
    input_version: int
    output_version: int
    input_signature: SHA256
    output_signature: SHA256 | None
    result_id: str | None
    status: Literal['DIRTY', 'BLOCKED', 'FAILED', 'VALID']
    integrity: Literal['MISSING', 'VALID', 'CORRUPT']
    blocked_by: tuple[StableID, ...]
    failure_code: StableID | None


def _ancestors(stage_id):
    relevant = {stage_id}
    for candidate in reversed(STAGE_REGISTRY.ordered_ids()):
        if candidate in relevant:
            relevant.update(STAGE_REGISTRY.by_id[candidate].prerequisites)
    return tuple(s for s in STAGE_REGISTRY.ordered_ids() if s in relevant)


def _walk(value):
    if isinstance(value, FrozenContract):
        yield value
        for field in type(value).model_fields:
            yield from _walk(getattr(value, field))


def make_signature(adapter: str, inputs: FrozenContract, pins: PinnedVersions,
                   policy: DesignValidationPolicy | None = None,
                   context: e.ElectricalContext | None = None) -> StageSignature:
    """Hash the complete detached input boundary, retaining list order and IDs.

    Version dependencies include registry ancestors: a changed rule cannot be
    hidden by an unchanged upstream numeric result. Aggregate catalog manifest
    hashes are excluded; exact consumed pins/content determine eligibility.
    Unknown catalog keys conservatively invalidate all stages.
    """
    binding = ADAPTERS[adapter]
    if type(inputs) is not binding.inputs:
        raise ValueError('Input type differs from the registered adapter.')
    inputs = binding.inputs.model_validate_json(inputs.model_dump_json())
    pins = PinnedVersions.model_validate(pins.model_dump(mode='json'))
    context = getattr(inputs, 'context', None) or context
    if context is None or context.engine_version != pins.engine_version:
        raise ValueError('Supply matching document context and engine pins.')
    stages = _ancestors(binding.stage_id)
    paths = {path for stage in stages for item in STAGE_REGISTRY.by_id[stage].inputs for path in item.paths}
    catalog_keys = {path.removeprefix('pins.catalog_versions.') for path in paths
                    if path.startswith('pins.catalog_versions.')}
    unknown = pins.catalog_versions.keys() - {'archetype', 'rules', 'components', 'enclosures', 'hardware'}
    catalog_keys.update(unknown)
    if catalog_keys - pins.catalog_versions.keys():
        raise ValueError('Required exact catalog/rule pins are missing.')
    uses_policy = 'pins.validation_policy_version' in paths
    if uses_policy and policy is None:
        raise ValueError('Supply saved validation policy content for physical consumers.')
    for value in _walk(inputs):
        if isinstance(value, e.ElectricalContext) and value != context:
            raise ValueError('Input ownership/context differs.')
        if isinstance(value, e.Snapshot):
            payload = value.read()
            for field in ('project_id', 'panel_id'):
                if hasattr(payload, field) and getattr(payload, field) != getattr(context, field):
                    raise ValueError('Snapshot ownership differs from document context.')
        for cls, field, key in (
            (e.PinnedRules, 'archetype_version', 'archetype'),
            (e.PinnedRules, 'rules_version', 'rules'),
            (e.PinnedComponents, 'catalog_version', 'components'),
            (p.PinnedEnclosures, 'catalog_version', 'enclosures'),
            (p.PinnedHardware, 'catalog_version', 'hardware'),
        ):
            if isinstance(value, cls) and getattr(value, field) != pins.catalog_versions.get(key):
                raise ValueError('Supplied catalog content and version pins differ.')
        if isinstance(value, p.PhysicalSnapshot) and uses_policy and value.read().validation_policy != policy:
            raise ValueError('Saved physical policy and signature policy differ.')
    if inputs.algorithm_version != STAGE_REGISTRY.by_id[binding.stage_id].algorithm_version:
        raise ValueError('Adapter algorithm version differs from the registry.')
    if isinstance(inputs, a.CADInput) and (
            inputs.generator_version != pins.generator.version or inputs.model_versions.read() != pins.model_versions):
        raise ValueError('CAD generator/model inputs and pins differ.')
    manifest = dict(schema_version='1.0.0', registry_schema=STAGE_REGISTRY.schema_version,
        adapter=adapter, stage_id=binding.stage_id,
        context=context.model_dump(mode='json'), inputs=inputs.model_dump(mode='json'),
        input_schema=content_hash(binding.inputs.model_json_schema()),
        output_schema=content_hash(binding.outputs.model_json_schema()),
        contracts={s: STAGE_REGISTRY.by_id[s].model_dump(mode='json') for s in stages},
        engine_version=pins.engine_version,
        catalog_versions={key: pins.catalog_versions[key] for key in sorted(catalog_keys)},
        model_versions=pins.model_versions if 'pins.model_versions' in paths else {},
        generator=pins.generator.model_dump(mode='json') if 'pins.generator' in paths else None,
        policy_sha256=content_hash(policy.model_dump(mode='json')) if uses_policy else None,
        validation_policy_version=pins.validation_policy_version if uses_policy else None)
    return StageSignature(manifest_json=canonical_json(manifest).decode('utf-8'))


def _binding(signature):
    manifest = signature.manifest
    binding = ADAPTERS[manifest['adapter']]
    if (manifest['schema_version'] != '1.0.0' or manifest['stage_id'] != binding.stage_id
            or manifest['registry_schema'] != STAGE_REGISTRY.schema_version
            or manifest['input_schema'] != content_hash(binding.inputs.model_json_schema())
            or manifest['output_schema'] != content_hash(binding.outputs.model_json_schema())
            or manifest['contracts'] != {s: STAGE_REGISTRY.by_id[s].model_dump(mode='json')
                                        for s in _ancestors(binding.stage_id)}):
        raise ValueError('Incompatible stage signature.')
    binding.inputs.model_validate(manifest['inputs'])
    return binding


class StageCache:
    def __init__(self, database):
        self.db = database
        self.assets = AssetStore(database.settings.asset_root)

    def _verify(self, row, signature):
        if row is None:
            return CacheLookup('MISSING')
        try:
            binding = _binding(signature)
            if (row['input_signature'] != signature.key or row['signature'] != signature.manifest
                    or content_hash(row['signature']) != row['input_signature']
                    or row['adapter'] != signature.manifest['adapter'] or row['stage_id'] != binding.stage_id
                    or content_hash(dict(output=row['result'], assets=row['assets'])) != row['result_sha256']):
                raise ValueError('Cache envelope differs.')
            output = binding.outputs.model_validate(row['result'])
            if output.model_dump(mode='json') != row['result']:
                raise ValueError('Cache payload is not canonical.')
            for asset in row['assets']:
                asset = ManagedAsset.model_validate(asset)
                self.assets.verified_path(asset.storage_key, asset.sha256, asset.byte_size)
            return CacheLookup('VALID', row['id'], output, row['result_sha256'])
        except (ValueError, KeyError, TypeError, AttributeError, RecursionError, AssetUnavailable):
            return CacheLookup('CORRUPT', row['id'])

    def lookup(self, signature: StageSignature) -> CacheLookup:
        """Detached verified result or a miss. No execution, repair or DB writes."""
        _binding(signature)
        with self.db.sessions() as session:
            row = session.execute(select(m.stage_results).where(
                m.stage_results.c.input_signature == signature.key).order_by(
                m.stage_results.c.created_at.desc(), m.stage_results.c.id.desc()).limit(1)).mappings().first()
            row = dict(row) if row else None
        # Asset hashing and output deserialization run after the read transaction.
        return self._verify(row, signature)

    def _lock(self, session, document_id, sequence, signature, completing=False):
        context = signature.manifest['context']
        project = ProjectRepository(session).row(context['project_id'], lock=True)
        document = session.execute(select(m.design_documents).where(
            m.design_documents.c.id == document_id,
            m.design_documents.c.project_id == project['id']).with_for_update()).mappings().first()
        if document is None or document['panel_id'] != context['panel_id']:
            raise PersistenceError('STAGE_DOCUMENT_MISMATCH', 'Stage document ownership differs.', 409)
        if type(sequence) is not int or document['document_sequence'] != sequence:
            raise PersistenceError('STAGE_INPUT_CONFLICT', 'Document changed before stage completion.', 409)
        previous = session.execute(select(m.document_stage_states).where(
            m.document_stage_states.c.document_id == document_id,
            m.document_stage_states.c.adapter == signature.manifest['adapter'])).mappings().first()
        if completing and previous:
            if previous['input_signature'] != signature.key:
                raise PersistenceError('STAGE_INPUT_CONFLICT', 'Stage inputs changed before completion.', 409)
            if previous['status'] == 'BLOCKED':
                raise PersistenceError('STAGE_BLOCKED', 'Stage dependencies remain blocked.', 409)
        return previous

    def _write(self, session, document_id, sequence, signature, previous, **changes):
        manifest = signature.manifest
        values = dict(document_id=document_id, adapter=manifest['adapter'], stage_id=manifest['stage_id'],
            document_sequence=sequence, input_signature=signature.key,
            input_version=(previous['input_version'] + (previous['input_signature'] != signature.key)
                           if previous else 1),
            output_version=previous['output_version'] if previous else 0,
            output_signature=previous['output_signature'] if previous else None,
            result_id=previous['result_id'] if previous else None,
            blocked_by=[], failure_code=None,
            updated_at=datetime.now(timezone.utc))
        values.update(changes)
        # Output counters describe accepted content, independently of input clocks.
        if 'accepted' in values:
            accepted = values.pop('accepted')
            old_hash = session.scalar(select(m.stage_results.c.result_sha256).where(
                m.stage_results.c.id == values['result_id'])) if values['result_id'] else None
            values.update(result_id=accepted.result_id, output_signature=signature.key,
                output_version=values['output_version'] + (old_hash != accepted.result_sha256))
        table = m.document_stage_states
        if previous:
            session.execute(update(table).where(table.c.document_id == document_id,
                table.c.adapter == manifest['adapter']).values(**values))
        else:
            session.execute(insert(table).values(**values))
        return StageState.model_validate({key: (str(value) if key == 'result_id' and value else value)
            for key, value in values.items() if key != 'updated_at'})

    def observe(self, document_id: str, sequence: int, signature: StageSignature,
                blocked_by: tuple[str, ...] = ()) -> StageState:
        """Refresh stale/integrity metadata, retaining prior outputs and failures.

        Blockers come from the caller's explicit dependency plan. This method
        neither schedules prerequisites nor adopts a cache hit as document output.
        """
        blocked_by = tuple(dict.fromkeys(blocked_by))
        if any(value not in ADAPTERS for value in blocked_by):
            raise ValueError('Unknown blocked adapter.')
        hit = self.lookup(signature)
        with self.db.sessions.begin() as session:
            previous = self._lock(session, document_id, sequence, signature)
            status, failure_code = 'DIRTY', None
            integrity = hit.integrity
            accepted = None
            if blocked_by:
                status = 'BLOCKED'
            elif previous and previous['input_signature'] == signature.key:
                if previous['status'] == 'FAILED':
                    status, failure_code = 'FAILED', previous['failure_code']
            if (not blocked_by and status != 'FAILED' and previous
                    and previous['output_signature'] == signature.key and previous['result_id']):
                row = session.execute(select(m.stage_results).where(
                    m.stage_results.c.id == previous['result_id'])).mappings().first()
                # Verify the accepted entry itself, never substitute a newer
                # cache entry behind an already accepted output reference.
                accepted = dict(row) if row else None
            # Attached output verification below is done outside transactions.
            previous = dict(previous) if previous else None
        if not blocked_by and status != 'FAILED' and previous and previous['output_signature'] == signature.key:
            attached = self._verify(accepted, signature)
            integrity = attached.integrity
            status = 'VALID' if integrity == 'VALID' else 'DIRTY'
        with self.db.sessions.begin() as session:
            current = self._lock(session, document_id, sequence, signature)
            if (dict(current) if current else None) != previous:
                raise PersistenceError('STAGE_INPUT_CONFLICT', 'Stage state changed during inspection.', 409)
            return self._write(session, document_id, sequence, signature, current,
                status=status, integrity=integrity, blocked_by=list(blocked_by), failure_code=failure_code)

    def record_failure(self, document_id: str, sequence: int, signature: StageSignature,
                       failure_code: str) -> StageState:
        """Persist a caller's explicit execution failure, without caching an output."""
        _binding(signature)
        # No exception text, SQL parameters or local paths are persisted here.
        if not failure_code or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in failure_code):
            raise ValueError('Use a structured failure code.')
        integrity = self.lookup(signature).integrity
        with self.db.sessions.begin() as session:
            previous = self._lock(session, document_id, sequence, signature, completing=True)
            return self._write(session, document_id, sequence, signature, previous,
                status='FAILED', integrity=integrity, failure_code=failure_code)

    def accept_cached(self, document_id: str, sequence: int, signature: StageSignature) -> StageState:
        """Explicitly adopt a verified hit; never execute or repair a miss."""
        hit = self.lookup(signature)
        if hit.integrity != 'VALID':
            raise PersistenceError('STAGE_CACHE_INTEGRITY', 'Stage cache is missing, corrupt or incompatible.', 409)
        with self.db.sessions.begin() as session:
            previous = self._lock(session, document_id, sequence, signature, completing=True)
            return self._write(session, document_id, sequence, signature, previous,
                status='VALID', integrity='VALID', accepted=hit)

    def record_success(self, document_id: str, sequence: int, signature: StageSignature,
                       output: FrozenContract, assets: tuple[ManagedAsset, ...] = ()) -> StageState:
        """Append an explicitly computed result, then accept only its cache metadata.

        The caller runs ``ADAPTERS[name].execute(inputs)`` outside any transaction.
        Register changed desired inputs with ``observe`` before starting work.
        No mutable cache row is repaired and no engineering snapshot is installed.
        """
        binding = _binding(signature)
        if type(output) is not binding.outputs:
            raise ValueError('Output type differs from the registered adapter.')
        payload = binding.outputs.model_validate_json(output.model_dump_json()).model_dump(mode='json')
        asset_rows = [ManagedAsset.model_validate(asset).model_dump(mode='json') for asset in assets]
        for asset in asset_rows:
            self.assets.verified_path(asset['storage_key'], asset['sha256'], asset['byte_size'])
        digest = content_hash(dict(output=payload, assets=asset_rows))
        result_id = uuid4()
        hit = CacheLookup('VALID', result_id, output, digest)
        with self.db.sessions.begin() as session:
            previous = self._lock(session, document_id, sequence, signature, completing=True)
            session.execute(insert(m.stage_results).values(id=result_id,
                stage_id=binding.stage_id, adapter=signature.manifest['adapter'],
                input_signature=signature.key, signature=signature.manifest, result=payload,
                assets=asset_rows, result_sha256=digest))
            return self._write(session, document_id, sequence, signature, previous,
                status='VALID', integrity='VALID', accepted=hit)
