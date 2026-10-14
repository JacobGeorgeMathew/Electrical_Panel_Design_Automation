from typing import Any, Dict, List
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
            "position": {"x": pdm.enclosure_width / 2.0, "y": pdm.enclosure_height / 2.0, "z": 10.0},
            "dimensions": {"width": pdm.enclosure_width - 60, "height": pdm.enclosure_height - 60, "depth": 3.0},
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
                "position": {"x": rail.x + rail.length / 2.0, "y": rail.y, "z": rail.z},
                "dimensions": {"width": rail.length, "height": 35.0, "depth": 7.5},
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
                "heat_loss_watts": comp.heat_loss_watts
            })

        # 5. Wire Route Primitives (Polyline Tubes)
        for route in pdm.routes:
            points = [{"x": wp.x, "y": wp.y, "z": wp.z} for wp in route.waypoints]
            mesh_primitives.append({
                "id": f"CAD-{route.id}",
                "type": "TUBE",
                "name": f"Wire {route.net_name}",
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
        for comp in pdm.components:
            script.append(f"# Component: {comp.name}")
            script.append(f"comp_box = Part.makeBox({comp.width}, {comp.height}, {comp.depth})")
            script.append(f"comp_box.translate(App.Vector({comp.position.x}, {comp.position.y}, {comp.position.z}))")
            script.append(f"doc.addObject('Part::Feature', '{comp.id}').Shape = comp_box")

        script.append("doc.recompute()")
        script.append("Part.export(doc.Objects, 'panel_model.step')")
        return "\n".join(script)
