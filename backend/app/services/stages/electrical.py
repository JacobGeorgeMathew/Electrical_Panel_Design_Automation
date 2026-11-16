"""Pure adapters for the existing prototype DB electrical algorithms.

All I/O belongs to the caller. Resolve exact published catalog/rule versions and
document role bindings before constructing inputs. JSON snapshots make legacy
mutable models deeply immutable at this boundary; read() returns a fresh copy.
These adapters neither publish revisions nor decide which manual slices to replace.
"""
import json
from typing import Any, Generic, Literal, TypeVar

from pydantic import TypeAdapter, field_validator, model_validator

from app.models.cem import (
    CalculationResult, CanonicalEngineeringModel, CEMState, ComponentRef,
    ConnectionRef, FunctionalModule, NetRef,
)
from app.models.electrical_graph import ElectricalGraphModel
from app.models.identity import StableID, finite_tree, unique_ids
from app.models.requirements import RequirementSet
from app.services.calculation_engine import CalculationEngine
from app.services.component_selector import ComponentSelector
from app.services.design_errors import DesignError
from app.services.graph_engine import GraphEngine
from app.services.netlist_engine import NetlistEngine
from app.services.requirement_engine import RequirementEngine
from app.services.schematic_engine import SchematicEngine
from app.services.stages.contracts import FrozenContract

T = TypeVar('T')


class Snapshot(FrozenContract, Generic[T]):
    """Typed canonical JSON, rather than shallow-frozen lists/dicts/models."""
    data_json: str

    @classmethod
    def _adapter(cls):
        return TypeAdapter(cls.__pydantic_generic_metadata__['args'][0])

    @field_validator('data_json')
    @classmethod
    def canonical_payload(cls, value):
        parsed = cls._adapter().validate_python(json.loads(value))
        finite_tree(parsed)
        return json.dumps(cls._adapter().dump_python(parsed, mode='json'),
                          sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                          allow_nan=False)

    @classmethod
    def capture(cls, value):
        parsed = cls._adapter().validate_python(value)
        finite_tree(parsed)
        return cls(data_json=json.dumps(cls._adapter().dump_python(parsed, mode='json'),
                                       allow_nan=False))

    def read(self) -> T:
        return self._adapter().validate_json(self.data_json)


class IdentityBinding(FrozenContract):
    namespace: Literal['component', 'module', 'calculation', 'net', 'connection']
    role: StableID
    document_id: StableID


class DocumentIdentities(FrozenContract):
    """Persisted role-to-ID bindings, independent of names, ratings and catalogs.

    Unbound roles retain legacy IDs for new documents. Callers retain bindings for
    removed roles so reintroduction reuses their identity. Terminal IDs stay local
    to their supplied component; no new terminal identifiers are allocated here.
    """
    bindings: tuple[IdentityBinding, ...] = ()

    @model_validator(mode='after')
    def unique_bindings(self):
        for namespace in ('component', 'module', 'calculation', 'net', 'connection'):
            entries = [b for b in self.bindings if b.namespace == namespace]
            unique_ids((b.role for b in entries), f'{namespace}.roles')
            unique_ids((b.document_id for b in entries), f'{namespace}.document_ids')
        # The existing netlist validator treats this enclosure endpoint specially.
        if self.resolve('component', 'PANEL_ROOT') != 'PANEL_ROOT' or any(
            b.namespace == 'component' and b.role != 'PANEL_ROOT' and
            b.document_id == 'PANEL_ROOT' for b in self.bindings
        ):
            raise ValueError('PANEL_ROOT is a reserved enclosure interface.')
        return self

    def resolve(self, namespace, role):
        return next((b.document_id for b in self.bindings
                     if b.namespace == namespace and b.role == role), role)

    def role(self, namespace, document_id):
        return next((b.role for b in self.bindings
                     if b.namespace == namespace and b.document_id == document_id), document_id)


class ElectricalContext(FrozenContract):
    project_id: StableID
    panel_id: StableID
    engine_version: StableID
    identities: DocumentIdentities = DocumentIdentities()


class PinnedRules(FrozenContract):
    archetype_version: StableID
    rules_version: StableID
    template: Snapshot[dict[str, Any]]


