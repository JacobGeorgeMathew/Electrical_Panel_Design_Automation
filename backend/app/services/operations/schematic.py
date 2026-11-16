"""Single-page presentation commands and terminal-owned electrical edits.

Regeneration is preview-only. Topology edits require explicit document-owned
electrical_topology evidence; legacy labels/classes never establish phase roles.
"""
from uuid import uuid5

from pydantic import ValidationError

from app.models.cem import ConnectionRef
from app.models.electrical_topology import ElectricalTopologyEvidence
from app.models.schematic import SchematicJunction, SchematicPoint, SchematicSymbol, SchematicPin, SchematicWire
from app.services.electrical_consistency import ElectricalDomain, TerminalEquivalence, project_legacy_connectivity
from app.services.operations.engineering import reject
from app.services.schematic_engine import SchematicEngine


def find(items, key, op):
    value = next((item for item in items if item.id == key), None)
    if value is None:
        reject(op, 'OPERATION_TARGET', 'Schematic target must exist in this page.')
    return value


def move_symbol(candidate, op, choices):
    schematic = candidate.snapshots.schematic
    symbol = find(schematic.symbols, op.target.symbol_id, op)
    position = op.parameters.position_mm
    if (position.x < 0 or position.y < 0 or position.x + symbol.width_mm > schematic.width_mm
            or position.y + symbol.height_mm > schematic.height_mm):
        reject(op, 'OPERATION_SCHEMATIC_BOUNDS', 'Symbol must fit within the single page.')
    dx, dy = position.x - symbol.position.x, position.y - symbol.position.y
    symbol.position = position.model_copy(deep=True)
    pins = {pin.id: pin for pin in symbol.pins}
    for pin in pins.values():
        pin.position = SchematicPoint(x=pin.position.x + dx, y=pin.position.y + dy)
    for wire in schematic.wires:
        if wire.source_pin_id in pins:
            wire.waypoints[0] = pins[wire.source_pin_id].position.model_copy(deep=True)
        if wire.target_pin_id in pins:
            wire.waypoints[-1] = pins[wire.target_pin_id].position.model_copy(deep=True)
    return ['presentation']


def update_label(candidate, op, choices):
    page = candidate.snapshots.schematic
    items = {'symbol': page.symbols, 'wire': page.wires,
             'pin': [pin for symbol in page.symbols for pin in symbol.pins]}
    find(items[op.target.kind], op.target.id, op).label = op.parameters.label
    return ['presentation']


def prune_junctions(page, cem):
    """Drop markers whose conductors no longer share an actual schematic pin."""
    connections = {c.id: c for c in cem.connections}
    retained = []
    for junction in page.junctions:
        members = [connections[w.conductor_id] for w in page.wires
                   if junction.pin_id in (w.source_pin_id, w.target_pin_id)]
        if len(members) >= 2 and len({c.net_id for c in members}) == 1:
            retained.append(junction)
    page.junctions = retained


def update_junction(candidate, op, choices):
    page, cem = candidate.snapshots.schematic, candidate.snapshots.cem
    find([p for s in page.symbols for p in s.pins], op.target.pin_id, op)
    wires = [w for w in page.wires if op.target.pin_id in (w.source_pin_id, w.target_pin_id)]
    connections = {c.id: c for c in cem.connections}
    if len(wires) < 2 or len({connections[w.conductor_id].net_id for w in wires}) != 1:
        reject(op, 'OPERATION_JUNCTION', 'Junction presentation requires an existing shared pin in one CEM net.')
    junction = next((j for j in page.junctions if j.pin_id == op.target.pin_id), None)
    if junction is None:
        junction = SchematicJunction(id=str(uuid5(op.operation_id, 'junction')), pin_id=op.target.pin_id)
        page.junctions.append(junction)
    junction.label, junction.visible = op.parameters.label, op.parameters.visible
    return ['presentation']


def topology_evidence(document, op):
    try:
        evidence = ElectricalTopologyEvidence.model_validate(document.configuration.get('electrical_topology', {}))
        domains = {(item.component_id, item.terminal_id): ElectricalDomain(supply_id=item.supply_id, role=item.role)
                   for item in evidence.domains}
        equivalences = tuple(TerminalEquivalence.model_validate(e.model_dump()) for e in evidence.equivalences)
    except (ValidationError, ValueError, TypeError, KeyError, AttributeError):
        reject(op, 'OPERATION_TOPOLOGY_EVIDENCE', 'Explicit supply/terminal role evidence is missing or malformed.')
    return domains, equivalences


