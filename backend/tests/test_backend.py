import json
import pytest

from app.models.cem import CEMState
from app.models.cem import ConnectionRef, NetRef
from app.models.pdm import PhysicalComponent, Position3D, PhysicalDesignModel, Waypoint3D, WireRoute
from app.algorithms.jps_theta_star import JPSThetaStarRouter, RoutePlanningError
from app.algorithms.layout_config import LayoutConfig
from app.repositories.enclosure_repository import EnclosureRepository
from app.services.change_propagation import ChangePropagationEngine
from app.services.component_selector import ComponentSelector
from app.services.design_errors import DesignError
from app.services.orchestrator import DesignOrchestrator
from app.services.requirement_engine import RequirementEngine


VALID_DB = {
    "supply_voltage": 415,
    "phases": 3,
    "frequency": 50,
    "incomer_rating": 250,
    "num_feeders": 12,
    "ip_rating": "IP54",
    "spare_capacity_pct": 20,
    "neutral_required": True,
}


def test_requirement_engine_checks_types_options_and_integer_fields():
    engine = RequirementEngine()
    questions = engine.get_questions("DB")
    assert len(questions) > 0

    valid = engine.validate_requirements("TEST_001", "DB", VALID_DB)
    assert valid.is_valid

    invalid = engine.validate_requirements("TEST_001", "DB", {
        **VALID_DB, "supply_voltage": "415", "phases": 2, "num_feeders": 12.5,
        "unexpected": True,
    })
    assert not invalid.is_valid
    assert any("Supply Voltage" in error for error in invalid.validation_errors)
    assert any("Phases" in error for error in invalid.validation_errors)
    assert any("whole number" in error for error in invalid.validation_errors)
    assert any("Unknown requirement" in error for error in invalid.validation_errors)
    with pytest.raises(DesignError) as unsupported:
        engine.get_questions("MCC")
    assert unsupported.value.code == "UNSUPPORTED_ARCHETYPE"


def test_requirement_engine_reports_missing_required_and_out_of_range_fields():
    engine = RequirementEngine()
    missing = engine.validate_requirements("TEST_001", "DB", {**VALID_DB, "incomer_rating": None})
    assert not missing.is_valid
    assert any("Incomer Current Rating" in error and "required" in error for error in missing.validation_errors)

    out_of_range = engine.validate_requirements("TEST_001", "DB", {**VALID_DB, "num_feeders": 60})
    assert not out_of_range.is_valid
    assert any("Number of Feeders" in error and "48" in error for error in out_of_range.validation_errors)


def test_requirement_engine_flags_cross_field_risk_and_marks_conditional_field_not_applicable():
    engine = RequirementEngine()
    risk = engine.validate_requirements("TEST_001", "DB", {**VALID_DB, "incomer_rating": 100, "num_feeders": 20})
    assert risk.is_valid
    assert any("may be undersized" in warning for warning in risk.validation_warnings)

    single_phase = engine.validate_requirements("TEST_001", "DB", {**VALID_DB, "phases": 1, "neutral_required": True})
    neutral = next(item for item in single_phase.items if item.id == "neutral_required")
    assert neutral.value is None
    assert neutral.message == "Not applicable for current selection"


def test_calculation_engine_marks_estimates_without_compliance_claims():
    orch = DesignOrchestrator()
    results = orch.calc_engine.calculate_db_parameters(VALID_DB)
    assert len(results) >= 6
    capacity = next(r for r in results if r.type == "total_capacity")
    assert capacity.value > 100.0
    voltage_drop = next(r for r in results if r.type == "voltage_drop")
    assert "not a standards compliance determination" in voltage_drop.notes


def test_enclosure_repository_does_not_fallback_to_infeasible_or_lower_ip(tmp_path):
    path = tmp_path / "enclosures.json"
    path.write_text(json.dumps([
        {"id": "small", "width": 300, "height": 400, "mounting_plate_width": 250,
         "mounting_plate_height": 350, "max_thermal_dissipation": 20, "ip_rating": "IP54"}
    ]), encoding="utf-8")
    repo = EnclosureRepository(str(path))
    assert repo.find_best_fit(500, 500, 10, "IP54") is None
    assert repo.find_best_fit(100, 100, 10, "IP65") is None


