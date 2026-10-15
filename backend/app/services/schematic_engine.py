from typing import Any, Dict, List
from app.models.cem import CanonicalEngineeringModel


class SchematicEngine:
    """Generates structured SVG schematic layout representations."""

    def generate_schematic_data(self, cem: CanonicalEngineeringModel) -> Dict[str, Any]:
        symbols = []
        wires = []
        components, nets = cem.components, cem.nets

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

        symbols.append({"id": "PANEL_ROOT", "name": cem.panel_id, "category": "PANEL", "type": "PANEL",
                        "x": 20, "y": 20, "width": 40, "height": 30, "label": cem.panel_id,
                        "terminals": [{"id": "EARTH_STUD", "x": 40, "y": 35}]})

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
                    {"id": "IN_L3", "x": canvas_width / 2 + 30, "y": 180},
                    {"id": "IN_N", "x": canvas_width / 2 + 60, "y": 180}
                ]
            })

        if spd:
            spd_terminals = []
            for terminal in spd.terminals:
                spd_terminals.append({"id": terminal["id"],
                                      "x": 80 + 80 * float(terminal.get("x", spd.width / 2)) / max(1, spd.width),
                                      "y": 180 if float(terminal.get("y", 0)) > spd.height / 2 else 240})
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
                "terminals": spd_terminals
            })

        # MCBs in Layer 3 (y=320)
        mcbs = [c for c in components if c.category == "MCB"]
        mcb_start_x = 100
        mcb_spacing = (canvas_width - 200) / max(1, len(mcbs))
        mcb_symbol_width = min(36, max(12, mcb_spacing * 0.75))

        for i, mcb in enumerate(mcbs):
            m_x = mcb_start_x + i * mcb_spacing
            symbols.append({
                "id": mcb.id,
                "name": mcb.name,
                "category": mcb.category,
                "type": "MCB",
                "x": m_x,
                "y": 320,
                "width": mcb_symbol_width,
                "height": 60,
                "label": f"{mcb.id}\n{mcb.current_rating}A",
                "terminals": ([{"id": f"L{p}_IN", "x": m_x + mcb_symbol_width * p / 4, "y": 320}
                               for p in range(1, min(3, mcb.poles) + 1)] +
                              [{"id": f"L{p}_OUT", "x": m_x + mcb_symbol_width * p / 4, "y": 380}
                               for p in range(1, min(3, mcb.poles) + 1)] if mcb.poles > 1 else [
                                  {"id": "IN", "x": m_x + mcb_symbol_width / 2, "y": 320},
                                  {"id": "OUT", "x": m_x + mcb_symbol_width / 2, "y": 380}])
            })

        # Terminals in Layer 5 (y=560)
        terms = [c for c in components if c.category == "TERMINAL"]
        terminal_symbol_width = min(30, max(8, mcb_spacing * 0.75))
        for i, term in enumerate(terms):
            t_x = mcb_start_x + i * mcb_spacing
            symbols.append({
                "id": term.id,
                "name": term.name,
                "category": term.category,
                "type": "TERMINAL",
                "x": t_x,
                "y": 540,
                "width": terminal_symbol_width,
                "height": 40,
                "label": term.id,
                "terminals": [
                    {"id": "LEFT", "x": t_x + terminal_symbol_width / 2, "y": 540},
                    {"id": "RIGHT", "x": t_x + terminal_symbol_width / 2, "y": 580}
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
                    from_terminal = next((t for t in from_sym["terminals"] if t["id"] == conn.from_terminal), None)
                    to_terminal = next((t for t in to_sym["terminals"] if t["id"] == conn.to_terminal), None)
                    if from_terminal is None or to_terminal is None:
                        continue
                    x1, y1 = from_terminal["x"], from_terminal["y"]
                    x2, y2 = to_terminal["x"], to_terminal["y"]

                    # Orthogonal routing: M x1 y1 -> V (y1+y2)/2 -> H x2 -> V y2
                    mid_y = (y1 + y2) / 2
                    svg_path = f"M {x1} {y1} V {mid_y} H {x2} V {y2}"

                    wires.append({
                        "id": conn.id,
                        "net_id": net.id,
                        "net_name": net.name,
                        "from": conn.from_component,
                        "from_terminal": conn.from_terminal,
                        "to": conn.to_component,
                        "to_terminal": conn.to_terminal,
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
