"""Detached DB physical adapters, in enclosure millimetres.

Execution order within registered ``placement`` is enclosure -> zoning ->
placement -> ducts/assembly. Then run routes -> physical_validation -> CAD.
BOM needs selection and assembly only. Candidate retry remains a caller concern.
No adapter reads catalogs, publishes revisions, or reconciles manual intent.
"""
import json
from dataclasses import asdict
from typing import Annotated, Any, Literal

from pydantic import BaseModel, PlainSerializer, TypeAdapter, field_validator, model_validator

from app.algorithms.cp_sat_placement import CPSATPlacementOptimizer, LayoutResult, validate_layout
from app.algorithms.duct_routing import DuctRouter
from app.algorithms.jps_theta_star import RoutePlanningError
from app.algorithms.layout_config import LayoutConfig
from app.models.cem import CanonicalEngineeringModel
from app.models.document import GenerationIntent
from app.models.identity import StableID, unique_ids
from app.models.pdm import DesignValidationPolicy, EnclosureSpec, PhysicalDesignModel
from app.services.design_errors import DesignError
from app.services.enclosure_engine import EnclosureEngine
from app.services.netlist_engine import NetlistEngine
from app.services.panel_assembly import PanelAssemblyEngine
from app.services.panel_geometry import component_geometry
from app.services.stages.contracts import FrozenContract
from app.services.stages.electrical import ElectricalContext, Snapshot, _stage_ids
from app.services.validation_engine import ValidationEngine
from app.services.wire_geometry import build_wire_geometry


def _layout_payload(config) -> dict[str, Any]:
    payload = asdict(config)
    for key in ('din_categories', 'plate_categories'):
        payload[key] = sorted(payload[key])
    return payload


class LayoutSnapshot(Snapshot[LayoutConfig]):
    """Stable set ordering across serialization and interpreter processes."""
    @classmethod
    def _adapter(cls):
        return TypeAdapter(Annotated[LayoutConfig, PlainSerializer(_layout_payload)])


def _restore_number_types(parsed, raw):
    # Legacy engines assign integer zero to float accounting fields (notably
    # empty duct wire_area_mm2). Preserve JSON number types after validation so
    # an extraction boundary does not change the existing snapshot hashes.
    if isinstance(parsed, BaseModel) and isinstance(raw, dict):
        for key in type(parsed).model_fields.keys() & raw.keys():
            setattr(parsed, key, _restore_number_types(getattr(parsed, key), raw[key]))
    elif isinstance(parsed, list) and isinstance(raw, list):
        return [_restore_number_types(a, b) for a, b in zip(parsed, raw)]
    elif isinstance(parsed, float) and type(raw) is int and parsed == raw:
        return raw
    return parsed


class PhysicalSnapshot(Snapshot[PhysicalDesignModel]):
    """Validated PDM with lossless legacy JSON numeric representation."""
    @classmethod
    def _adapter(cls):
        return TypeAdapter(PhysicalDesignModel)

    @field_validator('data_json')
    @classmethod
    def canonical_payload(cls, value):
        raw = json.loads(value)
        parsed = _restore_number_types(cls._adapter().validate_python(raw), raw)
        return json.dumps(parsed.model_dump(), sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False)

    @classmethod
    def capture(cls, value):
        # Pydantic's JSON mode itself normalizes int assignments into floats.
        payload = value.model_dump() if isinstance(value, BaseModel) else value
        return cls(data_json=json.dumps(payload, allow_nan=False))

    def read(self):
        return _restore_number_types(super().read(), json.loads(self.data_json))


class PinnedEnclosures(FrozenContract):
    catalog_version: StableID
    rows: Snapshot[list[EnclosureSpec]]

    @model_validator(mode='after')
    def unique_catalog(self):
        unique_ids((row.id for row in self.rows.read()), 'catalog.enclosures')
        return self


class PinnedHardware(FrozenContract):
    catalog_version: StableID
    rows: Snapshot[list[dict[str, Any]]]

    @model_validator(mode='after')
    def unique_catalog(self):
        unique_ids((row.get('code', row['id']) for row in self.rows.read()), 'catalog.hardware')
        return self


