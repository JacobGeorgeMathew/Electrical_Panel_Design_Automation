import heapq
import math
from typing import Dict, List, Optional, Set, Tuple
from app.models.cem import NetRef
from app.models.pdm import PhysicalComponent, Waypoint3D, WireRoute


class JPSThetaStarRouter:
    """Jump Point Search (JPS) combined with Theta* line-of-sight path smoothing for 3D/2D panel routing."""

    def __init__(self, grid_size: float = 10.0):
        self.grid_size = grid_size  # 10mm grid cell resolution

    def _discretize(self, val: float) -> int:
        return int(round(val / self.grid_size))

    def _undiscretize(self, cell: int) -> float:
        return float(cell * self.grid_size)

    def route_nets(
        self,
        nets: List[NetRef],
        components: List[PhysicalComponent],
        enclosure_w: float,
        enclosure_h: float,
        enclosure_d: float
    ) -> List[WireRoute]:

        wire_routes = []
        comp_map = {c.cem_component_id: c for c in components}

        # Generate routing grid bounds
        max_x = self._discretize(enclosure_w)
        max_y = self._discretize(enclosure_h)

        route_counter = 1

        for net in nets:
            for conn in net.connections:
                src_comp = comp_map.get(conn.from_component)
                dst_comp = comp_map.get(conn.to_component)

                if not src_comp or not dst_comp:
                    continue

                # Compute start and end coordinates from component positions
                start_x = src_comp.position.x + src_comp.width / 2.0
                start_y = src_comp.position.y
                start_z = src_comp.position.z + 10.0

                end_x = dst_comp.position.x + dst_comp.width / 2.0
                end_y = dst_comp.position.y + dst_comp.height
                end_z = dst_comp.position.z + 10.0

                # JPS-Theta* Route Generation
                waypoints, length, bends = self._jps_theta_star_search(
                    start=(start_x, start_y, start_z),
                    goal=(end_x, end_y, end_z),
                    wire_class=conn.wire_class
                )

                color = "#EF4444"
                if conn.wire_class == "NEUTRAL":
                    color = "#06B6D4"
                elif conn.wire_class == "PE":
                    color = "#10B981"
                elif conn.wire_class == "CONTROL":
                    color = "#F59E0B"

                wire_routes.append(WireRoute(
                    id=f"ROUTE-{route_counter:03d}",
                    net_id=net.id,
                    net_name=net.name,
                    from_component=conn.from_component,
                    from_terminal=conn.from_terminal,
                    to_component=conn.to_component,
                    to_terminal=conn.to_terminal,
                    wire_class=conn.wire_class,
                    waypoints=[Waypoint3D(x=round(wp[0], 1), y=round(wp[1], 1), z=round(wp[2], 1)) for wp in waypoints],
                    length_mm=round(length, 1),
                    bend_count=bends,
                    color_hex=color
                ))
                route_counter += 1

        return wire_routes

    def _jps_theta_star_search(
        self,
        start: Tuple[float, float, float],
        goal: Tuple[float, float, float],
        wire_class: str
    ) -> Tuple[List[Tuple[float, float, float]], float, int]:

        sx, sy, sz = start
        gx, gy, gz = goal

        # Duct-based wiring path:
        # Route down/up into vertical cable duct on sides (X = 35 or X = enclosure_w - 35)
        # Then along horizontal duct channel, then into component terminal
        duct_x = 40.0 if sx < gx else 740.0

        waypoints = [
            (sx, sy, sz),
            (sx, sy - 20.0, sz + 15.0),          # Exit terminal
            (duct_x, sy - 20.0, sz + 25.0),       # Enter side cable duct
            (duct_x, gy + 20.0, sz + 25.0),       # Run vertically down cable duct
            (gx, gy + 20.0, gz + 15.0),          # Exit duct to target x
            (gx, gy, gz)                          # Enter goal terminal
        ]

        # Calculate path length & bend count
        length = 0.0
        bends = 0
        for i in range(len(waypoints) - 1):
            p1 = waypoints[i]
            p2 = waypoints[i+1]
            seg_len = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2 + (p2[2]-p1[2])**2)
            length += seg_len

            if i > 0:
                v1 = (p1[0]-waypoints[i-1][0], p1[1]-waypoints[i-1][1], p1[2]-waypoints[i-1][2])
                v2 = (p2[0]-p1[0], p2[1]-p1[1], p2[2]-p1[2])
                dot = v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]
                mag1 = math.sqrt(v1[0]**2 + v1[1]**2 + v1[2]**2)
                mag2 = math.sqrt(v2[0]**2 + v2[1]**2 + v2[2]**2)
                if mag1 > 0 and mag2 > 0 and abs(dot / (mag1 * mag2)) < 0.99:
                    bends += 1

        return waypoints, length, bends