def check_conductor(candidate, connection, op):
    cem = candidate.snapshots.cem
    net = next((n for n in cem.nets if n.id == connection.net_id), None)
    if net is None or net.wire_class != connection.wire_class:
        reject(op, 'OPERATION_CONNECTION', 'Conductor requires an existing net of the same electrical class.')
    if connection.from_component == connection.to_component:
        reject(op, 'OPERATION_CONNECTION', 'A conductor must connect distinct components.')
    registry = {c.id: {t['id']: t for t in c.terminals} for c in cem.components}
    registry.update({i.component_id: {t: {} for t in i.terminal_ids} for i in candidate.document.enclosure_interfaces})
    for component, terminal in ((connection.from_component, connection.from_terminal),
                                (connection.to_component, connection.to_terminal)):
        if component not in registry or terminal not in registry[component]:
            reject(op, 'OPERATION_TERMINALS', 'Conductor endpoints must reference existing explicit terminals.')
        spec = registry[component][terminal]
        area = connection.cross_section_mm2
        if ((spec.get('conductor_min_mm2') is not None and area < spec['conductor_min_mm2'])
                or (spec.get('conductor_max_mm2') is not None and area > spec['conductor_max_mm2'])):
            reject(op, 'OPERATION_CONDUCTOR', 'Conductor area is outside the pinned terminal capacity.')
    ends = frozenset(((connection.from_component, connection.from_terminal),
                      (connection.to_component, connection.to_terminal)))
    if any(c.id != connection.id and frozenset(((c.from_component, c.from_terminal),
            (c.to_component, c.to_terminal))) == ends for c in cem.connections):
        reject(op, 'OPERATION_CONNECTION', 'Duplicate terminal conductors require a separate supported proposal.')


def modify_connection(candidate, op, choices):
    cem, pdm, page = candidate.snapshots.cem, candidate.snapshots.pdm, candidate.snapshots.schematic
    action, intent, key = op.parameters.action, op.parameters.conductor, op.target.connection_id
    existing = next((c for c in cem.connections if c.id == key), None)
    if ((action == 'CREATE' and (key is not None or intent is None))
            or (action != 'CREATE' and existing is None)
            or (action == 'REPLACE' and intent is None) or (action == 'DELETE' and intent is not None)):
        reject(op, 'OPERATION_CONNECTION', 'Connection action, identity and conductor intent disagree.')
    key = str(uuid5(op.operation_id, 'conductor')) if action == 'CREATE' else key
    routes = [r.id for r in pdm.routes if r.conductor_id == key] if pdm else []
    if sorted(routes) != sorted(op.parameters.invalidated_route_ids):
        reject(op, 'OPERATION_ROUTE_CONSEQUENCES', 'Explicitly list the exact physical routes invalidated by this conductor edit.')
    replacement = ConnectionRef(id=key, **intent.model_dump()) if intent is not None else None
    if replacement is not None:
        check_conductor(candidate, replacement, op)
        if existing == replacement:
            return []
    index = next((i for i, c in enumerate(cem.connections) if c.id == key), len(cem.connections))
    cem.connections = [c for c in cem.connections if c.id != key]
    if replacement is not None:
        # Preserve existing conductor ordering, which is part of canonical state.
        cem.connections.insert(index, replacement)
    for net in cem.nets:
        net.connections = [c for c in cem.connections if c.net_id == net.id]
    removed_nets = [net.id for net in cem.nets if not net.connections and existing is not None
                    and net.id == existing.net_id]
    if sorted(removed_nets) != sorted(op.parameters.removed_net_ids):
        reject(op, 'OPERATION_NET_CONSEQUENCES', 'Explicitly list the exact nets emptied by this conductor edit.')
    cem.nets = [net for net in cem.nets if net.id not in removed_nets]
    domains, equivalences = topology_evidence(candidate.document, op)
    if replacement is not None:
        for endpoint in ((replacement.from_component, replacement.from_terminal),
                         (replacement.to_component, replacement.to_terminal)):
            domain = domains.get(endpoint)
            if domain is not None and ((domain.role == 'PE') != (replacement.wire_class == 'PE')
                                       or (domain.role == 'N') != (replacement.wire_class == 'NEUTRAL')):
                reject(op, 'OPERATION_CONNECTION', 'Conductor class conflicts with explicit terminal phase/N/PE roles.')
    project_legacy_connectivity(cem, domains=domains, equivalences=equivalences).require_consistent()
    if pdm:
        pdm.routes = [r for r in pdm.routes if r.id not in routes]
        for duct in pdm.ducts:
            duct.route_ids = [r for r in duct.route_ids if r not in routes]
    if page:
        wires = [w for w in page.wires if w.conductor_id == key]
        if replacement is None:
            page.wires = [w for w in page.wires if w.conductor_id != key]
        else:
            pins = {}
            for symbol in page.symbols:
                for pin in symbol.pins:
                    pins.setdefault((symbol.component_id, pin.terminal_id), []).append(pin)
            endpoints = [(replacement.from_component, replacement.from_terminal),
                         (replacement.to_component, replacement.to_terminal)]
            if any(len(pins.get(endpoint, [])) != 1 for endpoint in endpoints):
                reject(op, 'OPERATION_PRESENTATION', 'Connection requires one unambiguous schematic pin for each endpoint.')
            source, target = [pins[endpoint][0] for endpoint in endpoints]
            if not wires:
                wires = [SchematicWire(id=str(uuid5(op.operation_id, 'schematic-wire')), conductor_id=key,
                    source_pin_id=source.id, target_pin_id=target.id, waypoints=[source.position, target.position])]
                page.wires.extend(wires)
            for wire in wires:
                wire.source_pin_id, wire.target_pin_id = source.id, target.id
                wire.waypoints = [source.position.model_copy(deep=True), target.position.model_copy(deep=True)]
        prune_junctions(page, cem)
    return ['connections']


