import json
import os
from typing import Any, Dict, List, Optional


class ComponentRepository:
    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            data_path = os.path.join(os.path.dirname(__file__), "..", "data", "components.json")
        self.data_path = data_path
        self._load_data()

    def _load_data(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, "r", encoding="utf-8") as f:
                self._components = json.load(f)
        else:
            self._components = []

    def get_all(self) -> List[Dict[str, Any]]:
        return self._components

    def get_by_id(self, component_id: str) -> Optional[Dict[str, Any]]:
        for comp in self._components:
            if comp["id"] == component_id:
                return comp
        return None

    def filter_candidates(self, category: str, min_current: float = 0, min_breaking_capacity: float = 0, poles: Optional[int] = None) -> List[Dict[str, Any]]:
        candidates = []
        for comp in self._components:
            if comp.get("category") != category:
                continue
            if comp.get("current_rating", 0) < min_current:
                continue
            if comp.get("breaking_capacity", 0) < min_breaking_capacity:
                continue
            if poles is not None and comp.get("poles") != poles:
                continue
            candidates.append(comp)
        return candidates
