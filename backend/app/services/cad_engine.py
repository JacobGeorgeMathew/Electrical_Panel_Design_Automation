from typing import Any, Dict, List
import math
from app.models.pdm import PhysicalDesignModel


class CADEngine:
    """Parametric geometry builder generating lightweight 3D geometry representation and STEP export hooks."""

    def generate_parametric_geometry(self, pdm: PhysicalDesignModel) -> Dict[str, Any]:
        mesh_primitives = []

        # 1. Enclosure Outer Shell Mesh
        mesh_primitives.append({
            "id": "CAD-ENCLOSURE",
            "type": "BOX",
            "name": f"Enclosure {pdm.enclosure_width}x{pdm.enclosure_height}x{pdm.enclosure_depth}",
            "position": {"x": pdm.enclosure_width / 2.0, "y": pdm.enclosure_height / 2.0, "z": pdm.enclosure_depth / 2.0},
            "dimensions": {"width": pdm.enclosure_width, "height": pdm.enclosure_height, "depth": pdm.enclosure_depth},
            "color": "#1E293B",
            "opacity": 0.25,
            "wireframe": True
        })

        # 2. Mounting Backplate Mesh
        mesh_primitives.append({
            "id": "CAD-BACKPLATE",
            "type": "BOX",
            "name": "Galvanized Steel Mounting Plate",
            "position": {"x": pdm.mounting_plate_x + (pdm.mounting_plate_width or pdm.enclosure_width - 60) / 2.0,
                         "y": pdm.mounting_plate_y + (pdm.mounting_plate_height or pdm.enclosure_height - 60) / 2.0,
                         "z": pdm.mounting_plate_z + 1.5},
            "dimensions": {"width": pdm.mounting_plate_width or pdm.enclosure_width - 60,
                           "height": pdm.mounting_plate_height or pdm.enclosure_height - 60, "depth": 3.0},
            "color": "#94A3B8",
            "opacity": 0.9,
            "wireframe": False
        })

        # 3. DIN Rails
        for rail in pdm.rails:
            mesh_primitives.append({
                "id": f"CAD-{rail.id}",
                "type": "BOX",
                "name": rail.label,
                "position": {"x": rail.x + rail.length / 2.0, "y": rail.y + rail.profile_height / 2.0, "z": rail.z + rail.profile_depth / 2.0},
                "dimensions": {"width": rail.length, "height": rail.profile_height, "depth": rail.profile_depth},
                "color": "#CBD5E1",
                "opacity": 1.0,
                "wireframe": False
            })

        # 4. Component 3D Primitives
        for comp in pdm.components:
            mesh_primitives.append({
                "id": f"CAD-{comp.id}",
                "type": "BOX",
                "name": comp.name,
                "position": {
                    "x": comp.position.x + comp.width / 2.0,
                    "y": comp.position.y + comp.height / 2.0,
                    "z": comp.position.z + comp.depth / 2.0
                },
                "dimensions": {"width": comp.width, "height": comp.height, "depth": comp.depth},
                "color": comp.color_hex,
                "opacity": 0.95,
                "wireframe": False,
                "category": comp.category,
                "pdm_component_id": comp.id,
                "cem_component_id": comp.cem_component_id,
                "heat_loss_watts": comp.heat_loss_watts,
                "rotation_xyzw": [0, 0, math.sin(math.radians(comp.rotation_deg) / 2), math.cos(math.radians(comp.rotation_deg) / 2)]
            })

        # 5. Wire Route Primitives (Polyline Tubes)
        for route in pdm.routes:
            points = [{"x": wp.x, "y": wp.y, "z": wp.z} for wp in route.waypoints]
            mesh_primitives.append({
                "id": f"CAD-{route.id}",
                "type": "TUBE",
                "name": f"Wire {route.net_name}",
                "route_id": route.id,
                "net_id": route.net_id,
                "points": points,
                "radius": 3.0 if route.wire_class == "POWER" else 1.5,
                "color": route.color_hex,
                "opacity": 0.85
            })

        return {
            "panel_id": pdm.panel_id,
            "units": "mm",
            "primitives": mesh_primitives
        }

    def export_freecad_script(self, pdm: PhysicalDesignModel) -> str:
        """Generates standalone Python script executable in FreeCAD for STEP/IGES file creation."""
        script = [
            "# Auto-generated FreeCAD Parametric CAD Export Script",
            "import FreeCAD as App",
            "import Part",
            "doc = App.newDocument('ElectricalPanel')",
            f"box = Part.makeBox({pdm.enclosure_width}, {pdm.enclosure_height}, {pdm.enclosure_depth})",
            "doc.addObject('Part::Feature', 'Enclosure').Shape = box",
        ]
        plate_w = pdm.mounting_plate_width or pdm.enclosure_width - 60
        plate_h = pdm.mounting_plate_height or pdm.enclosure_height - 60
        plate = f"Plate-{pdm.panel_id}".replace("-", "_")
        script.extend([
            f"plate = Part.makeBox({plate_w}, {plate_h}, 3)",
            f"plate.translate(App.Vector({pdm.mounting_plate_x}, {pdm.mounting_plate_y}, {pdm.mounting_plate_z}))",
            f"doc.addObject('Part::Feature', '{plate}').Shape = plate",
        ])
        for rail in pdm.rails:
            name = f"Rail-{rail.id}".replace("-", "_")
            script.append(f"rail = Part.makeBox({rail.length}, {rail.profile_height}, {rail.profile_depth})")
            script.append(f"rail.translate(App.Vector({rail.x}, {rail.y}, {rail.z}))")
            script.append(f"doc.addObject('Part::Feature', '{name}').Shape = rail")
        for comp in pdm.components:
            script.append(f"# Component: {comp.name}")
            script.append(f"comp_box = Part.makeBox({comp.width}, {comp.height}, {comp.depth})")
            if comp.rotation_deg:
                script.append(f"comp_box.rotate(App.Vector({comp.width/2}, {comp.height/2}, {comp.depth/2}), App.Vector(0, 0, 1), {comp.rotation_deg})")
            script.append(f"comp_box.translate(App.Vector({comp.position.x}, {comp.position.y}, {comp.position.z}))")
            safe_id = comp.id.replace("-", "_")
            script.append(f"doc.addObject('Part::Feature', '{safe_id}').Shape = comp_box")

        for route in pdm.routes:
            safe_id = route.id.replace("-", "_")
            if len(route.waypoints) >= 2:
                points = ", ".join(f"App.Vector({p.x}, {p.y}, {p.z})" for p in route.waypoints)
                script.append(f"route_points = [{points}]")
                script.append("route_edges = [Part.makeLine(route_points[i], route_points[i + 1]) for i in range(len(route_points) - 1)]")
                script.append(f"doc.addObject('Part::Feature', 'Wire_{safe_id}').Shape = Part.makeCompound(route_edges)")

        script.append("doc.recompute()")
        script.append("Part.export(doc.Objects, 'panel_model.step')")
        return "\n".join(script)
