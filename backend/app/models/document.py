"""Version 1 working-document contracts; storage/operations are separate tasks.

A reference-only WorkingDocument is metadata, not proof of snapshot integrity.
Resolve all references into ResolvedDocument before accepting engineering content.
Snapshot digests cover canonical JSON of the fully defaulted model_dump(mode='json').
Reference schema 1 is the snapshot envelope version; CEM.revision is not a clock.
"""
import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.models.cem import CanonicalEngineeringModel
from app.models.identity import ContractModel, StableID, require_reference, unique_ids
from app.models.pdm import PhysicalDesignModel
from app.models.requirements import RequirementSet
from app.models.schematic import SchematicPresentation

SHA256 = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
DirtyStage = Literal['requirements', 'calculations', 'selection', 'connectivity',
                     'schematic', 'placement', 'routes', 'physical_validation', 'bom', 'cad']


def snapshot_sha256(snapshot) -> str:
    payload = snapshot.model_dump(mode='json')
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


class SnapshotReference(ContractModel):
    schema_version: Literal[1] = 1
    sha256: SHA256

    @field_validator('schema_version', mode='before')
    @classmethod
    def integer_schema(cls, value):
        if type(value) is not int:
            raise PydanticCustomError('unsupported_schema_version', 'Snapshot schema version must be integer 1')
        return value


class DocumentReferences(ContractModel):
    requirements: SnapshotReference
    cem: SnapshotReference | None = None
    pdm: SnapshotReference | None = None
    schematic: SnapshotReference | None = None


class GeneratorPin(ContractModel):
    name: StableID
    version: StableID


class PinnedVersions(ContractModel):
    engine_version: StableID
    generator: GeneratorPin
    catalog_manifest_sha256: SHA256
    validation_policy_version: StableID
    # Exact immutable catalog/model version IDs, never a "latest" lookup.
    catalog_versions: dict[StableID, StableID] = Field(default_factory=dict)
    model_versions: dict[StableID, StableID] = Field(default_factory=dict)


class DocumentProvenance(ContractModel):
    origin: Literal['MANUAL', 'AUTOMATIC', 'IMPORT', 'RESTORE', 'COMPATIBILITY', 'AI_PROPOSAL']
    actor_id: StableID
    last_operation_id: StableID | None = None
    source_revision_id: StableID | None = None
    proposal_id: StableID | None = None
    job_id: StableID | None = None


class EnclosureInterface(ContractModel):
    """Explicit electrical endpoint registry, including any PANEL_ROOT interface."""
    component_id: StableID
    terminal_ids: list[StableID]

    @model_validator(mode='after')
    def terminals_unique(self):
        unique_ids(self.terminal_ids, f'interfaces.{self.component_id}.terminal_ids')
        return self


class GenerationIntent(ContractModel):
    """Retained user intent; ordinary Save cannot clear operation-owned locks."""
    manual_models: list[Literal['cem', 'pdm', 'schematic']] = Field(default_factory=list)
    locked_placements: list[StableID] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique_intents(self):
        unique_ids(self.manual_models, 'generation_intent.manual_models')
        unique_ids(self.locked_placements, 'generation_intent.locked_placements')
        return self


class WorkingDocument(ContractModel):
    schema_version: Literal['1.0.0'] = '1.0.0'
    document_id: StableID
    project_id: StableID
    panel_id: StableID
    archetype: Literal['DB'] = 'DB'
    document_sequence: int = Field(default=0, ge=0, strict=True)
    lock_version: int = Field(ge=1, strict=True)
    base_revision_id: StableID | None = None
    models: DocumentReferences
    configuration: dict[str, Any] = Field(default_factory=dict)
    pins: PinnedVersions
    provenance: DocumentProvenance
    dirty_stages: list[DirtyStage] = Field(default_factory=list)
    enclosure_interfaces: list[EnclosureInterface] = Field(default_factory=list)
    generation_intent: GenerationIntent | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode='after')
    def namespaces_unique(self):
        unique_ids(self.dirty_stages, 'dirty_stages')
        unique_ids((item.component_id for item in self.enclosure_interfaces), 'enclosure_interfaces')
        return self


class DocumentSnapshots(ContractModel):
    requirements: RequirementSet
    cem: CanonicalEngineeringModel | None = None
    pdm: PhysicalDesignModel | None = None
    schematic: SchematicPresentation | None = None