class PhysicalInput(FrozenContract):
    context: ElectricalContext
    cem: Snapshot[CanonicalEngineeringModel]


class EnclosureInput(PhysicalInput):
    algorithm_version: Literal['db-placement-1'] = 'db-placement-1'
    catalog: PinnedEnclosures
    layout: LayoutSnapshot
    ip_rating: StableID
    # A selected/locked enclosure is filtered before feasibility, never upsized.
    enclosure_id: StableID | None = None


class EnclosureOutput(FrozenContract):
    candidates: Snapshot[list[EnclosureSpec]]


class ZoningInput(FrozenContract):
    algorithm_version: Literal['db-placement-1'] = 'db-placement-1'
    enclosure: Snapshot[EnclosureSpec]
    layout: LayoutSnapshot
    hardware: PinnedHardware


class ZoningOutput(FrozenContract):
    enclosure: Snapshot[EnclosureSpec]
    layout: LayoutSnapshot
    hardware: PinnedHardware


class PlacementInput(PhysicalInput):
    algorithm_version: Literal['db-placement-1'] = 'db-placement-1'
    zoning: ZoningOutput
    intent: Snapshot[GenerationIntent] = Snapshot[GenerationIntent].capture(GenerationIntent())
    # Whole accepted placement/assembly is retained conservatively. The current
    # solver has no fixed-variable API; partial locked solving is not invented.
    accepted_layout: PhysicalSnapshot | None = None


class PhysicalOutput(FrozenContract):
    pdm: PhysicalSnapshot


class PlacementOutput(PhysicalOutput):
    zoning: ZoningOutput
    retained_assembly: bool = False


class DuctsInput(FrozenContract):
    algorithm_version: Literal['db-placement-1'] = 'db-placement-1'
    placement: PlacementOutput


class RoutesInput(PhysicalInput):
    algorithm_version: Literal['db-routes-1'] = 'db-routes-1'
    pdm: PhysicalSnapshot
    layout: LayoutSnapshot
    # Global bundle lanes and capacity are coupled. A locked route blocks full
    # network rerouting; callers may instead rebuild local geometry unchanged.
    locked_route_ids: tuple[StableID, ...] = ()

    @model_validator(mode='after')
    def unique_locks(self):
        unique_ids(self.locked_route_ids, 'locked_route_ids')
        return self


class PhysicalValidationInput(PhysicalInput):
    algorithm_version: Literal['db-physical_validation-1'] = 'db-physical_validation-1'
    pdm: PhysicalSnapshot


class GeometryInput(PhysicalValidationInput):
    """Rebuild derived meshes/fillets from existing paths; never find new paths."""


def _cem(inputs):
    cem = inputs.cem.read()
    if (cem.project_id, cem.panel_id) != (inputs.context.project_id, inputs.context.panel_id):
        raise DesignError('STAGE_IDENTITY_MISMATCH', 'CEM ownership differs from stage input.')
    _stage_ids((c.id for c in cem.components), 'cem.components')
    _stage_ids((n.id for n in cem.nets), 'cem.nets')
    _stage_ids((c.id for n in cem.nets for c in n.connections), 'cem.connections')
    if cem.connections != [c for n in cem.nets for c in n.connections] or any(
        c.net_id != n.id for n in cem.nets for c in n.connections
    ):
        raise DesignError('INVALID_NETLIST', 'Canonical connections differ from net membership.')
    valid, errors = NetlistEngine().validate_netlist(cem.nets, cem.components)
    if not valid:
        raise DesignError('INVALID_NETLIST', 'Physical stage requires valid electrical connectivity.',
                          {'errors': errors}, errors)
    return cem