class PinnedComponents(FrozenContract):
    catalog_version: StableID
    # Order is significant: preserve the selector's existing first-SPD behavior.
    rows: Snapshot[list[dict[str, Any]]]

    @model_validator(mode='after')
    def unique_catalog(self):
        unique_ids((row['id'] for row in self.rows.read()), 'catalog.components')
        return self


class RequirementsInput(FrozenContract):
    context: ElectricalContext
    algorithm_version: Literal['db-requirements-1'] = 'db-requirements-1'
    archetype: Literal['DB'] = 'DB'
    answers: Snapshot[dict[str, Any]]
    rules: PinnedRules


class RequirementsOutput(FrozenContract):
    validated_requirements: Snapshot[RequirementSet]
    modules: Snapshot[list[FunctionalModule]]

    def values(self):
        req = self.validated_requirements.read()
        if not req.is_valid:
            raise DesignError('INVALID_REQUIREMENTS', 'Requirements must be corrected before design generation.',
                              {'project_id': req.project_id, 'validation_errors': req.validation_errors,
                               'validation_warnings': req.validation_warnings}, req.validation_errors)
        return {item.id: item.value for item in req.items if item.value is not None}


class CalculationsInput(FrozenContract):
    context: ElectricalContext
    algorithm_version: Literal['db-calculations-1'] = 'db-calculations-1'
    requirements: RequirementsOutput


class CalculationsOutput(FrozenContract):
    calculations: Snapshot[list[CalculationResult]]


class SelectionInput(FrozenContract):
    context: ElectricalContext
    algorithm_version: Literal['db-selection-1'] = 'db-selection-1'
    requirements: RequirementsOutput
    calculations: CalculationsOutput
    catalog: PinnedComponents
    # Explicit accepted document choices override the generated role's selection.
    # Resolve and pin these records before execution; never fetch "latest" here.
    accepted_components: Snapshot[list[ComponentRef]] | None = None


class SelectionOutput(FrozenContract):
    components: Snapshot[list[ComponentRef]]
    modules: Snapshot[list[FunctionalModule]]


class ConnectivityOutput(FrozenContract):
    electrical_graph: Snapshot[ElectricalGraphModel]
    nets: Snapshot[list[NetRef]]
    connections: Snapshot[list[ConnectionRef]]


class ConnectivityInput(FrozenContract):
    context: ElectricalContext
    algorithm_version: Literal['db-connectivity-1'] = 'db-connectivity-1'
    requirements: RequirementsOutput
    selection: SelectionOutput
    # An accepted topology is authoritative; regeneration must not erase it.
    intent: ConnectivityOutput | None = None


class SchematicInput(FrozenContract):
    context: ElectricalContext
    algorithm_version: Literal['db-schematic-1'] = 'db-schematic-1'
    selection: SelectionOutput
    connectivity: ConnectivityOutput


class SchematicOutput(FrozenContract):
    schematic: Snapshot[dict[str, Any]]


class _SuppliedComponents:
    """Selector protocol over detached supplied rows only; no repository fallback."""
    def __init__(self, rows):
        self.rows = rows

    def get_by_id(self, component_id):
        return next((row for row in self.rows if row['id'] == component_id), None)

    def filter_candidates(self, category, min_current=0, min_breaking_capacity=0, poles=None):
        return [row for row in self.rows if row.get('category') == category
                and row.get('current_rating', 0) >= min_current
                and row.get('breaking_capacity', 0) >= min_breaking_capacity
                and (poles is None or row.get('poles') == poles)]


def _check_requirements(context, requirements):
    if requirements.validated_requirements.read().project_id != context.project_id:
        raise DesignError('STAGE_IDENTITY_MISMATCH', 'Requirement ownership differs from stage input.')
    return requirements.values()


def _stage_ids(values, namespace):
    try:
        return unique_ids(values, namespace)
    except ValueError as exc:
        raise DesignError('STAGE_IDENTITY_COLLISION', 'Stage identities must be unique.',
                          {'namespace': namespace}) from exc