class ResolvedDocument(ContractModel):
    document: WorkingDocument
    snapshots: DocumentSnapshots

    @model_validator(mode='after')
    def resolve(self):
        doc, snapshots = self.document, self.snapshots
        for kind in ('requirements', 'cem', 'pdm', 'schematic'):
            reference, snapshot = getattr(doc.models, kind), getattr(snapshots, kind)
            if (reference is None) != (snapshot is None):
                raise PydanticCustomError('snapshot_missing', 'Reference and snapshot presence differ: {kind}', {'kind': kind})
            if snapshot is None:
                continue
            if snapshot.project_id != doc.project_id or (
                kind != 'requirements' and snapshot.panel_id != doc.panel_id
            ):
                raise PydanticCustomError('identity_mismatch', 'Snapshot ownership differs: {kind}', {'kind': kind})
            if reference.sha256 != snapshot_sha256(snapshot):
                raise PydanticCustomError('snapshot_hash_mismatch', 'Snapshot digest differs: {kind}', {'kind': kind})
        if snapshots.requirements.archetype != doc.archetype:
            raise PydanticCustomError('identity_mismatch', 'Requirement archetype differs')
        unique_ids((item.id for item in snapshots.requirements.items), 'requirements.items')
        if snapshots.cem is None:
            if snapshots.pdm is not None or snapshots.schematic is not None:
                raise PydanticCustomError('unknown_reference', 'PDM/schematic require a CEM snapshot')
            return self
        validate_engineering_references(doc, snapshots)
        return self


def validate_engineering_references(doc: WorkingDocument, snapshots: DocumentSnapshots) -> None:
    """Shared boundary for documents/imports/operations; no geometry regeneration."""
    cem, pdm, schematic = snapshots.cem, snapshots.pdm, snapshots.schematic
    assert cem is not None
    if cem.panel_type != doc.archetype:
        raise PydanticCustomError('identity_mismatch', 'CEM archetype differs')
    for name in ('requirements', 'modules', 'loads', 'components', 'connections', 'nets', 'calculations', 'constraints'):
        unique_ids((item.id for item in getattr(cem, name)), f'cem.{name}')
    components = {item.id: item for item in cem.components}
    terminals = {item.id: unique_ids((t.get('id') for t in item.terminals), f'cem.{item.id}.terminals')
                 for item in cem.components}
    for interface in doc.enclosure_interfaces:
        if interface.component_id in terminals:
            raise PydanticCustomError('duplicate_id', 'Interface shadows CEM component: {reference}', {'reference': interface.component_id})
        terminals[interface.component_id] = set(interface.terminal_ids)
    nets = {item.id: item for item in cem.nets}
    connections = {item.id: item for item in cem.connections}
    for module in cem.modules:
        if module.assigned_component_id is not None:
            require_reference(module.assigned_component_id, components, f'modules.{module.id}.assigned_component_id')
    for connection in cem.connections:
        require_reference(connection.net_id, nets, f'connections.{connection.id}.net_id')
        for side in ('from', 'to'):
            component = getattr(connection, f'{side}_component')
            terminal = getattr(connection, f'{side}_terminal')
            require_reference(component, terminals, f'connections.{connection.id}.{side}_component')
            require_reference(terminal, terminals[component], f'connections.{connection.id}.{side}_terminal')
    membership = []
    for net in cem.nets:
        for member in net.connections:
            require_reference(member.id, connections, f'nets.{net.id}.connections')
            if member != connections[member.id] or member.net_id != net.id:
                raise PydanticCustomError('reference_mismatch', 'Net membership differs from canonical connection: {reference}', {'reference': member.id})
            membership.append(member.id)
    unique_ids(membership, 'cem.net_membership')
    if set(membership) != set(connections):
        raise PydanticCustomError('reference_mismatch', 'Each connection must belong to exactly one net')
    if cem.electrical_graph is not None:
        graph = cem.electrical_graph
        if graph.project_id != doc.project_id:
            raise PydanticCustomError('identity_mismatch', 'Electrical graph project differs')
        nodes = unique_ids((node.id for node in graph.nodes), 'cem.electrical_graph.nodes')
        for edge in graph.edges:
            require_reference(edge.source, nodes, 'electrical_graph.edge.source')
            require_reference(edge.target, nodes, 'electrical_graph.edge.target')
    if pdm is not None:
        if pdm.validation_policy.version != doc.pins.validation_policy_version:
            raise PydanticCustomError('version_pin_mismatch', 'PDM validation policy differs from document pin')
        validate_physical_references(cem, pdm, components, connections)
    elif cem.physical_design_id is not None:
        raise PydanticCustomError('unknown_reference', 'CEM physical_design_id has no PDM snapshot')
    if schematic is not None:
        for symbol in schematic.symbols:
            require_reference(symbol.component_id, terminals, f'symbols.{symbol.id}.component_id')
            for pin in symbol.pins:
                require_reference(pin.terminal_id, terminals[symbol.component_id], f'pins.{pin.id}.terminal_id')
        pins = {pin.id: (symbol.component_id, pin.terminal_id) for symbol in schematic.symbols for pin in symbol.pins}
        for wire in schematic.wires:
            require_reference(wire.conductor_id, connections, f'wires.{wire.id}.conductor_id')
            connection = connections[wire.conductor_id]
            if (pins[wire.source_pin_id], pins[wire.target_pin_id]) != (
                (connection.from_component, connection.from_terminal), (connection.to_component, connection.to_terminal)
            ):
                raise PydanticCustomError('reference_mismatch', 'Schematic wire endpoints differ: {reference}', {'reference': wire.id})
        for junction in schematic.junctions:
            members = [connections[w.conductor_id] for w in schematic.wires
                       if junction.pin_id in (w.source_pin_id, w.target_pin_id)]
            if len(members) < 2 or len({c.net_id for c in members}) != 1:
                raise PydanticCustomError('reference_mismatch', 'Junction must present an existing shared CEM terminal in one net')