def _ownership(cem, pdm):
    if (pdm.project_id, pdm.panel_id) != (cem.project_id, cem.panel_id):
        raise DesignError('STAGE_IDENTITY_MISMATCH', 'PDM ownership differs from stage input.')
    for field in ('components', 'rails', 'ducts', 'accessories', 'routes'):
        _stage_ids((item.id for item in getattr(pdm, field)), 'pdm.'+field)
    _stage_ids((c.cem_component_id for c in pdm.components), 'pdm.component_references')
    rail_ids = {r.id for r in pdm.rails}
    if any(c.rail_id is not None and c.rail_id not in rail_ids for c in pdm.components):
        raise DesignError('STAGE_IDENTITY_MISMATCH', 'A component references an absent DIN rail.')
    components = {c.id: c for c in cem.components}
    for part in pdm.components:
        component = components.get(part.cem_component_id)
        if component is not None and (
            (part.width, part.height, part.depth, part.category, part.heat_loss_watts, part.terminals) !=
            (component.width, component.height, component.depth, component.category, component.heat_loss, component.terminals)
        ):
            raise DesignError('STAGE_COMPONENT_MISMATCH', 'Accepted geometry differs from the supplied component.',
                              {'component_id': part.cem_component_id})


def enclosure_stage(inputs: EnclosureInput) -> EnclosureOutput:
    cem = _cem(inputs)
    width = sum(c.width for c in cem.components if c.category in {'MCCB', 'MCB', 'SPD', 'BUSBAR'})
    heat = sum(c.heat_loss for c in cem.components)
    config = inputs.layout.read()
    rows = [r.model_dump() for r in inputs.catalog.rows.read()
            if inputs.enclosure_id is None or r.id == inputs.enclosure_id]

    class SuppliedEnclosures:
        def get_all(self):
            return rows

    candidates = EnclosureEngine(SuppliedEnclosures()).candidates(
        width, heat, inputs.ip_rating, config.thermal_density_limit_w_per_l)
    if not candidates:
        raise DesignError('NO_FEASIBLE_ENCLOSURE',
            'No catalog enclosure satisfies the geometry, heat density and IP constraints; choose a larger enclosure or revise the requirements.',
            {'minimum_component_width_mm': width, 'total_heat_loss_w': heat,
             'thermal_density_limit_w_per_l': config.thermal_density_limit_w_per_l,
             'minimum_volume_litres': heat/config.thermal_density_limit_w_per_l,
             'ip_rating': inputs.ip_rating})
    return EnclosureOutput(candidates=Snapshot[list[EnclosureSpec]].capture(candidates))


def zoning_stage(inputs: ZoningInput) -> ZoningOutput:
    # Existing zoning is enclosure metadata plus category preferences and hard
    # trough reservations in LayoutConfig, not a separate optimization algorithm.
    config = PanelAssemblyEngine(inputs.hardware.rows.read()).layout_config(
        inputs.enclosure.read(), inputs.layout.read())
    return ZoningOutput(enclosure=inputs.enclosure, layout=LayoutSnapshot.capture(config),
                        hardware=inputs.hardware)