def requirements_stage(inputs: RequirementsInput) -> RequirementsOutput:
    template = inputs.rules.template.read()
    if template.get('archetype') != 'DB':
        raise DesignError('UNSUPPORTED_ARCHETYPE', 'The supplied requirement template must describe DB.')
    engine = RequirementEngine(templates={'DB': template})
    req = engine.validate_requirements(inputs.context.project_id, 'DB', inputs.answers.read())
    # Match the full generator's error and default/visibility behavior exactly.
    output = RequirementsOutput(validated_requirements=Snapshot[RequirementSet].capture(req),
                                modules=Snapshot[list[FunctionalModule]].capture([]))
    values = output.values()
    modules = [FunctionalModule(
        id=inputs.context.identities.resolve('module', f"MOD-{m['name']}"),
        name=m['name'], category=m['category'],
        required=(m.get('required', True) and (m['category'] != 'NEUTRAL_BAR' or
                  values.get('neutral_required', values['phases'] == 3))),
    ) for m in template.get('modules', [])]
    _stage_ids((m.id for m in modules), 'modules')
    return RequirementsOutput(validated_requirements=output.validated_requirements,
                              modules=Snapshot[list[FunctionalModule]].capture(modules))


def calculations_stage(inputs: CalculationsInput) -> CalculationsOutput:
    values = _check_requirements(inputs.context, inputs.requirements)
    calculations = CalculationEngine().calculate_db_parameters(values)
    for calculation in calculations:
        calculation.id = inputs.context.identities.resolve('calculation', calculation.id)
    _stage_ids((c.id for c in calculations), 'calculations')
    return CalculationsOutput(calculations=Snapshot[list[CalculationResult]].capture(calculations))


def selection_stage(inputs: SelectionInput) -> SelectionOutput:
    values = _check_requirements(inputs.context, inputs.requirements)
    rows = inputs.catalog.rows.read()
    busbar = next(c for c in inputs.calculations.calculations.read() if c.type == 'busbar_rating')
    components = ComponentSelector(_SuppliedComponents(rows)).select_components(
        incomer_rating=values['incomer_rating'], num_feeders=values['num_feeders'],
        phases=values['phases'], neutral_required=values.get('neutral_required', values['phases'] == 3),
        busbar_rating=busbar.value)
    by_catalog = {row['id']: row for row in rows}
    for component in components:
        component.id = inputs.context.identities.resolve('component', component.id)
        row = by_catalog[component.catalog_id]
        for field in ('component_version_id', 'product_version_id', 'cad_model_version_id'):
            setattr(component, field, row.get(field))
    _stage_ids((c.id for c in components), 'components')
    if inputs.accepted_components is not None:
        accepted = inputs.accepted_components.read()
        _stage_ids((c.id for c in accepted), 'accepted_components')
        generated_ids = {c.id for c in components}
        for component in accepted:
            if component.id not in generated_ids or component.catalog_id not in by_catalog:
                raise DesignError('STAGE_COMPONENT_MISMATCH', 'Accepted component is outside the supplied roles/catalog.')
            row = by_catalog[component.catalog_id]
            if any(getattr(component, field) != row.get(field) for field in
                   ('component_version_id', 'product_version_id', 'cad_model_version_id')):
                raise DesignError('STAGE_PIN_MISMATCH', 'Accepted component version differs from the supplied catalog.')
        overrides = {c.id: c for c in accepted}
        components = [overrides.get(c.id, c) for c in components]
    modules = inputs.requirements.modules.read()
    for module in modules:
        candidate = next((c for c in components if c.category == module.category), None)
        module.assigned_component_id = candidate.id if candidate else None
    return SelectionOutput(components=Snapshot[list[ComponentRef]].capture(components),
                           modules=Snapshot[list[FunctionalModule]].capture(modules))


def _canonical_components(selection, identities):
    components = selection.components.read()
    _stage_ids((c.id for c in components), 'components')
    for component in components:
        component.id = identities.role('component', component.id)
    _stage_ids((c.id for c in components), 'component.roles')
    return components


