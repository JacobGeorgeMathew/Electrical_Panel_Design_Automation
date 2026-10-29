from typing import Any, Dict, Optional
from app.algorithms.cp_sat_placement import CPSATPlacementOptimizer
from app.algorithms.jps_theta_star import JPSThetaStarRouter, RoutePlanningError
from app.algorithms.duct_routing import DuctRouter
from app.services.panel_assembly import PanelAssemblyEngine, assembly_bom
from app.algorithms.layout_config import LayoutConfig
from app.models.cem import CEMState, CanonicalEngineeringModel, FunctionalModule
from app.models.pdm import PhysicalDesignModel, DesignValidationPolicy
from app.repositories.component_repository import ComponentRepository
from app.repositories.enclosure_repository import EnclosureRepository
from app.repositories.project_repository import ProjectRepository
from app.services.cad_engine import CADEngine
from app.services.calculation_engine import CalculationEngine
from app.services.change_propagation import ChangePropagationEngine
from app.services.component_selector import ComponentSelector
from app.services.design_errors import DesignError
from app.services.enclosure_engine import EnclosureEngine
from app.services.graph_engine import GraphEngine
from app.services.netlist_engine import NetlistEngine
from app.services.requirement_engine import RequirementEngine
from app.services.schematic_engine import SchematicEngine
from app.services.validation_engine import ValidationEngine


DEFAULT_PROJECT = {
    "id": "",
    "name": "Distribution Board",
    "archetype": "DB",
    "requirements": {"supply_voltage": 415, "phases": 3, "frequency": 50,
                     "incomer_rating": 250, "num_feeders": 12, "ip_rating": "IP54",
                     "spare_capacity_pct": 20, "neutral_required": True},
}


