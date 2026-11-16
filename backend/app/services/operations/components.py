"""Catalog-backed component commands and exact, reviewable removal closures."""
from uuid import uuid5

from app.models.cem import ComponentRef
from app.models.operations import CascadeConfirmation
from app.models.electrical_topology import ElectricalTopologyEvidence
from app.models.pdm import PhysicalComponent
from app.persistence.assets import content_hash
from app.services.design_errors import DesignError
from app.services.operations.engineering import catalog_choice, reject
from app.services.operations.physical import validate_placement
from pydantic import ValidationError


def allocated_ids(op):
    # Repeated preview, commit and retry allocate the same opaque identities.
    return str(uuid5(op.operation_id, 'cem-component')), str(uuid5(op.operation_id, 'pdm-component'))


def add_component(candidate, op, choices):
    cem, pdm = candidate.snapshots.cem, candidate.snapshots.pdm
    if pdm is None or op.target.panel_id != candidate.document.panel_id:
        reject(op, 'OPERATION_TARGET', 'Add requires an existing physical panel and explicit placement.')
    row = dict(catalog_choice(op, choices))
    product = op.parameters.product_version_id
    if product is not None and (op.parameters.component_version_id, product) not in choices.products:
        reject(op, 'OPERATION_CATALOG', 'Product choice must be an exact published version of the selected component.')
    row['product_version_id'] = product
    if row['category'] not in {'MCB', 'MCCB', 'SPD', 'BUSBAR', 'NEUTRAL_BAR', 'EARTH_BAR', 'TERMINAL'}:
        reject(op, 'OPERATION_CATALOG', 'Only DB electrical devices can be added with this command.')
    terminal_ids = [t['id'] for t in row['terminals']]
    if sorted(op.parameters.terminal_ids) != sorted(terminal_ids):
        reject(op, 'OPERATION_TERMINALS', 'Explicit unconnected terminal intent must cover the exact catalog terminals.')
    electrical_id, physical_id = allocated_ids(op)
    if (electrical_id in {c.id for c in cem.components}
            or electrical_id in {i.component_id for i in candidate.document.enclosure_interfaces}
            or physical_id in {c.id for c in pdm.components}):
        reject(op, 'OPERATION_TARGET', 'Allocated component identities already exist.')
    intent = op.parameters.placement
    if intent.zone_name not in {z.name for z in pdm.zones} or (
            intent.rail_id is not None and intent.rail_id not in {r.id for r in pdm.rails}):
        reject(op, 'OPERATION_TARGET', 'Placement requires an existing zone and rail, when specified.')
    if row['mounting'] == 'DIN' and intent.rail_id is None:
        reject(op, 'OPERATION_TARGET', 'DIN devices require explicit rail intent.')
    if any(c.rotation_deg != 0 for c in pdm.components):
        reject(op, 'UNSUPPORTED_ROTATION', 'Adding to rotated layouts requires validated oriented geometry support.')
    values = {k: row[k] for k in ('name', 'category', 'current_rating', 'breaking_capacity', 'poles',
        'width', 'height', 'depth', 'mounting', 'heat_loss', 'cad_model', 'terminals',
        'component_version_id', 'product_version_id')}
    component = ComponentRef(id=electrical_id, catalog_id=row['code'], **values)
    position = intent.position_mm.model_dump()
    terminals = []
    for terminal in component.terminals:
        if any(type(terminal.get(axis)) not in (int, float) for axis in ('x', 'y', 'z')):
            reject(op, 'OPERATION_CATALOG', 'Pinned catalog terminals require local millimetre coordinates.')
        terminals.append({**terminal, **{axis: terminal[axis] + position[axis] for axis in position}})
    physical = PhysicalComponent(id=physical_id, cem_component_id=electrical_id,
        position=position, rail_id=intent.rail_id, zone_name=intent.zone_name,
        heat_loss_watts=component.heat_loss, terminals=terminals,
        **{k: getattr(component, k) for k in ('name', 'category', 'width', 'height', 'depth', 'cad_model')})
    zone = next(z for z in pdm.zones if z.name == intent.zone_name)
    if (position['x'] < zone.x_min or position['y'] < zone.y_min or position['z'] < zone.z_min
            or position['x'] + physical.width > zone.x_max or position['y'] + physical.height > zone.y_max
            or position['z'] + physical.depth > zone.z_max):
        reject(op, 'OPERATION_GEOMETRY', 'The device envelope must fit the explicitly selected physical zone.')
    pdm.components.append(physical)
    # A new device must not bypass the saved thermal policy using a stale total.
    pdm.total_heat_loss_watts = max(pdm.total_heat_loss_watts,
                                  sum(c.heat_loss_watts for c in pdm.components[:-1])) + physical.heat_loss_watts
    validate_placement(pdm, op)
    cem.components.append(component)
    candidate.document.pins.catalog_versions['component:' + electrical_id] = component.component_version_id
    if component.product_version_id:
        candidate.document.pins.catalog_versions['product:' + electrical_id] = component.product_version_id
    return ['components']


