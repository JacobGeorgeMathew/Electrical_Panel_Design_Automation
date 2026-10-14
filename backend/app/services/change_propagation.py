from typing import Any, Dict, List, Set, Tuple


class ChangePropagationEngine:
    """Manages design dependency DAG and evaluates affected downstream stages when requirements change."""

    DEPENDENCY_DAG = {
        "supply_voltage": ["CALC_001", "CALC_006", "NETLIST", "SCHEMATIC"],
        "incomer_rating": ["CALC_001", "CALC_002", "CALC_003", "CALC_004", "CALC_005", "CALC_006", "CALC_007", "COMPONENT_SELECTION", "NETLIST", "PDM_PLACEMENT", "ROUTING", "VALIDATION", "BOM"],
        "num_feeders": ["CALC_004", "CALC_007", "COMPONENT_SELECTION", "NETLIST", "SCHEMATIC", "ENCLOSURE", "PDM_PLACEMENT", "ROUTING", "VALIDATION", "BOM"],
        "phases": ["CALC_001", "CALC_006", "COMPONENT_SELECTION", "NETLIST", "SCHEMATIC", "PDM_PLACEMENT"],
        "ip_rating": ["ENCLOSURE", "VALIDATION"]
    }

    def identify_dirty_nodes(self, modified_field: str) -> Set[str]:
        dirty = set()
        dirty.add(modified_field)
        downstream = self.DEPENDENCY_DAG.get(modified_field, [])
        for node in downstream:
            dirty.add(node)
        return dirty

    def compute_diff(self, old_cem: Dict[str, Any], new_cem: Dict[str, Any], old_pdm: Dict[str, Any], new_pdm: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates structural BEFORE vs AFTER diffs for UI presentation."""

        old_feeders = len([c for c in old_cem.get("components", []) if c.get("category") == "MCB"])
        new_feeders = len([c for c in new_cem.get("components", []) if c.get("category") == "MCB"])

        old_incomer = next((c for c in old_cem.get("components", []) if c.get("category") == "MCCB"), {})
        new_incomer = next((c for c in new_cem.get("components", []) if c.get("category") == "MCCB"), {})

        old_enc = f"{old_pdm.get('enclosure_width')}x{old_pdm.get('enclosure_height')}x{old_pdm.get('enclosure_depth')}"
        new_enc = f"{new_pdm.get('enclosure_width')}x{new_pdm.get('enclosure_height')}x{new_pdm.get('enclosure_depth')}"

        diffs = [
            {
                "property": "Feeder Breakers Count",
                "before": f"{old_feeders} MCBs",
                "after": f"{new_feeders} MCBs",
                "changed": old_feeders != new_feeders
            },
            {
                "property": "Incomer MCCB Rating",
                "before": f"{old_incomer.get('name', 'N/A')} ({old_incomer.get('current_rating', 0)}A)",
                "after": f"{new_incomer.get('name', 'N/A')} ({new_incomer.get('current_rating', 0)}A)",
                "changed": old_incomer.get("current_rating") != new_incomer.get("current_rating")
            },
            {
                "property": "Enclosure Dimensions (WxHxD mm)",
                "before": old_enc,
                "after": new_enc,
                "changed": old_enc != new_enc
            },
            {
                "property": "Total Thermal Dissipation",
                "before": f"{round(old_pdm.get('total_heat_loss_watts', 0), 1)} W",
                "after": f"{round(new_pdm.get('total_heat_loss_watts', 0), 1)} W",
                "changed": round(old_pdm.get("total_heat_loss_watts", 0), 1) != round(new_pdm.get("total_heat_loss_watts", 0), 1)
            },
            {
                "property": "Total Wire Routes Count",
                "before": f"{len(old_pdm.get('routes', []))} Wire Nets",
                "after": f"{len(new_pdm.get('routes', []))} Wire Nets",
                "changed": len(old_pdm.get("routes", [])) != len(new_pdm.get("routes", []))
            }
        ]

        return {
            "timestamp": "2026-09-17T00:00:00Z",
            "modified_field": list(self.DEPENDENCY_DAG.keys())[0],
            "diffs": diffs
        }
