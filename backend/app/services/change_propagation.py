from datetime import datetime, timezone
from typing import Any, Dict, List, Set


class ChangePropagationEngine:
    """Manages design dependency DAG and evaluates affected downstream stages when requirements change."""

    DEPENDENCY_DAG = {
        "supply_voltage": ["CALCULATIONS", "NETLIST", "SCHEMATIC", "ROUTING", "VALIDATION", "CAD"],
        "frequency": ["REQUIREMENT_VALIDATION", "CALCULATIONS"],
        "incomer_rating": ["CALC_001", "CALC_002", "CALC_003", "CALC_004", "CALC_005", "CALC_006", "CALC_007", "COMPONENT_SELECTION", "NETLIST", "PDM_PLACEMENT", "ROUTING", "VALIDATION", "BOM"],
        "num_feeders": ["CALCULATIONS", "COMPONENT_SELECTION", "ELECTRICAL_GRAPH", "NETLIST", "SCHEMATIC", "ENCLOSURE", "PDM_PLACEMENT", "ROUTING", "VALIDATION", "BOM", "CAD"],
        "phases": ["CALCULATIONS", "COMPONENT_SELECTION", "ELECTRICAL_GRAPH", "NETLIST", "SCHEMATIC", "ENCLOSURE", "PDM_PLACEMENT", "ROUTING", "VALIDATION", "BOM", "CAD"],
        "ip_rating": ["ENCLOSURE", "PDM_PLACEMENT", "ROUTING", "VALIDATION", "CAD"],
        "neutral_required": ["COMPONENT_SELECTION", "ELECTRICAL_GRAPH", "NETLIST", "SCHEMATIC", "PDM_PLACEMENT", "ROUTING", "VALIDATION", "BOM", "CAD"],
        "spare_capacity_pct": ["CALCULATIONS"],
    }

    def identify_dirty_nodes(self, modified_field: str) -> Set[str]:
        dirty = set()
        dirty.add(modified_field)
        downstream = self.DEPENDENCY_DAG.get(modified_field, [])
        for node in downstream:
            dirty.add(node)
        return dirty

    def compute_diff(self, old_cem: Dict[str, Any], new_cem: Dict[str, Any], old_pdm: Dict[str, Any],
                     new_pdm: Dict[str, Any], modified_field: str = "",
                     old_values: Dict[str, Any] = None, new_values: Dict[str, Any] = None) -> Dict[str, Any]:
        """Calculates structural BEFORE vs AFTER diffs for UI presentation."""

        old_feeders = len([c for c in old_cem.get("components", []) if c.get("category") == "MCB"])
        new_feeders = len([c for c in new_cem.get("components", []) if c.get("category") == "MCB"])

        old_incomer = next((c for c in old_cem.get("components", []) if c.get("category") == "MCCB"), {})
        new_incomer = next((c for c in new_cem.get("components", []) if c.get("category") == "MCCB"), {})

        old_enc = f"{old_pdm.get('enclosure_width')}x{old_pdm.get('enclosure_height')}x{old_pdm.get('enclosure_depth')}"
        new_enc = f"{new_pdm.get('enclosure_width')}x{new_pdm.get('enclosure_height')}x{new_pdm.get('enclosure_depth')}"

        old_values = old_values or {}
        new_values = new_values or {}
        diffs = [
            {
                "property": f"Requirement: {modified_field}",
                "before": str(old_values.get(modified_field, "N/A")),
                "after": str(new_values.get(modified_field, "N/A")),
                "changed": old_values.get(modified_field) != new_values.get(modified_field)
            },
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "modified_field": modified_field,
            "affected_stages": sorted(self.identify_dirty_nodes(modified_field)) if modified_field else [],
            "diffs": diffs
        }