def placement_stage(inputs: PlacementInput) -> PlacementOutput:
    cem = _cem(inputs)
    enclosure, config = inputs.zoning.enclosure.read(), inputs.zoning.layout.read()
    intent = inputs.intent.read()
    if (intent.locked_placements or 'pdm' in intent.manual_models) and inputs.accepted_layout is None:
        raise DesignError('STAGE_LOCK_CONFLICT', 'Locked/manual placement requires an accepted layout.')
    if inputs.accepted_layout is not None:
        pdm = inputs.accepted_layout.read()
        _ownership(cem, pdm)
        frame = dict(enclosure_id=enclosure.id, enclosure_width=enclosure.width,
            enclosure_height=enclosure.height, enclosure_depth=enclosure.depth,
            mounting_plate_x=enclosure.mounting_plate_offset_x,
            mounting_plate_y=enclosure.mounting_plate_offset_y,
            mounting_plate_z=enclosure.mounting_plate_offset_z,
            mounting_plate_width=enclosure.mounting_plate_width,
            mounting_plate_height=enclosure.mounting_plate_height, ip_rating=enclosure.ip_rating)
        if any(getattr(pdm, key) != value for key, value in frame.items()):
            raise DesignError('STAGE_LOCK_CONFLICT', 'Accepted placement uses a different enclosure frame.')
        if not set(intent.locked_placements).issubset(c.cem_component_id for c in pdm.components):
            raise DesignError('STAGE_LOCK_CONFLICT', 'A locked component is absent from accepted placement.')
        pdm.routes = []
        pdm.validation_results = []
        pdm.total_heat_loss_watts = sum(c.heat_loss for c in cem.components)
        _validate(pdm, cem, require_routes=False)
        return PlacementOutput(pdm=PhysicalSnapshot.capture(pdm), zoning=inputs.zoning,
                               retained_assembly=True)
    connections = [(c.from_component, c.to_component) for c in cem.connections
                   if c.from_component != 'PANEL_ROOT' and c.to_component != 'PANEL_ROOT']
    try:
        placement = CPSATPlacementOptimizer(config).solve(
            cem.components, enclosure.width, enclosure.height, connections)
    except RuntimeError as exc:
        raise DesignError('PLACEMENT_ENGINE_UNAVAILABLE', 'The placement solver is unavailable.',
                          {'reason': str(exc)}) from exc
    if not placement.feasible:
        raise DesignError('PLACEMENT_INFEASIBLE', 'Selected components cannot be placed in the selected enclosure.',
            {'enclosure_id': enclosure.id, 'solver_status': placement.status, 'reason': placement.message})
    violations = placement.violations or validate_layout(placement.components, enclosure.width, enclosure.height, config)
    if violations:
        raise DesignError('PLACEMENT_INVALID', 'The placement solver returned geometry that fails its independent checks.',
                          {'violations': violations})
    pdm = PhysicalDesignModel(id='PDM-'+cem.project_id, project_id=cem.project_id, panel_id=cem.panel_id,
        enclosure_id=enclosure.id, enclosure_width=enclosure.width, enclosure_height=enclosure.height,
        enclosure_depth=enclosure.depth, ip_rating=enclosure.ip_rating,
        mounting_plate_x=enclosure.mounting_plate_offset_x, mounting_plate_y=enclosure.mounting_plate_offset_y,
        mounting_plate_z=enclosure.mounting_plate_offset_z, mounting_plate_width=enclosure.mounting_plate_width,
        mounting_plate_height=enclosure.mounting_plate_height, zones=enclosure.zones,
        components=placement.components, rails=placement.rails,
        total_heat_loss_watts=sum(c.heat_loss for c in cem.components),
        validation_policy=DesignValidationPolicy.from_layout(config))
    return PlacementOutput(pdm=PhysicalSnapshot.capture(pdm), zoning=inputs.zoning)


def ducts_stage(inputs: DuctsInput) -> PhysicalOutput:
    placed = inputs.placement
    pdm = placed.pdm.read()
    if not placed.retained_assembly:
        assembly = PanelAssemblyEngine(placed.zoning.hardware.rows.read())
        pdm.ducts = assembly.ducts(LayoutResult(True, 'FEASIBLE', components=pdm.components, rails=pdm.rails),
                                  placed.zoning.enclosure.read(), placed.zoning.layout.read())
        pdm.construction = assembly.parameters('PANEL_SHELL_STEEL')
        pdm.accessories = assembly.accessories(pdm)
    for part in pdm.components:
        part.geometry = component_geometry(part)
    return PhysicalOutput(pdm=PhysicalSnapshot.capture(pdm))


