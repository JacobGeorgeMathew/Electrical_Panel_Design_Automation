"""Validated DB stage DAG and pure invalidation planning, without execution or I/O.

Paths are relative to resolved document snapshots/metadata. A '*' segment names
every member of a collection; parent changes overlap all consumed descendants.
Prerequisites order execution. Invalidation follows dependants only: a valid
prerequisite is reusable, never implicitly scheduled by a downstream edit.
"""
from types import MappingProxyType
from typing import Annotated, Any, Iterable, Literal, Union, get_args, get_origin
from types import UnionType

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.document import DirtyStage, DocumentSnapshots, WorkingDocument
from app.models.identity import ContractModel, StableID, unique_ids


FieldPath = Annotated[str, Field(pattern=(
    r'^(requirements|cem|pdm|schematic|configuration|pins|generation_intent|'
    r'enclosure_interfaces|display|results|algorithms)(\.(\*|[A-Za-z0-9_:-]+))*$'))]


class FrozenContract(ContractModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, frozen=True)


class StageInput(FrozenContract):
    name: StableID
    paths: tuple[FieldPath, ...] = Field(min_length=1)
    # None denotes authoritative document/catalog input, not a computed result.
    source_stage: DirtyStage | None = None
    source_output: StableID | None = None

    @model_validator(mode='after')
    def paired_source(self):
        if (self.source_stage is None) != (self.source_output is None):
            raise ValueError('Stage input source_stage and source_output must be paired.')
        unique_ids(self.paths, 'input.paths')
        return self