def test_component_selection_rejects_unsupported_incomer_and_way_capacity():
    selector = ComponentSelector()
    with pytest.raises(DesignError) as no_incomer:
        selector.select_components(700, 12, 3, True, busbar_rating=875)
    assert no_incomer.value.code == "NO_FEASIBLE_COMPONENT"
    with pytest.raises(DesignError) as over_capacity:
        selector.select_components(250, 25, 3, True, busbar_rating=312)
    assert over_capacity.value.code == "NO_FEASIBLE_COMPONENT"


def test_pipeline_uses_consistent_cem_pdm_schematic_routes_bom_and_cad_ids():
    result = DesignOrchestrator().generate_design("TEST_PROJ_001")
    cem, pdm = result["cem"], result["pdm"]
    assert cem["state"] == CEMState.FINAL_VALIDATED.value
    assert cem["electrical_graph"]["project_id"] == cem["project_id"]
    assert cem["physical_design_id"] == pdm["id"]
    assert {component["id"] for component in cem["components"]} == {
        component["cem_component_id"] for component in pdm["components"]
    }
    assert len({net["id"] for net in cem["nets"]}) == len(cem["nets"])
    connection_ids = {connection["id"] for net in cem["nets"] for connection in net["connections"]}
    assert {wire["id"] for wire in result["schematic"]["wires"]} == connection_ids
    assert {route["id"] for route in pdm["routes"]} == {f"ROUTE-{connection_id}" for connection_id in connection_ids}
    assert {symbol["id"] for symbol in result["schematic"]["symbols"]} >= {
        component["id"] for component in cem["components"]
    }
    assert {item["component_id"] for item in result["bom"]} == (
        {component["id"] for component in cem["components"]} |
        {item['id'] for group in ('accessories','ducts','rails') for item in pdm[group]})
    cad_components = {primitive["cem_component_id"] for primitive in result["cad"]["primitives"]
                      if primitive.get("cem_component_id")}
    assert cad_components == {component["id"] for component in cem["components"]}
    cad_by_component = {primitive["cem_component_id"]: primitive for primitive in result["cad"]["primitives"]
                        if primitive.get("cem_component_id")}
    for component in pdm["components"]:
        primitive = cad_by_component[component["cem_component_id"]]
        assert primitive["position"] == {
            "x": component["position"]["x"] + component["width"] / 2,
            "y": component["position"]["y"] + component["height"] / 2,
            "z": component["position"]["z"] + component["depth"] / 2,
        }
    cad_route_ids = {primitive["route_id"] for primitive in result["cad"]["primitives"] if primitive.get("route_id")}
    assert cad_route_ids == {route["id"] for route in pdm["routes"]}
    cad_by_route = {primitive["route_id"]: primitive for primitive in result["cad"]["primitives"]
                    if primitive.get("route_id")}
    for route in pdm["routes"]:
        assert cad_by_route[route["id"]]["points"] == route["waypoints"]
    assert not any(v["severity"] == "CRITICAL" for v in pdm["validation_results"])
    assert len(pdm["routes"]) == len(connection_ids)
    placed = {component["cem_component_id"]: component for component in pdm["components"]}
    cem_components = {component["id"]: component for component in cem["components"]}
    for route in pdm["routes"]:
        if route["from_component"] != "PANEL_ROOT":
            source = placed[route["from_component"]]
            terminal = next(t for t in cem_components[route["from_component"]]["terminals"]
                            if t["id"] == route["from_terminal"])
            assert (route["waypoints"][0]["x"], route["waypoints"][0]["y"], route["waypoints"][0]["z"]) == (
                round(source["position"]["x"] + terminal["x"], 1),
                round(source["position"]["y"] + terminal["y"], 1),
                round(source["position"]["z"] + terminal["z"], 1))
        if route["to_component"] != "PANEL_ROOT":
            target = placed[route["to_component"]]
            terminal = next(t for t in cem_components[route["to_component"]]["terminals"]
                            if t["id"] == route["to_terminal"])
            assert (route["waypoints"][-1]["x"], route["waypoints"][-1]["y"], route["waypoints"][-1]["z"]) == (
                round(target["position"]["x"] + terminal["x"], 1),
                round(target["position"]["y"] + terminal["y"], 1),
                round(target["position"]["z"] + terminal["z"], 1))