def regenerate_schematic(candidate, op, choices):
    page = candidate.snapshots.schematic
    if op.target.schematic_id != page.id:
        reject(op, 'OPERATION_TARGET', 'Regeneration target must match this page.')
    if op.proposal_status != 'PROPOSED':
        reject(op, 'OPERATION_PROPOSAL_REQUIRED', 'Schematic regeneration must be an explicit proposal.')
    generated = SchematicEngine().generate_schematic_data(candidate.snapshots.cem)
    old_symbols = {s.component_id: s for s in page.symbols}
    if len(old_symbols) != len(page.symbols):
        reject(op, 'OPERATION_PRESENTATION', 'Regeneration requires unambiguous component symbols. Review a new proposal.')
    registered = {c.id for c in candidate.snapshots.cem.components} | {
        i.component_id for i in candidate.document.enclosure_interfaces}
    symbols = []
    for spec in generated['symbols']:
        if spec['id'] not in registered:
            continue
        old = old_symbols.get(spec['id'])
        if old is not None and not op.parameters.replace_manual_positions:
            symbols.append(old)
            continue
        old_pins = {p.terminal_id: p for p in old.pins} if old else {}
        symbols.append(SchematicSymbol(id=old.id if old else str(uuid5(op.operation_id, 'symbol:' + spec['id'])),
            component_id=spec['id'], position=dict(x=spec['x'], y=spec['y']),
            width_mm=spec['width'], height_mm=spec['height'], label=old.label if old else spec['label'],
            pins=[SchematicPin(id=old_pins[t['id']].id if t['id'] in old_pins else str(uuid5(op.operation_id, 'pin:' + t['port_id'])),
                terminal_id=t['id'], position=dict(x=t['x'], y=t['y']), direction=t['direction'],
                label=old_pins[t['id']].label if t['id'] in old_pins else '') for t in spec['terminals']]))
    pins = {(s.component_id, p.terminal_id): p for s in symbols for p in s.pins}
    old_wires = {w.conductor_id: w for w in page.wires}
    wires = []
    for connection in candidate.snapshots.cem.connections:
        a = pins.get((connection.from_component, connection.from_terminal))
        b = pins.get((connection.to_component, connection.to_terminal))
        if a is None or b is None:
            reject(op, 'OPERATION_PRESENTATION', 'Regeneration cannot resolve a conductor endpoint.')
        old = old_wires.get(connection.id)
        if old and not op.parameters.replace_manual_positions and (old.source_pin_id, old.target_pin_id) == (a.id, b.id):
            wires.append(old)
        else:
            wires.append(SchematicWire(id=old.id if old else str(uuid5(op.operation_id, 'wire:' + connection.id)),
                conductor_id=connection.id, source_pin_id=a.id, target_pin_id=b.id,
                label=old.label if old else '', waypoints=[a.position, b.position]))
    page.symbols, page.wires = symbols, wires
    page.width_mm, page.height_mm = max(page.width_mm, generated['width']), max(page.height_mm, generated['height'])
    prune_junctions(page, candidate.snapshots.cem)
    return ['presentation']