class StageOutput(FrozenContract):
    name: StableID
    paths: tuple[FieldPath, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_paths(self):
        unique_ids(self.paths, 'output.paths')
        return self


class StageContract(FrozenContract):
    id: DirtyStage
    algorithm_version: StableID
    inputs: tuple[StageInput, ...] = Field(min_length=1)
    outputs: tuple[StageOutput, ...] = Field(min_length=1)
    prerequisites: tuple[DirtyStage, ...] = ()
    validation_obligations: tuple[StableID, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_members(self):
        unique_ids((item.name for item in self.inputs), 'stage.inputs')
        unique_ids((item.name for item in self.outputs), 'stage.outputs')
        unique_ids(self.prerequisites, 'stage.prerequisites')
        unique_ids(self.validation_obligations, 'stage.validation_obligations')
        return self


class InvalidationPlan(FrozenContract):
    stages: tuple[DirtyStage, ...]
    direct_stages: tuple[DirtyStage, ...]
    validation_obligations: tuple[StableID, ...]
    conservative_roots: tuple[str, ...] = ()


def paths_overlap(left: str, right: str) -> bool:
    """Whole-subtree consumption and whole-parent edits are both conservative."""
    return all(a == b or a == '*' or b == '*'
               for a, b in zip(left.split('.'), right.split('.')))


def known_document_path(path: str) -> bool:
    """Do not let a consumed subtree mask an unknown typed model field.

    Collection members are logical IDs, indexes or '*'. Dictionary keys and Any
    payloads are intentionally open; their contents belong to the declared input.
    """
    root, *parts = path.split('.')
    fields = (DocumentSnapshots.model_fields if root in DocumentSnapshots.model_fields
              else WorkingDocument.model_fields)
    if root not in fields:
        return root in {'results', 'algorithms', 'display'}

    def walk(schema, segments):
        if not segments or schema is Any:
            return True
        origin, args = get_origin(schema), get_args(schema)
        if origin is Annotated:
            return walk(args[0], segments)
        if origin in (Union, UnionType):
            return any(walk(arg, segments) for arg in args if arg is not type(None))
        if origin in (list, tuple):
            return walk(args[0], segments[1:])
        if origin is dict:
            return walk(args[1], segments[1:])
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            field = schema.model_fields.get(segments[0])
            return field is not None and walk(field.annotation, segments[1:])
        return False

    return walk(fields[root].annotation, parts)


# These paths belong to transient view state, never engineering or saved symbol
# coordinates. Unknown display fields do not receive this exemption.
DISPLAY_PATHS = ('display.camera', 'display.selection', 'display.visibility',
                 'display.grid', 'display.snap', 'display.explode', 'display.panels', 'display.tool')


class StageRegistry(FrozenContract):
    schema_version: Literal['1.0.0'] = '1.0.0'
    stages: tuple[StageContract, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def validate_graph(self):
        unique_ids((stage.id for stage in self.stages), 'registry.stages')
        by_id = self.by_id
        for stage in self.stages:
            for item in (*stage.inputs, *stage.outputs):
                if any(not known_document_path(path) for path in item.paths):
                    raise ValueError(f'Undefined document field path: {stage.id}.{item.name}')
            for prerequisite in stage.prerequisites:
                if prerequisite not in by_id:
                    raise ValueError(f'Undefined stage reference: {stage.id} -> {prerequisite}')
            for item in stage.inputs:
                if item.source_stage is None:
                    continue
                if item.source_stage not in stage.prerequisites:
                    raise ValueError(f'Input producer must be a prerequisite: {stage.id}.{item.name}')
                producer = by_id[item.source_stage]
                output = next((output for output in producer.outputs if output.name == item.source_output), None)
                if output is None:
                    raise ValueError(f'Undefined stage output: {item.source_stage}.{item.source_output}')
                if any(not any(paths_overlap(path, produced) for produced in output.paths) for path in item.paths):
                    raise ValueError(f'Input paths do not belong to producer output: {stage.id}.{item.name}')
        self.ordered_ids()  # Also rejects self-cycles and disconnected cycles.
        return self

    @property
    def by_id(self):
        return MappingProxyType({stage.id: stage for stage in self.stages})

    def ordered_ids(self) -> tuple[DirtyStage, ...]:
        ordered, visiting, visited = [], set(), set()
        by_id = self.by_id

        def visit(stage_id):
            if stage_id in visiting:
                raise ValueError(f'Stage dependency cycle at {stage_id}')
            if stage_id in visited:
                return
            visiting.add(stage_id)
            for prerequisite in by_id[stage_id].prerequisites:
                visit(prerequisite)
            visiting.remove(stage_id)
            visited.add(stage_id)
            ordered.append(stage_id)

        for stage in self.stages:
            visit(stage.id)
        return tuple(ordered)

    def downstream(self, stage_ids: Iterable[str]) -> tuple[DirtyStage, ...]:
        if isinstance(stage_ids, str):
            raise TypeError('Pass a collection of stage IDs, not a single string.')
        dirty = set(stage_ids)
        if dirty - self.by_id.keys():
            raise ValueError(f'Undefined stage references: {sorted(dirty - self.by_id.keys())}')
        # Topological traversal reaches every transitive dependant in one pass.
        for stage_id in self.ordered_ids():
            if dirty.intersection(self.by_id[stage_id].prerequisites):
                dirty.add(stage_id)
        return tuple(stage_id for stage_id in self.ordered_ids() if stage_id in dirty)

    def invalidate(self, changed_paths: Iterable[str]) -> InvalidationPlan:
        if isinstance(changed_paths, str):
            raise TypeError('Pass a collection of changed paths, not a single string.')
        direct, conservative = set(), set()
        for path in changed_paths:
            # A parent 'display' replacement may include unknown fields.
            if any(path == allowed or path.startswith(allowed + '.') for allowed in DISPLAY_PATHS):
                continue
            consumers = {stage.id for stage in self.stages for item in stage.inputs
                         if any(paths_overlap(path, consumed) for consumed in item.paths)}
            # A whole-model reader (e.g. CAD reading schematic) must not hide an
            # unknown model field and bypass that model's own producer closure.
            declared = any(paths_overlap(path, consumed) for stage in self.stages
                for item in stage.inputs for consumed in item.paths if '.' in consumed)
            if consumers and declared and known_document_path(path):
                direct.update(consumers)
                continue
            root = path.split('.')[0]
            conservative.add(root)
            # Unknown model fields invalidate that model's producers AND consumers.
            # Unknown metadata, pin names or namespaces invalidate the whole DAG.
            if root in {'requirements', 'cem', 'pdm', 'schematic'}:
                direct.update(stage.id for stage in self.stages
                    if any(p.split('.')[0] == root for item in (*stage.inputs, *stage.outputs)
                           for p in item.paths))
            else:
                direct.update(self.by_id)
        stages = self.downstream(direct)
        obligations = tuple(dict.fromkeys(code for stage_id in stages
            for code in self.by_id[stage_id].validation_obligations))
        return InvalidationPlan(stages=stages,
            direct_stages=tuple(stage_id for stage_id in self.ordered_ids() if stage_id in direct),
            validation_obligations=obligations, conservative_roots=tuple(sorted(conservative)))


def source(name, *paths):
    return StageInput(name=name, paths=paths)


def result(stage, output, *paths):
    return StageInput(name=output, paths=paths, source_stage=stage, source_output=output)


def stage(stage_id, inputs, outputs, prerequisites=(), obligations=('stable_identity',)):
    return StageContract(id=stage_id, algorithm_version=f'db-{stage_id}-1',
        inputs=(*inputs, source('algorithm', f'algorithms.{stage_id}'),
                source('engine', 'pins.engine_version')),
        outputs=tuple(StageOutput(name=name, paths=paths) for name, paths in outputs),
        prerequisites=prerequisites, validation_obligations=obligations)


ENCLOSURE_PATHS = ('pdm.enclosure_id', 'pdm.enclosure_width', 'pdm.enclosure_height',
    'pdm.enclosure_depth', 'pdm.ip_rating', 'pdm.mounting_plate_x', 'pdm.mounting_plate_y',
    'pdm.mounting_plate_z', 'pdm.mounting_plate_width', 'pdm.mounting_plate_height')


# Coarse boundaries deliberately retain the v1 DirtyStage/TypeScript vocabulary.
# connectivity = graph + netlist; placement = enclosure + zones + placement +
# cabinet assembly; routes = DuctRouter + exact wire geometry. These are contracts
# for existing algorithms, not yet adapters or a scheduler.
STAGE_REGISTRY = StageRegistry(stages=(
    stage('requirements', (
        source('answers', 'requirements.items', 'requirements.archetype'),
        source('rules', 'pins.catalog_versions.archetype', 'pins.catalog_versions.rules'),
    ), (('validated_requirements', ('results.requirements',)),),
        obligations=('requirement_rules', 'finite_units')),
    stage('calculations', (
        result('requirements', 'validated_requirements', 'results.requirements'),
        source('answers', *(f'requirements.items.{field}.value' for field in
            ('supply_voltage', 'phases', 'incomer_rating', 'num_feeders', 'spare_capacity_pct'))),
        source('manual_ratings', 'cem.components.*.current_rating'),
    ), (('calculations', ('cem.calculations',)),), ('requirements',),
        ('finite_units', 'prototype_calculation_assumptions')),
    stage('selection', (
        result('calculations', 'calculations', 'cem.calculations'),
        source('answers', 'requirements.items'),
        source('catalog', 'pins.catalog_versions.components', 'cem.components.*.component_version_id',
               'cem.components.*.product_version_id'),
    ), (('components', ('cem.components', 'cem.modules')),), ('calculations',),
        ('published_catalog_versions', 'stable_identity', 'requirement_rules')),
    stage('connectivity', (
        result('selection', 'components', 'cem.components'),
        source('electrical_intent', 'cem.connections', 'cem.nets', 'cem.electrical_graph',
               'configuration.electrical_topology', 'enclosure_interfaces'),
        source('answers', 'requirements.items.supply_voltage.value', 'requirements.items.phases.value'),
    ), (('connectivity', ('cem.electrical_graph', 'cem.nets', 'cem.connections')),), ('selection',),
        ('terminal_references', 'netlist_integrity', 'electrical_consistency', 'requirement_rules')),
    stage('schematic', (
        result('connectivity', 'connectivity', 'cem.connections', 'cem.nets'),
        source('symbols', 'cem.components', 'schematic.symbols', 'schematic.wires',
               'schematic.junctions', 'schematic.width_mm', 'schematic.height_mm'),
        source('manual_intent', 'generation_intent.manual_models'),
    ), (('schematic', ('schematic',)),), ('connectivity',),
        ('schematic_references', 'preserve_manual_presentation')),
    stage('placement', (
        result('selection', 'components', 'cem.components'),
        result('connectivity', 'connectivity', 'cem.connections'),
        source('enclosure', *ENCLOSURE_PATHS, 'configuration.enclosure_id',
               'configuration.enclosure_parameters', 'pins.catalog_versions.enclosures'),
        source('assembly', 'pins.catalog_versions.hardware', 'requirements.items.ip_rating.value'),
        source('locks_and_policy', 'generation_intent.locked_placements', 'pdm.validation_policy',
               'pins.validation_policy_version'),
    ), (('placement', (*ENCLOSURE_PATHS, 'pdm.components', 'pdm.zones', 'pdm.rails', 'pdm.ducts',
                       'pdm.accessories', 'pdm.construction', 'pdm.total_heat_loss_watts',
                       'pdm.validation_policy')),), ('selection', 'connectivity'),
        ('physical_constraints', 'preserve_locked_placements', 'enclosure_mm')),
    stage('routes', (
        result('placement', 'placement', *ENCLOSURE_PATHS, 'pdm.components', 'pdm.rails', 'pdm.ducts', 'pdm.zones'),
        result('connectivity', 'connectivity', 'cem.connections', 'cem.nets'),
        source('policy', 'pdm.validation_policy', 'pins.validation_policy_version'),
    ), (('routes', ('pdm.routes',)),), ('placement', 'connectivity'),
        ('physical_constraints', 'routing', 'connected_duct_network', 'terminal_endpoints', 'finite_wire_geometry')),
    stage('physical_validation', (
        result('placement', 'placement', *ENCLOSURE_PATHS, 'pdm.components', 'pdm.rails',
               'pdm.ducts', 'pdm.accessories', 'pdm.total_heat_loss_watts'),
        result('routes', 'routes', 'pdm.routes'),
        source('electrical', 'cem.components', 'cem.connections', 'cem.nets'),
        source('policy', 'pdm.validation_policy', 'pins.validation_policy_version'),
    ), (('validation', ('pdm.validation_results', 'pdm.thermal_density_index')),), ('placement', 'routes'),
        ('physical_validation', 'empty_physical_violations_including_warnings')),
    stage('bom', (
        result('selection', 'components', 'cem.components'),
        result('placement', 'placement', 'pdm.accessories', 'pdm.rails', 'pdm.ducts'),
    ), (('bom', ('results.bom',)),), ('selection', 'placement'),
        ('stable_identity', 'catalog_quantities_and_cut_lengths')),
    stage('cad', (
        result('physical_validation', 'validation', 'pdm.validation_results'),
        result('schematic', 'schematic', 'schematic'),
        source('physical_geometry', *ENCLOSURE_PATHS, 'pdm.panel_id', 'pdm.components', 'pdm.routes', 'pdm.rails', 'pdm.ducts',
               'pdm.accessories', 'pdm.construction'),
        source('generator', 'pins.generator', 'pins.model_versions', 'cem.components.*.cad_model_version_id'),
    ), (('cad', ('results.cad',)),), ('physical_validation', 'schematic'),
        ('empty_physical_violations_including_warnings', 'stable_identity', 'managed_asset_hashes')),
))