def _router_component(component_id, x, y, width=20, height=20, terminals=None):
    return PhysicalComponent(
        id=f"PDM-{component_id}", cem_component_id=component_id, name=component_id,
        category="TEST", position=Position3D(x=x, y=y, z=10), width=width, height=height,
        depth=20, zone_name="TEST", heat_loss_watts=0, cad_model="test",
        terminals=terminals or [{"id": "T", "x": width / 2, "y": height / 2, "z": 10}],
    )


def _test_net(from_id="SRC", to_id="DST"):
    connection = ConnectionRef(id="C1", from_component=from_id, from_terminal="T",
                               to_component=to_id, to_terminal="T", net_id="N1", wire_class="CONTROL")
    return NetRef(id="N1", name="Test control", voltage_level=24, wire_class="CONTROL", connections=[connection])


def test_router_routes_from_exact_terminals_around_component_obstacle():
    source = _router_component("SRC", 20, 45)
    target = _router_component("DST", 120, 45)
    obstacle = _router_component("OBSTACLE", 65, 25, width=20, height=60)
    router = JPSThetaStarRouter(LayoutConfig(grid_mm=5, wire_clearance=5))
    route = router.route_nets([_test_net()], [source, target, obstacle], [], 160, 120, 60)[0]

    assert route.from_component == "SRC" and route.to_component == "DST"
    assert route.wire_class == "CONTROL"
    assert route.waypoints[0].x == 30 and route.waypoints[0].y == 55 and route.waypoints[0].z == 20
    assert route.waypoints[-1].x == 130 and route.waypoints[-1].y == 55 and route.waypoints[-1].z == 20
    assert all(0 <= point.x <= 160 and 0 <= point.y <= 120 and 0 <= point.z <= 60 for point in route.waypoints)
    assert any(point.y < 20 or point.y > 90 for point in route.waypoints)


def test_router_returns_structured_error_for_missing_terminal_or_blocked_route():
    router = JPSThetaStarRouter(LayoutConfig(grid_mm=5, wire_clearance=5))
    source = _router_component("SRC", 20, 45)
    target = _router_component("DST", 120, 45)
    missing_terminal = _test_net()
    missing_terminal.connections[0].from_terminal = "MISSING"
    with pytest.raises(RoutePlanningError) as missing:
        router.route_nets([missing_terminal], [source, target], [], 160, 120, 60)
    assert missing.value.connection_id == "C1"
    assert "Terminal 'MISSING'" in missing.value.reason

    wall = _router_component("WALL", 70, 0, width=20, height=120)
    with pytest.raises(RoutePlanningError) as impossible:
        router.route_nets([_test_net()], [source, target, wall], [], 160, 120, 60)
    assert impossible.value.net_id == "N1"
    assert "No collision-free path" in impossible.value.reason


def test_physical_validator_flags_overlapping_and_out_of_plate_placement():
    first = _router_component("A", 10, 10)
    overlapping = _router_component("B", 15, 15)
    outside = _router_component("C", 90, 90)
    pdm = PhysicalDesignModel(id="PDM-T", project_id="T", panel_id="T", enclosure_id="E",
        enclosure_width=100, enclosure_height=100, enclosure_depth=60, ip_rating="IP54",
        mounting_plate_x=0, mounting_plate_y=0, mounting_plate_width=80, mounting_plate_height=80,
        components=[first, overlapping, outside])
    violations = DesignOrchestrator().validation_engine.validate_pdm(pdm)
    assert any(v.type == "OVERLAP" and v.object_a == "PDM-A" and v.object_b == "PDM-B" for v in violations)
    assert any(v.type == "BOUNDARY" and v.object_a == "PDM-C" for v in violations)


