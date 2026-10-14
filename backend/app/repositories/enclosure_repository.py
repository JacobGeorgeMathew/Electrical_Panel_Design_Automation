import json
import os
from typing import Any, Dict, List, Optional


class EnclosureRepository:
    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            data_path = os.path.join(os.path.dirname(__file__), "..", "data", "enclosures.json")
        self.data_path = data_path
        self._load_data()

    def _load_data(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, "r", encoding="utf-8") as f:
                self._enclosures = json.load(f)
        else:
            self._enclosures = []

    def get_all(self) -> List[Dict[str, Any]]:
        return self._enclosures

    def get_by_id(self, enclosure_id: str) -> Optional[Dict[str, Any]]:
        for enc in self._enclosures:
            if enc["id"] == enclosure_id:
                return enc
        return None

    def find_best_fit(self, min_width: float, min_height: float, min_thermal_dissipation: float, ip_rating: str = "IP54") -> Optional[Dict[str, Any]]:
        feasible = []
        for enc in self._enclosures:
            if enc["mounting_plate_width"] >= min_width and enc["mounting_plate_height"] >= min_height and enc.get("max_thermal_dissipation", 999) >= min_thermal_dissipation:
                feasible.append(enc)
        if not feasible:
            # Fallback to largest available
            return max(self._enclosures, key=lambda e: e["width"] * e["height"]) if self._enclosures else None
        # Sort by usable surface area ascending (smallest feasible enclosure)
        feasible.sort(key=lambda e: e["width"] * e["height"])
        return feasible[0]
