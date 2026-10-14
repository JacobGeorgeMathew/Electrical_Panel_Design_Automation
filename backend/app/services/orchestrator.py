from typing import Any, Dict, Optional
from app.algorithms.cp_sat_placement import CPSATPlacementOptimizer
from app.algorithms.jps_theta_star import JPSThetaStarRouter
from app.models.cem import CEMState, CanonicalEngineeringModel
from app.models.pdm import PhysicalDesignModel
from app.repositories.component_repository import ComponentRepository
from app.repositories.enclosure_repository import EnclosureRepository
from app.repositories.project_repository import ProjectRepository
from app.services.cad_engine import CADEngine
from app.services.calculation_engine import CalculationEngine
from app.services.change_propagation import ChangePropagationEngine
from app.services.component_selector import ComponentSelector
from app.services.enclosure_engine import EnclosureEngine
from app.services.graph_engine import GraphEngine
from app.services.netlist_engine import NetlistEngine
from app.services.requirement_engine import RequirementEngine
from app.services.schematic_engine import SchematicEngine
from app.services.validation_engine import ValidationEngine
from app.services.zoning_engine import ZoningEngine


class DesignOrchestrator:
    """Central pipeline orchestrator executing full engineering panel generation."""

    def __init__(self):
        self.project_repo = ProjectRepository()
        self.comp_repo = ComponentRepository()
        self.enclosure_repo = EnclosureRepository()

        self.req_engine = RequirementEngine()
        self.calc_engine = CalculationEngine()
        self.comp_selector = ComponentSelector(self.comp_repo)
        self.graph_engine = GraphEngine()
        self.netlist_engine = NetlistEngine()
        self.schematic_engine = SchematicEngine()
        self.zoning_engine = ZoningEngine()
        self.enclosure_engine = EnclosureEngine(self.enclosure_repo)
        self.placement_optimizer = CPSATPlacementOptimizer()
        self.routing_router = JPSThetaStarRouter()
        self.validation_engine = ValidationEngine()
        self.cad_engine = CADEngine()
        self.change_prop_engine = ChangePropagationEngine()

    def generate_design(self, project_id: str, requirement_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        project = self.project_repo.get_by_id(project_id)
        if not project:
            # Create default project if missing
            project = {
                "id": project_id,
                "name": f"Panel Project {project_id}",
                "archetype": "DB",
                "requirements": {
                    "supply_voltage": 415,
                    "phases": 3,
                    "frequency": 50,
                    "incomer_rating": 250,
                    "num_feeders": 12,
                    "ip_rating": "IP54",
                    "spare_capacity_pct": 20,
                    "neutral_required": True
                }
            }

        req_values = project.get("requirements", {})
        if requirement_overrides:
            req_values.update(requirement_overrides)
            project["requirements"] = req_values
            self.project_repo.save(project)

        # Step 1: Validate Requirements
        req_set = self.req_engine.validate_requirements(project_id, "DB", req_values)

        # Step 2: Build Base CEM
        cem = CanonicalEngineeringModel(
            project_id=project_id,
            panel_id=f"DB-{project_id}",
            panel_type="DB",
            state=CEMState.REQUIREMENTS_VALIDATED,
            requirements=req_set.items
        )

        # Step 3: Run Engineering Calculations
        calc_results = self.calc_engine.calculate_db_parameters(req_values)
        cem.calculations = calc_results
        cem.state = CEMState.ENGINEERING_CALCULATED

        # Step 4: Select Components
        incomer_rating = req_values.get("incomer_rating", 250)
        num_feeders = req_values.get("num_feeders", 12)
        phases = req_values.get("phases", 3)

        components = self.comp_selector.select_components(incomer_rating, num_feeders, phases)
        cem.components = components
        cem.state = CEMState.COMPONENTS_SELECTED

        # Step 5: Build Electrical Graph
        graph = self.graph_engine.build_electrical_graph(project_id, components)

        # Step 6: Generate Netlist & Validate
        nets = self.netlist_engine.generate_netlist(graph)
        is_net_valid, net_errors = self.netlist_engine.validate_netlist(nets)
        cem.nets = nets
        cem.state = CEMState.NETLIST_VALIDATED

        # Step 7: Generate Schematic SVG Layout Model
        schematic_data = self.schematic_engine.generate_schematic_data(components, nets)
        cem.state = CEMState.SCHEMATIC_GENERATED

        # Step 8: Select Enclosure & Zoning
        total_comp_width = sum(c.width for c in components if c.category in ["MCCB", "MCB", "SPD", "BUSBAR"])
        total_heat_loss = sum(c.heat_loss for c in components)

        enclosure = self.enclosure_engine.select_enclosure(
            total_components_width=total_comp_width,
            total_heat_loss=total_heat_loss,
            ip_rating=req_values.get("ip_rating", "IP54")
        )

        zones = self.zoning_engine.get_default_zones(enclosure["width"], enclosure["height"])
        zones_map = {z.name: {"x_min": z.x_min, "x_max": z.x_max, "y_min": z.y_min, "y_max": z.y_max} for z in zones}

        # Step 9: CP-SAT Placement Optimization
        physical_components, rails = self.placement_optimizer.optimize_placement(
            components=components,
            enclosure_width=enclosure["width"],
            enclosure_height=enclosure["height"],
            enclosure_depth=enclosure["depth"],
            zones_map=zones_map
        )

        # Step 10: JPS-Theta* Wire Routing
        wire_routes = self.routing_router.route_nets(
            nets=nets,
            components=physical_components,
            enclosure_w=enclosure["width"],
            enclosure_h=enclosure["height"],
            enclosure_d=enclosure["depth"]
        )

        # Step 11: Build Physical Design Model (PDM)
        pdm = PhysicalDesignModel(
            id=f"PDM-{project_id}",
            project_id=project_id,
            panel_id=f"DB-{project_id}",
            enclosure_id=enclosure["id"],
            enclosure_width=enclosure["width"],
            enclosure_height=enclosure["height"],
            enclosure_depth=enclosure["depth"],
            ip_rating=enclosure["ip_rating"],
            zones=zones,
            components=physical_components,
            rails=rails,
            routes=wire_routes,
            total_heat_loss_watts=total_heat_loss
        )

        # Step 12: Validate Physical Design & Thermal
        violations = self.validation_engine.validate_pdm(pdm)
        pdm.validation_results = violations

        cem.physical_design_id = pdm.id
        cem.state = CEMState.FINAL_VALIDATED

        # Step 13: Generate CAD Primitives
        cad_data = self.cad_engine.generate_parametric_geometry(pdm)

        # Return full design package
        return {
            "cem": cem.model_dump(),
            "pdm": pdm.model_dump(),
            "schematic": schematic_data,
            "cad": cad_data,
            "validation_errors": [v.model_dump() for v in violations]
        }