def test_physical_validator_flags_wrong_route_terminal_and_obstacle_clearance():
    source = _router_component("SRC", 10, 10)
    obstacle = _router_component("OBSTACLE", 40, 10)
    target = _router_component("DST", 70, 10)
    route = WireRoute(id="ROUTE-C1", net_id="N1", net_name="test", from_component="SRC", from_terminal="T",
        to_component="DST", to_terminal="T", wire_class="CONTROL",
        waypoints=[Waypoint3D(x=10, y=20, z=20), Waypoint3D(x=80, y=20, z=20)],
        length_mm=70, bend_count=0)
    pdm = PhysicalDesignModel(id="PDM-T", project_id="T", panel_id="T", enclosure_id="E",
        enclosure_width=100, enclosure_height=100, enclosure_depth=60, ip_rating="IP54",
        mounting_plate_width=100, mounting_plate_height=100,
        components=[source, obstacle, target], routes=[route])
    violations = DesignOrchestrator().validation_engine.validate_pdm(pdm)
    assert any(v.type == "TERMINAL" and v.object_a == route.id for v in violations)
    assert any(v.type == "ROUTE_CLEARANCE" and v.object_a == route.id and v.object_b == obstacle.id for v in violations)


def test_invalid_generation_is_structured_and_does_not_persist_requirements():
    orch = DesignOrchestrator()
    before = orch.project_repo.get_by_id("PROJ_DB_DEMO_001")["requirements"].copy()
    with pytest.raises(DesignError) as raised:
        orch.generate_design("PROJ_DB_DEMO_001", {"num_feeders": 100})
    assert raised.value.code == "INVALID_REQUIREMENTS"
    assert orch.project_repo.get_by_id("PROJ_DB_DEMO_001")["requirements"] == before


def test_change_diff_reports_actual_field_values_and_stages():
    engine = ChangePropagationEngine()
    old = {"components": [{"category": "MCB"}], "nets": []}
    new = {"components": [{"category": "MCB"}, {"category": "MCB"}], "nets": []}
    report = engine.compute_diff(old, new, {}, {}, "num_feeders", {"num_feeders": 1}, {"num_feeders": 2})
    assert report["modified_field"] == "num_feeders"
    assert "COMPONENT_SELECTION" in report["affected_stages"]
    requirement_diff = report["diffs"][0]
    assert (requirement_diff["before"], requirement_diff["after"], requirement_diff["changed"]) == ("1", "2", True)


# Database-backed HTTP lifecycle/propagation tests live in test_postgres.py.


def test_validate_placement_endpoint_checks_the_submitted_pdm_and_project_identity():
    from app.api import routes_design
    from app.models.pdm import PhysicalComponent, PhysicalDesignModel, Position3D

    pdm = PhysicalDesignModel(
        id="PDM-EDIT-01", project_id="PROJECT-01", panel_id="DB-01", enclosure_id="ENC-01",
        enclosure_width=200, enclosure_height=200, enclosure_depth=100, ip_rating="IP54",
        mounting_plate_x=20, mounting_plate_y=20, mounting_plate_width=160, mounting_plate_height=160,
        components=[PhysicalComponent(id="PDM-QF001", cem_component_id="QF001", name="Incomer",
            category="MCCB", position=Position3D(x=-10, y=40, z=10), width=40, height=60, depth=40,
            zone_name="POWER", heat_loss_watts=1, cad_model="demo")],
    )
    result = routes_design.validate_placement("PROJECT-01", pdm)
    assert result["pdm"]["components"][0]["position"]["x"] == -10
    assert any(item["type"] == "BOUNDARY" and item["severity"] == "CRITICAL"
               for item in result["validation_results"])
    with pytest.raises(DesignError) as mismatch:
        routes_design.validate_placement("OTHER-PROJECT", pdm)
    assert mismatch.value.code == "PROJECT_MISMATCH"