def routes_stage(inputs: RoutesInput) -> PhysicalOutput:
    cem, pdm = _cem(inputs), inputs.pdm.read()
    _ownership(cem, pdm)
    if inputs.locked_route_ids:
        raise DesignError('STAGE_LOCK_CONFLICT', 'Connected duct-network rerouting would replace locked routes.',
                          {'route_ids': list(inputs.locked_route_ids)})
    pdm.routes = []  # Existing routes are never mixed with new global bundle lanes.
    _validate(pdm, cem, require_routes=False)
    config = inputs.layout.read()
    config.wire_clearance = pdm.validation_policy.wire_clearance_mm
    # Keep the legacy main-net diameter rule independent of opaque document IDs.
    nets = cem.model_copy(deep=True).nets
    for net in nets:
        net.id = inputs.context.identities.role('net', net.id)
        for conn in net.connections:
            conn.net_id = net.id
    try:
        pdm.routes = DuctRouter(config).route_layout(
            LayoutResult(True, 'FEASIBLE', components=pdm.components, rails=pdm.rails), nets,
            pdm.enclosure_width, pdm.enclosure_height, pdm.enclosure_depth, ducts=pdm.ducts)
    except RoutePlanningError as exc:
        raise DesignError('ROUTING_INFEASIBLE', 'An electrical connection could not be routed.',
            {'connection_id': exc.connection_id, 'net_id': inputs.context.identities.resolve('net', exc.net_id),
             'reason': exc.reason}) from exc
    except ValueError as exc:
        raise DesignError('ROUTING_INFEASIBLE', 'An electrical connection could not be routed.',
                          {'reason': str(exc)}) from exc
    for route in pdm.routes:
        route.net_id = inputs.context.identities.resolve('net', route.net_id)
    # The registered routes result owns exact wire geometry, not just paths.
    return local_geometry_stage(GeometryInput(context=inputs.context, cem=inputs.cem,
                                              pdm=PhysicalSnapshot.capture(pdm)))


def _validate(pdm, cem, require_routes=True):
    _ownership(cem, pdm)
    if any(abs(c.rotation_deg) % 360 > 1e-6 for c in pdm.components):
        raise DesignError('ROUTING_INFEASIBLE', 'Rotated-device obstacle routing is not supported; restore zero rotation.')
    if abs(pdm.total_heat_loss_watts - sum(c.heat_loss for c in cem.components)) > 1e-6:
        raise DesignError('STAGE_COMPONENT_MISMATCH', 'Physical heat total differs from supplied components.')
    if require_routes and cem.connections and not pdm.ducts:
        raise DesignError('ROUTING_INFEASIBLE', 'Physical wiring ducts are required for duct routing.')
    # Validate placement before routing without inventing missing-route failures.
    electrical = cem if require_routes else cem.model_copy(update={'nets': [], 'connections': []})
    violations = ValidationEngine().validate_pdm(pdm, electrical)
    if require_routes:
        expected = {'ROUTE-'+c.id: c.id for c in cem.connections}
        if set(expected) != {r.id for r in pdm.routes} or any(
            r.conductor_id != expected.get(r.id) for r in pdm.routes
        ):
            raise DesignError('ROUTING_INFEASIBLE', 'Route-to-connection identities are incomplete or inconsistent.')
        connections = {c.id: c for c in cem.connections}
        for route in pdm.routes:
            connection = connections[route.conductor_id]
            if (route.wire_class != connection.wire_class or
                route.minimum_bend_radius_mm != connection.minimum_bend_radius_mm or
                (connection.insulation_diameter_mm is not None and
                 route.wire_diameter_mm != connection.insulation_diameter_mm)):
                raise DesignError('ROUTING_INFEASIBLE', 'Route conductor properties differ from electrical intent.',
                                  {'route_id': route.id, 'connection_id': connection.id})
    pdm.validation_results = violations
    if violations:
        raise DesignError('PHYSICAL_VALIDATION_FAILED', 'The generated physical design does not satisfy all physical constraints.',
                          {'violations': [v.model_dump() for v in violations]})


def local_geometry_stage(inputs: GeometryInput) -> PhysicalOutput:
    cem, pdm = _cem(inputs), inputs.pdm.read()
    _validate(pdm, cem)
    for part in pdm.components:
        part.geometry = component_geometry(part)
    for route in pdm.routes:
        try:
            route.geometry = build_wire_geometry(route, pdm)
            route.validation_checks = route.geometry.checks
        except ValueError as exc:
            raise DesignError('ROUTING_INFEASIBLE', 'Wire geometry validation failed.',
                              {'route_id': route.id, 'reason': str(exc)}) from exc
    return PhysicalOutput(pdm=PhysicalSnapshot.capture(pdm))


def physical_validation_stage(inputs: PhysicalValidationInput) -> PhysicalOutput:
    # Geometry checks follow independent placement/duct/terminal validation just
    # as in full generation. Old PASS flags and cached meshes are never trusted.
    return local_geometry_stage(GeometryInput(context=inputs.context, cem=inputs.cem, pdm=inputs.pdm))
