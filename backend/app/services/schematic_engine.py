from typing import Any, Dict, List
from app.models.cem import ComponentRef, NetRef


class SchematicEngine:
    """Generates structured SVG schematic layout representations."""

    def generate_schematic_data(self, components: List[ComponentRef], nets: List[NetRef]) -> Dict[str, Any]:
        symbols = []
        wires = []

        # 1. Sugiyama/Hierarchical Grouping into Vertical Layers
        # Layer 1 (y=50): Panel Incomer MCCB
        # Layer 2 (y=180): SPD (left) & Main Busbar (center)
        # Layer 3 (y=320): Outgoing MCBs (horizontal row)
        # Layer 4 (y=460): Neutral / Earth Bars
        # Layer 5 (y=580): Outgoing Terminal Strip

        comp_dict = {c.id: c for c in components}
        incomer = comp_dict.get("QF001")
        busbar = comp_dict.get("BUS001")
        spd = comp_dict.get("SPD001")
        nbar = comp_dict.get("NBAR01")
        pebar = comp_dict.get("PEBAR01")

        canvas_width = 1200
        canvas_height = 700

        if incomer:
            symbols.append({
                "id": incomer.id,
                "name": incomer.name,
                "category": incomer.category,
                "type": "MCCB",
                "x": canvas_width / 2 - 50,
                "y": 50,
                "width": 100,
                "height": 70,
                "label": f"{incomer.id}\n{incomer.current_rating}A 3P",
                "terminals": [
                    {"id": "L1_IN", "x": canvas_width / 2 - 30, "y": 50},
                    {"id": "L2_IN", "x": canvas_width / 2, "y": 50},
                    {"id": "L3_IN", "x": canvas_width / 2 + 30, "y": 50},
                    {"id": "L1_OUT", "x": canvas_width / 2 - 30, "y": 120},
                    {"id": "L2_OUT", "x": canvas_width / 2, "y": 120},
                    {"id": "L3_OUT", "x": canvas_width / 2 + 30, "y": 120}
                ]
            })

        if busbar:
            symbols.append({
                "id": busbar.id,
                "name": busbar.name,
                "category": busbar.category,
                "type": "BUSBAR",
                "x": 200,
                "y": 180,
                "width": 800,
                "height": 30,
                "label": f"MAIN BUSBAR SYSTEM {busbar.current_rating}A (L1, L2, L3, N)",
                "terminals": [
                    {"id": "IN_L1", "x": canvas_width / 2 - 30, "y": 180},
                    {"id": "IN_L2", "x": canvas_width / 2, "y": 180},
                    {"id": "IN_L3", "x": canvas_width / 2 + 30, "y": 180}
                ]
            })

        if spd:
            symbols.append({
                "id": spd.id,
                "name": spd.name,
                "category": spd.category,
                "type": "SPD",
                "x": 80,
                "y": 180,
                "width": 80,
                "height": 60,
                "label": "SPD Type 2",
                "terminals": [{"id": "L1", "x": 120, "y": 180}]
            })

        # MCBs in Layer 3 (y=320)
        mcbs = [c for c in components if c.category == "MCB"]
        mcb_start_x = 100
        mcb_spacing = max(50, (canvas_width - 200) / max(1, len(mcbs)))

        for i, mcb in enumerate(mcbs):
            m_x = mcb_start_x + i * mcb_spacing
            symbols.append({
                "id": mcb.id,
                "name": mcb.name,
                "category": mcb.category,
                "type": "MCB",
                "x": m_x,
                "y": 320,
                "width": 36,
                "height": 60,
                "label": f"{mcb.id}\n{mcb.current_rating}A",
                "terminals": [
                    {"id": "IN", "x": m_x + 18, "y": 320},
                    {"id": "OUT", "x": m_x + 18, "y": 380}
                ]
            })

        # Terminals in Layer 5 (y=560)
        terms = [c for c in components if c.category == "TERMINAL"]
        for i, term in enumerate(terms):
            t_x = mcb_start_x + i * mcb_spacing
            symbols.append({
                "id": term.id,
                "name": term.name,
                "category": term.category,
                "type": "TERMINAL",
                "x": t_x,
                "y": 540,
                "width": 30,
                "height": 40,
                "label": term.id,
                "terminals": [
                    {"id": "LEFT", "x": t_x + 15, "y": 540},
                    {"id": "RIGHT", "x": t_x + 15, "y": 580}
                ]
            })

        if nbar:
            symbols.append({
                "id": nbar.id,
                "name": nbar.name,
                "category": nbar.category,
                "type": "BAR",
                "x": 100,
                "y": 450,
                "width": 450,
                "height": 20,
                "label": "NEUTRAL BAR (N)",
                "terminals": [{"id": "MAIN_N", "x": 325, "y": 450}]
            })

        if pebar:
            symbols.append({
                "id": pebar.id,
                "name": pebar.name,
                "category": pebar.category,
                "type": "BAR",
                "x": 600,
                "y": 450,
                "width": 450,
                "height": 20,
                "label": "EARTH BAR (PE)",
                "terminals": [{"id": "MAIN_PE", "x": 825, "y": 450}]
            })

        # Generate Orthogonal SVG Wire Paths
        sym_map = {s["id"]: s for s in symbols}

        for net in nets:
            for conn in net.connections:
                from_sym = sym_map.get(conn.from_component)
                to_sym = sym_map.get(conn.to_component)

                if from_sym and to_sym:
                    # Compute orthogonal path coordinates
                    x1 = from_sym["x"] + from_sym["width"] / 2
                    y1 = from_sym["y"] + from_sym["height"]
                    x2 = to_sym["x"] + to_sym["width"] / 2
                    y2 = to_sym["y"]

                    # Orthogonal routing: M x1 y1 -> V (y1+y2)/2 -> H x2 -> V y2
                    mid_y = (y1 + y2) / 2
                    svg_path = f"M {x1} {y1} V {mid_y} H {x2} V {y2}"

                    wires.append({
                        "id": conn.id,
                        "net_id": net.id,
                        "net_name": net.name,
                        "from": conn.from_component,
                        "to": conn.to_component,
                        "wire_class": conn.wire_class,
                        "svg_path": svg_path,
                        "color": "#EF4444" if conn.wire_class == "POWER" else ("#3B82F6" if conn.wire_class == "NEUTRAL" else "#10B981")
                    })

        return {
            "width": canvas_width,
            "height": canvas_height,
            "symbols": symbols,
            "wires": wires
        }