def removal_consequences(candidate, op):
    cem, pdm, schematic = candidate.snapshots.cem, candidate.snapshots.pdm, candidate.snapshots.schematic
    target = op.target.cem_component_id
    component = next((c for c in cem.components if c.id == target), None)
    if component is None:
        reject(op, 'OPERATION_TARGET', 'Removal requires an existing electrical component.')
    connections = [c for c in cem.connections if target in (c.from_component, c.to_component)]
    connection_ids = {c.id for c in connections}
    physical = [c for c in pdm.components if c.cem_component_id == target] if pdm else []
    parents = {c.id for c in physical}
    if pdm and parents & {item.id for group in (pdm.rails, pdm.ducts, pdm.accessories) for item in group}:
        reject(op, 'OPERATION_CASCADE_AMBIGUOUS', 'Physical parent identities overlap. Resolve the ambiguity in a new proposal.')
    accessories = []
    if pdm:
        while True:
            found = [a for a in pdm.accessories if a.parent_id in parents and a.id not in parents]
            if not found:
                break
            accessories.extend(found)
            parents.update(a.id for a in found)
    objects = dict(components=[component], connections=connections, physical_components=physical,
        routes=[r for r in pdm.routes if r.conductor_id in connection_ids] if pdm else [],
        symbols=[s for s in schematic.symbols if s.component_id == target] if schematic else [],
        wires=[w for w in schematic.wires if w.conductor_id in connection_ids] if schematic else [],
        modules=[m for m in cem.modules if m.assigned_component_id == target], accessories=accessories,
        clearances=[c for c in pdm.clearances if c.component_id in parents] if pdm else [],
        graph_nodes=[n for n in cem.electrical_graph.nodes if n.id == target] if cem.electrical_graph else [],
        graph_edges=[e for e in cem.electrical_graph.edges if target in (e.source, e.target)] if cem.electrical_graph else [])
    removed_pins = {p.id for s in objects['symbols'] for p in s.pins}
    removed_wires = {w.id for w in objects['wires']}
    objects['junctions'] = [j for j in schematic.junctions if j.pin_id in removed_pins or sum(
        j.pin_id in (w.source_pin_id, w.target_pin_id) for w in schematic.wires if w.id not in removed_wires) < 2] if schematic else []
    removed_objects = parents | connection_ids | {r.id for r in objects['routes']} | {target}
    objects['physical_diagnostics'] = [v for v in pdm.validation_results if v.object_a in removed_objects
                                     or v.object_b in removed_objects] if pdm else []
    payload = {key: [value.model_dump(mode='json') for value in values] for key, values in objects.items()}
    # Edges/envelopes have no stable ID. Their content digests identify the exact
    # consequences; the overall digest also fences changes to dependent content.
    dependencies = {key: sorted(str(getattr(value, 'id', content_hash(value.model_dump(mode='json'))))
                                for value in values) for key, values in objects.items()}
    topology = candidate.document.configuration.get('electrical_topology', {})
    if 'electrical_topology' in candidate.document.configuration:
        try:
            ElectricalTopologyEvidence.model_validate(topology)
        except (ValidationError, ValueError, TypeError):
            reject(op, 'OPERATION_TOPOLOGY_EVIDENCE', 'Removal requires valid explicit topology evidence.')
    for key, entries in (
        ('domains', [d for d in topology.get('domains', []) if d.get('component_id') == target]),
        ('equivalences', [e for e in topology.get('equivalences', []) if any(m[0] == target for m in e.get('members', []))])):
        payload[key] = entries
        dependencies[key] = sorted(content_hash(entry) for entry in entries)
    return CascadeConfirmation(dependencies=dependencies, sha256=content_hash(payload))


def remove_component(candidate, op, choices):
    consequence = removal_consequences(candidate, op)
    if op.parameters.confirmed_cascade is None:
        return []  # Read-only consequence proposal; commit separately rejects it.
    if op.parameters.confirmed_cascade != consequence:
        raise DesignError('OPERATION_CASCADE_CHANGED', 'Removal consequences changed. Review a new explicit proposal.',
                          {'operation_id': str(op.operation_id), 'consequences': consequence.model_dump(mode='json')})
    cem, pdm, schematic = candidate.snapshots.cem, candidate.snapshots.pdm, candidate.snapshots.schematic
    ids = {k: set(v) for k, v in consequence.dependencies.items()}
    target = op.target.cem_component_id
    cem.components = [c for c in cem.components if c.id != target]
    cem.connections = [c for c in cem.connections if c.id not in ids['connections']]
    for net in cem.nets:
        net.connections = [c for c in net.connections if c.id not in ids['connections']]
    for module in cem.modules:
        if module.id in ids['modules']:
            module.assigned_component_id = None
    if cem.electrical_graph:
        cem.electrical_graph.nodes = [n for n in cem.electrical_graph.nodes if n.id != target]
        cem.electrical_graph.edges = [e for e in cem.electrical_graph.edges if target not in (e.source, e.target)]
    if pdm:
        pdm.components = [c for c in pdm.components if c.id not in ids['physical_components']]
        pdm.routes = [r for r in pdm.routes if r.id not in ids['routes']]
        pdm.accessories = [a for a in pdm.accessories if a.id not in ids['accessories']]
        pdm.clearances = [c for c in pdm.clearances if c.component_id not in ids['physical_components'] | ids['accessories']]
        pdm.validation_results = [v for v in pdm.validation_results if content_hash(v.model_dump(mode='json')) not in ids['physical_diagnostics']]
        for duct in pdm.ducts:
            duct.route_ids = [r for r in duct.route_ids if r not in ids['routes']]
    if schematic:
        schematic.symbols = [s for s in schematic.symbols if s.id not in ids['symbols']]
        schematic.wires = [w for w in schematic.wires if w.id not in ids['wires']]
        schematic.junctions = [j for j in schematic.junctions if j.id not in ids['junctions']]
    topology = candidate.document.configuration.get('electrical_topology', {})
    for key in ('domains', 'equivalences'):
        if key in topology:
            topology[key] = [entry for entry in topology[key] if content_hash(entry) not in ids[key]]
    for kind in ('component', 'product'):
        candidate.document.pins.catalog_versions.pop(kind + ':' + target, None)
    return ['cascade']