class DesignOrchestrator:
    """Coordinates typed CEM and PDM contracts for deterministic DB generation."""

    def __init__(self, project_repo=None, comp_repo=None, enclosure_repo=None, req_engine=None, layout_config=None, hardware_catalog=None):
        self.project_repo = project_repo or ProjectRepository()
        self.comp_repo = comp_repo or ComponentRepository()
        self.enclosure_repo = enclosure_repo or EnclosureRepository()
        self.req_engine = req_engine or RequirementEngine()
        self.layout_config = layout_config or LayoutConfig()
        self.calc_engine = CalculationEngine()
        self.comp_selector = ComponentSelector(self.comp_repo)
        self.graph_engine = GraphEngine()
        self.netlist_engine = NetlistEngine()
        self.schematic_engine = SchematicEngine()
        self.enclosure_engine = EnclosureEngine(self.enclosure_repo)
        self.placement_optimizer = CPSATPlacementOptimizer()
        self.routing_router = JPSThetaStarRouter()
        self.validation_engine = ValidationEngine()
        self.cad_engine = CADEngine()
        self.change_prop_engine = ChangePropagationEngine()
        self.panel_assembly = PanelAssemblyEngine(hardware_catalog)

    def generate_design(self, project_id: str, requirement_overrides: Optional[Dict[str, Any]] = None,
                        persist_requirements: bool = True) -> Dict[str, Any]:
        project = self.project_repo.get_by_id(project_id)
        project_existed = project is not None
        if not project:
            project = {**DEFAULT_PROJECT, "id": project_id, "name": f"Panel Project {project_id}"}
        if project.get("archetype", "DB") != "DB":
            raise DesignError("UNSUPPORTED_ARCHETYPE", "This workflow currently supports DB projects only.",
                              {"archetype": project.get("archetype")})

        req_values = dict(project.get("requirements", {}))
        if requirement_overrides:
            req_values.update(requirement_overrides)
        req_set = self.req_engine.validate_requirements(project_id, "DB", req_values)
        if not req_set.is_valid:
            raise DesignError("INVALID_REQUIREMENTS", "Requirements must be corrected before design generation.",
                              {"project_id": project_id, "validation_errors": req_set.validation_errors,
                               "validation_warnings": req_set.validation_warnings}, req_set.validation_errors)
        values = {item.id: item.value for item in req_set.items if item.value is not None}

        cem = CanonicalEngineeringModel(
            project_id=project_id, panel_id=f"DB-{project_id}", panel_type="DB",
            state=CEMState.REQUIREMENTS_VALIDATED, requirements=req_set.items,
            modules=[FunctionalModule(id=f"MOD-{m['name']}", name=m["name"], category=m["category"],
                                     required=(m.get("required", True) and
                                               (m["category"] != "NEUTRAL_BAR" or
                                                values.get("neutral_required", values["phases"] == 3))))
                     for m in self.req_engine.get_template("DB").get("modules", [])],
        )

        cem.calculations = self.calc_engine.calculate_db_parameters(values)
        cem.state = CEMState.ENGINEERING_CALCULATED
        busbar_calc = next(result for result in cem.calculations if result.type == "busbar_rating")
        components = self.comp_selector.select_components(
            incomer_rating=values["incomer_rating"], num_feeders=values["num_feeders"],
            phases=values["phases"], neutral_required=values.get("neutral_required", values["phases"] == 3),
            busbar_rating=busbar_calc.value)
        cem.components = components
        for module in cem.modules:
            candidate = next((c for c in components if c.category == module.category), None)
            module.assigned_component_id = candidate.id if candidate else None
        cem.state = CEMState.COMPONENTS_SELECTED

        graph = self.graph_engine.build_electrical_graph(project_id, components)
        cem.electrical_graph = graph
        nets = self.netlist_engine.generate_netlist(graph, components,
                                                    voltage=values["supply_voltage"], phases=values["phases"])
        valid_netlist, errors = self.netlist_engine.validate_netlist(nets, components)
        if not valid_netlist:
            raise DesignError("INVALID_NETLIST", "The selected components do not form a complete electrical netlist.",
                              {"errors": errors}, errors)
        cem.nets = nets
        cem.connections = [connection for net in nets for connection in net.connections]
        net_ids_by_pair: Dict[tuple, set] = {}
        for net in nets:
            for connection in net.connections:
                pair = (connection.from_component, connection.to_component)
                net_ids_by_pair.setdefault(pair, set()).add(net.id)
        for edge in graph.edges:
            edge.properties["net_ids"] = sorted(net_ids_by_pair.get((edge.source, edge.target), set()))
        cem.electrical_graph = graph
        cem.state = CEMState.NETLIST_VALIDATED
        schematic_data = self.schematic_engine.generate_schematic_data(cem)
        cem.state = CEMState.SCHEMATIC_GENERATED

        total_comp_width = sum(c.width for c in components if c.category in {"MCCB", "MCB", "SPD", "BUSBAR"})
        total_heat_loss = sum(c.heat_loss for c in components)
        candidates = self.enclosure_engine.candidates(
            total_components_width=total_comp_width, total_heat_loss=total_heat_loss,
            ip_rating=values["ip_rating"], thermal_density_limit_w_per_l=self.layout_config.thermal_density_limit_w_per_l)
        if not candidates:
            raise DesignError("NO_FEASIBLE_ENCLOSURE", "No catalog enclosure satisfies the geometry, heat density and IP constraints; choose a larger enclosure or revise the requirements.",
                              {"minimum_component_width_mm": total_comp_width, "total_heat_loss_w": total_heat_loss,
                               "thermal_density_limit_w_per_l": self.layout_config.thermal_density_limit_w_per_l,
                               "minimum_volume_litres": total_heat_loss/self.layout_config.thermal_density_limit_w_per_l,
                               "ip_rating": values["ip_rating"]})
        attempted=[]
        pdm=None
        last_error=None
        retryable={"PLACEMENT_INFEASIBLE","PLACEMENT_INVALID","ROUTING_INFEASIBLE",
                   "PHYSICAL_VALIDATION_FAILED","DUCT_SPACE_INFEASIBLE"}
        for enclosure in candidates:
            attempted.append(enclosure.id)
            try:
                pdm,violations=self._physical_design(cem,components,nets,enclosure,total_heat_loss)
                break
            except DesignError as exc:
                if exc.code not in retryable: raise
                last_error=exc
        if pdm is None:
            last_error.details["attempted_enclosure_ids"]=attempted
            raise last_error
        cem.physical_design_id = pdm.id
        cem.state = CEMState.FINAL_VALIDATED
        cad_data = self.cad_engine.generate_parametric_geometry(pdm)
        bom = assembly_bom(cem, pdm)

        if requirement_overrides and persist_requirements and project_existed:
            updated = {**project, "requirements": req_values}
            self.project_repo.save(updated)
        return {"cem": cem.model_dump(), "pdm": pdm.model_dump(), "schematic": schematic_data,
                "cad": cad_data, "bom": bom, "validation_errors": [v.model_dump() for v in violations]}

    def _physical_design(self, cem, components, nets, enclosure, total_heat_loss):
        project_id=cem.project_id
        connections = [(conn.from_component, conn.to_component) for net in nets for conn in net.connections
                       if conn.from_component != "PANEL_ROOT" and conn.to_component != "PANEL_ROOT"]
        plate_cfg = self.panel_assembly.layout_config(enclosure, self.layout_config)
        try:
            placement = CPSATPlacementOptimizer(plate_cfg).solve(
                components, enclosure.width, enclosure.height, connections)
        except RuntimeError as exc:
            raise DesignError("PLACEMENT_ENGINE_UNAVAILABLE", "The placement solver is unavailable.",
                              {"reason": str(exc)}) from exc
        if not placement.feasible:
            raise DesignError("PLACEMENT_INFEASIBLE", "Selected components cannot be placed in the selected enclosure.",
                              {"enclosure_id": enclosure.id, "solver_status": placement.status,
                               "reason": placement.message})
        if placement.violations:
            raise DesignError("PLACEMENT_INVALID", "The placement solver returned geometry that fails its independent checks.",
                              {"violations": placement.violations})

        ducts = self.panel_assembly.ducts(placement, enclosure, plate_cfg)
        try:
            routes = DuctRouter(plate_cfg).route_layout(
                placement, nets, enclosure.width, enclosure.height, enclosure.depth, ducts=ducts)
        except RoutePlanningError as exc:
            raise DesignError("ROUTING_INFEASIBLE", "An electrical connection could not be routed.",
                              {"connection_id": exc.connection_id, "net_id": exc.net_id,
                               "reason": exc.reason}) from exc
        expected_routes = sum(len(net.connections) for net in nets)
        if len(routes) != expected_routes:
            routed = {route.id.removeprefix("ROUTE-") for route in routes}
            missing = [conn.id for net in nets for conn in net.connections
                       if conn.id not in routed]
            raise DesignError("ROUTING_INFEASIBLE", "One or more electrical connections could not be routed: " + ", ".join(missing),
                              {"missing_connection_ids": missing})

        pdm = PhysicalDesignModel(
            id=f"PDM-{project_id}", project_id=project_id, panel_id=cem.panel_id,
            enclosure_id=enclosure.id, enclosure_width=enclosure.width,
            enclosure_height=enclosure.height, enclosure_depth=enclosure.depth,
            ip_rating=enclosure.ip_rating,
            mounting_plate_x=enclosure.mounting_plate_offset_x,
            mounting_plate_y=enclosure.mounting_plate_offset_y,
            mounting_plate_z=enclosure.mounting_plate_offset_z,
            mounting_plate_width=enclosure.mounting_plate_width,
            mounting_plate_height=enclosure.mounting_plate_height,
            zones=enclosure.zones,
            components=placement.components, rails=placement.rails, routes=routes,
            ducts=ducts, construction=self.panel_assembly.parameters('PANEL_SHELL_STEEL'),
            total_heat_loss_watts=total_heat_loss,
            validation_policy=DesignValidationPolicy.from_layout(plate_cfg),
        )
        pdm.accessories = self.panel_assembly.accessories(pdm)
        from app.services.panel_geometry import component_geometry
        for part in pdm.components:
            part.geometry = component_geometry(part)
        violations = self.validation_engine.validate_pdm(pdm, cem, plate_cfg)
        pdm.validation_results = violations
        if violations:
            raise DesignError("PHYSICAL_VALIDATION_FAILED", "The generated physical design does not satisfy all physical constraints.",
                              {"violations": [v.model_dump() for v in violations]})
        from app.services.wire_geometry import build_wire_geometry
        for route in pdm.routes:
            try:
                route.geometry=build_wire_geometry(route,pdm)
                route.validation_checks=route.geometry.checks
            except ValueError as exc:
                raise DesignError('ROUTING_INFEASIBLE','Wire geometry validation failed.',
                    {'route_id':route.id,'reason':str(exc)}) from exc
        return pdm,violations
