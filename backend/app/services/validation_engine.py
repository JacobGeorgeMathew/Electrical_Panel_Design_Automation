from typing import List, Tuple
from shapely.geometry import LineString, box
from app.algorithms.layout_config import LayoutConfig
from app.models.cem import CanonicalEngineeringModel
from app.models.pdm import PhysicalComponent, PhysicalDesignModel, ValidationViolation


class ValidationEngine:
    """Performs 2D computational geometry clearance, boundary containment, and thermal safety checks."""

    def validate_pdm(self, pdm: PhysicalDesignModel, cem: CanonicalEngineeringModel = None,
                     layout_config: LayoutConfig = None) -> List[ValidationViolation]:
        violations = []
        layout_config = layout_config or LayoutConfig()

        components = pdm.components
        enc_w = pdm.enclosure_width
        enc_h = pdm.enclosure_height

        # 1. Component Overlap & Clearance Checks
        boxes = []
        for c in components:
            poly = box(c.position.x, c.position.y, c.position.x + c.width, c.position.y + c.height)
            boxes.append((c, poly))

        for i in range(len(boxes)):
            c1, poly1 = boxes[i]

            # Boundary containment check
            plate_x0, plate_y0 = pdm.mounting_plate_x, pdm.mounting_plate_y
            plate_x1 = plate_x0 + (pdm.mounting_plate_width or enc_w - 2 * plate_x0)
            plate_y1 = plate_y0 + (pdm.mounting_plate_height or enc_h - 2 * plate_y0)
            if (c1.position.x < plate_x0 or c1.position.x + c1.width > plate_x1
                    or c1.position.y < plate_y0 or c1.position.y + c1.height > plate_y1):
                violations.append(ValidationViolation(
                    type="BOUNDARY",
                    severity="CRITICAL",
                    object_a=c1.id,
                    required_value=0,
                    actual_value=-1,
                    unit="mm",
                    message=f"Component {c1.name} ({c1.id}) exceeds panel enclosure boundary."
                ))

            for j in range(i + 1, len(boxes)):
                c2, poly2 = boxes[j]

                # Overlap check
                if poly1.intersects(poly2):
                    inter_area = poly1.intersection(poly2).area
                    if inter_area > 0.01:
                        violations.append(ValidationViolation(
                            type="OVERLAP",
                            severity="CRITICAL",
                            object_a=c1.id,
                            object_b=c2.id,
                            required_value=0.0,
                            actual_value=round(inter_area, 1),
                            unit="mm²",
                            message=f"Collision detected between {c1.name} and {c2.name}."
                        ))

                # Clearance distance check
                dist = poly1.distance(poly2)
                min_req = layout_config.device_gap_x if c1.rail_id and c2.rail_id else layout_config.plate_clearance
                if 0 < dist < min_req:
                    violations.append(ValidationViolation(
                        type="CLEARANCE",
                        severity="WARNING",
                        object_a=c1.id,
                        object_b=c2.id,
                        required_value=min_req,
                        actual_value=round(dist, 1),
                        unit="mm",
                        message=f"Clearance between {c1.id} and {c2.id} ({round(dist, 1)}mm) is less than required {min_req}mm."
                    ))

        # 2. Thermal Density Index Check
        thermal_index = pdm.total_heat_loss_watts / max(1.0, (enc_w * enc_h * pdm.enclosure_depth) / 1000000.0)
        pdm.thermal_density_index = round(thermal_index, 3)

        if thermal_index > 0.45:
            violations.append(ValidationViolation(
                type="THERMAL",
                severity="WARNING",
                object_a="ENCLOSURE",
                required_value=0.45,
                actual_value=round(thermal_index, 3),
                unit="W/L",
                message=f"High thermal load density ({round(thermal_index, 3)} W/L). Forced ventilation louvers recommended."
            ))

        component_ids = {component.cem_component_id for component in pdm.components}
        component_by_cem_id = {component.cem_component_id: component for component in pdm.components}
        if len({route.id for route in pdm.routes}) != len(pdm.routes):
            violations.append(ValidationViolation(type="IDENTITY", severity="CRITICAL", object_a="ROUTES",
                required_value=0, actual_value=len(pdm.routes) - len({route.id for route in pdm.routes}), unit="duplicates",
                message="Route IDs must be unique."))
        for route in pdm.routes:
            for endpoint in (route.from_component, route.to_component):
                if endpoint != "PANEL_ROOT" and endpoint not in component_ids:
                    violations.append(ValidationViolation(type="IDENTITY", severity="CRITICAL", object_a=route.id,
                        object_b=endpoint, required_value=1, actual_value=0, unit="references",
                        message=f"Route {route.id} references a component absent from the PDM."))
            for point in route.waypoints:
                if not (0 <= point.x <= enc_w and 0 <= point.y <= enc_h and 0 <= point.z <= pdm.enclosure_depth):
                    violations.append(ValidationViolation(type="BOUNDARY", severity="CRITICAL", object_a=route.id,
                        required_value=0, actual_value=-1, unit="mm", message=f"Route {route.id} leaves the enclosure bounds."))

            endpoint_components = []
            for side, component_id, terminal_id, waypoint in (
                ("from", route.from_component, route.from_terminal, route.waypoints[0] if route.waypoints else None),
                ("to", route.to_component, route.to_terminal, route.waypoints[-1] if route.waypoints else None),
            ):
                component = component_by_cem_id.get(component_id)
                endpoint_components.append(component)
                if component_id == "PANEL_ROOT":
                    continue
                terminal = next((t for t in component.terminals if t.get("id") == terminal_id), None) if component else None
                if terminal is None or waypoint is None:
                    violations.append(ValidationViolation(type="TERMINAL", severity="CRITICAL", object_a=route.id,
                        object_b=component_id, required_value=1, actual_value=0, unit="references",
                        message=f"Route {route.id} has no valid {side} terminal reference."))
                    continue
                expected = (component.position.x + float(terminal.get("x", component.width / 2)),
                            component.position.y + float(terminal.get("y", component.height / 2)),
                            component.position.z + float(terminal.get("z", component.depth / 2)))
                actual = (waypoint.x, waypoint.y, waypoint.z)
                deviation = max(abs(expected[i] - actual[i]) for i in range(3))
                if deviation > 0.11:
                    violations.append(ValidationViolation(type="TERMINAL", severity="CRITICAL", object_a=route.id,
                        object_b=component_id, required_value=0, actual_value=round(deviation, 2), unit="mm",
                        message=f"Route {route.id} does not begin or end at its declared {side} terminal."))

            if len(route.waypoints) >= 2:
                clearance = max(float(layout_config.wire_clearance), float(layout_config.grid_mm))
                last_segment = len(route.waypoints) - 2
                for index, (a, b) in enumerate(zip(route.waypoints, route.waypoints[1:])):
                    buffered_segment = LineString([(a.x, a.y), (b.x, b.y)]).buffer(clearance, cap_style="square")
                    for component in components:
                        if index == 0 and component is endpoint_components[0]:
                            continue
                        if index == last_segment and component is endpoint_components[1]:
                            continue
                        footprint = box(component.position.x, component.position.y,
                                        component.position.x + component.width,
                                        component.position.y + component.height)
                        if buffered_segment.intersects(footprint):
                            violations.append(ValidationViolation(type="ROUTE_CLEARANCE", severity="CRITICAL",
                                object_a=route.id, object_b=component.id, required_value=clearance,
                                actual_value=0, unit="mm", message=f"Route {route.id} violates wire clearance at {component.id}."))
                            break

        if cem is not None:
            cem_ids = {component.id for component in cem.components}
            pdm_ids = {component.cem_component_id for component in pdm.components}
            for missing in sorted(cem_ids - pdm_ids):
                violations.append(ValidationViolation(type="IDENTITY", severity="CRITICAL", object_a=missing,
                    required_value=1, actual_value=0, unit="components", message=f"CEM component {missing} has no PDM placement."))
            for extra in sorted(pdm_ids - cem_ids):
                violations.append(ValidationViolation(type="IDENTITY", severity="CRITICAL", object_a=extra,
                    required_value=0, actual_value=1, unit="components", message=f"PDM component {extra} has no CEM component."))
            route_by_connection = {route.id.removeprefix("ROUTE-"): route for route in pdm.routes}
            for net in cem.nets:
                for conn in net.connections:
                    route = route_by_connection.get(conn.id)
                    if route is None:
                        violations.append(ValidationViolation(type="IDENTITY", severity="CRITICAL", object_a=conn.id,
                            required_value=1, actual_value=0, unit="routes", message=f"CEM connection {conn.id} has no PDM route."))
                    elif (route.net_id != net.id or route.from_component != conn.from_component
                          or route.from_terminal != conn.from_terminal or route.to_component != conn.to_component
                          or route.to_terminal != conn.to_terminal):
                        violations.append(ValidationViolation(type="IDENTITY", severity="CRITICAL", object_a=route.id,
                            object_b=conn.id, required_value=1, actual_value=0, unit="references",
                            message=f"PDM route {route.id} does not match CEM connection {conn.id}."))

        return violations
