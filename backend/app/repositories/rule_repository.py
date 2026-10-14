import json
import os
from typing import Any, Dict, List, Optional


class RuleRepository:
    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            data_path = os.path.join(os.path.dirname(__file__), "..", "data", "rules.json")
        self.data_path = data_path
        self._load_data()

    def _load_data(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, "r", encoding="utf-8") as f:
                self._rules = json.load(f)
        else:
            self._rules = []

    def get_all(self) -> List[Dict[str, Any]]:
        return self._rules

    def get_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [r for r in self._rules if r.get("category") == category]