def _validate_connectivity(context, selection, output):
    graph, nets, connections = (output.electrical_graph.read(), output.nets.read(),
                                output.connections.read())
    components = selection.components.read()
    valid, errors = NetlistEngine().validate_netlist(nets, components)
    if graph.project_id != context.project_id:
        errors.append('Electrical graph ownership differs from stage input.')
    nodes = _stage_ids((node.id for node in graph.nodes), 'graph.nodes')
    component_ids = {c.id for c in components} | {'PANEL_ROOT'}
    if nodes != component_ids or any(e.source not in nodes or e.target not in nodes for e in graph.edges):
        errors.append('Electrical graph component references differ from stage input.')
    if connections != [c for net in nets for c in net.connections]:
        errors.append('Canonical connections differ from net membership.')
    if not valid or errors:
        raise DesignError('INVALID_NETLIST', 'The selected components do not form a complete electrical netlist.',
                          {'errors': errors}, errors)


def connectivity_stage(inputs: ConnectivityInput) -> ConnectivityOutput:
    values = _check_requirements(inputs.context, inputs.requirements)
    if inputs.intent is not None:
        _validate_connectivity(inputs.context, inputs.selection, inputs.intent)
        return inputs.intent
    ids = inputs.context.identities
    components = _canonical_components(inputs.selection, ids)
    graph = GraphEngine().build_electrical_graph(inputs.context.project_id, components)
    nets = NetlistEngine().generate_netlist(graph, components,
                                          voltage=values['supply_voltage'], phases=values['phases'])
    for node in graph.nodes:
        node.id = ids.resolve('component', node.id)
    for edge in graph.edges:
        edge.source, edge.target = ids.resolve('component', edge.source), ids.resolve('component', edge.target)
    pairs = {}
    for net in nets:
        net.id = ids.resolve('net', net.id)
        for connection in net.connections:
            connection.id = ids.resolve('connection', connection.id)
            connection.net_id = net.id
            connection.from_component = ids.resolve('component', connection.from_component)
            connection.to_component = ids.resolve('component', connection.to_component)
            pairs.setdefault((connection.from_component, connection.to_component), set()).add(net.id)
    for edge in graph.edges:
        edge.properties['net_ids'] = sorted(pairs.get((edge.source, edge.target), set()))
    output = ConnectivityOutput(electrical_graph=Snapshot[ElectricalGraphModel].capture(graph),
        nets=Snapshot[list[NetRef]].capture(nets),
        connections=Snapshot[list[ConnectionRef]].capture([c for net in nets for c in net.connections]))
    _validate_connectivity(inputs.context, inputs.selection, output)
    return output


def schematic_stage(inputs: SchematicInput) -> SchematicOutput:
    _validate_connectivity(inputs.context, inputs.selection, inputs.connectivity)
    ids = inputs.context.identities
    components = _canonical_components(inputs.selection, ids)
    nets = inputs.connectivity.nets.read()
    for net in nets:
        for connection in net.connections:
            connection.from_component = ids.role('component', connection.from_component)
            connection.to_component = ids.role('component', connection.to_component)
    cem = CanonicalEngineeringModel(project_id=inputs.context.project_id, panel_id=inputs.context.panel_id,
        state=CEMState.NETLIST_VALIDATED, components=components, nets=nets)
    schematic = SchematicEngine().generate_schematic_data(cem)
    for symbol in schematic['symbols']:
        old_id = symbol['id']
        symbol['id'] = ids.resolve('component', old_id)
        if old_id != 'PANEL_ROOT':
            symbol['label'] = symbol['id'] + symbol['label'][len(old_id):]
        for terminal in symbol['terminals']:
            terminal['port_id'] = symbol['id'] + ':' + terminal['id']
    for wire in schematic['wires']:
        wire['from'], wire['to'] = ids.resolve('component', wire['from']), ids.resolve('component', wire['to'])
        wire['source_port_id'] = wire['from'] + ':' + wire['from_terminal']
        wire['target_port_id'] = wire['to'] + ':' + wire['to_terminal']
        for junction in wire['junctions']:
            if 'port_id' in junction:
                component, terminal = junction['port_id'].rsplit(':', 1)
                junction['port_id'] = ids.resolve('component', component) + ':' + terminal
                junction['id'] = f"JUNCTION:{wire['net_id']}:{junction['port_id']}"
    return SchematicOutput(schematic=Snapshot[dict[str, Any]].capture(schematic))