def validate_physical_references(cem, pdm, components, connections) -> None:
    unique_ids([pdm.id], 'pdm.id')
    if cem.physical_design_id is not None and cem.physical_design_id != pdm.id:
        raise PydanticCustomError('reference_mismatch', 'CEM physical_design_id differs from PDM ID')
    for name in ('components', 'rails', 'ducts', 'accessories', 'busbars', 'routes'):
        unique_ids((item.id for item in getattr(pdm, name)), f'pdm.{name}')
    unique_ids((zone.name for zone in pdm.zones), 'pdm.zones')
    physical = {item.id for item in pdm.components}
    rails = {item.id for item in pdm.rails}
    ducts = {item.id for item in pdm.ducts}
    routes = {item.id for item in pdm.routes}
    parents = physical | rails | ducts | {item.id for item in pdm.accessories} | {'ENCLOSURE'}
    for accessory in pdm.accessories:
        require_reference(accessory.parent_id, parents, f'pdm.{accessory.id}.parent_id')
    for component in pdm.components:
        require_reference(component.cem_component_id, components, f'pdm.{component.id}.cem_component_id')
        if component.rail_id is not None:
            require_reference(component.rail_id, rails, f'pdm.{component.id}.rail_id')
        require_reference(component.zone_name, {zone.name for zone in pdm.zones}, f'pdm.{component.id}.zone_name')
        unique_ids((terminal.get('id') for terminal in component.terminals), f'pdm.{component.id}.terminals')
        for terminal in component.terminals:
            require_reference(terminal.get('id'), {t.get('id') for t in components[component.cem_component_id].terminals}, f'pdm.{component.id}.terminals')
    unique_ids((component.cem_component_id for component in pdm.components), 'pdm.cem_component_ids')
    for clearance in pdm.clearances:
        require_reference(clearance.component_id, physical, 'pdm.clearances.component_id')
    for duct in pdm.ducts:
        unique_ids(duct.route_ids, f'pdm.ducts.{duct.id}.route_ids')
        for route_id in duct.route_ids:
            require_reference(route_id, routes, f'pdm.ducts.{duct.id}.route_ids')
    for route in pdm.routes:
        require_reference(route.conductor_id, connections, f'routes.{route.id}.conductor_id')
        connection = connections[route.conductor_id]
        for field in ('net_id', 'from_component', 'from_terminal', 'to_component', 'to_terminal', 'wire_class'):
            if getattr(route, field) != getattr(connection, field):
                raise PydanticCustomError('reference_mismatch', 'Route differs from conductor at {path}', {'path': f'routes.{route.id}.{field}'})
        for duct_id in route.duct_ids:
            require_reference(duct_id, ducts, f'routes.{route.id}.duct_ids')
        if route.geometry is not None:
            if route.geometry.route_id != route.id:
                raise PydanticCustomError('reference_mismatch', 'Wire geometry references a different route')
    unique_ids((route.geometry.id for route in pdm.routes if route.geometry is not None), 'pdm.wire_geometry')
