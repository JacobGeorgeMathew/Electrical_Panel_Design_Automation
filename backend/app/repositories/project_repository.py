import json
import os
from typing import Any, Dict, List, Optional


class ProjectRepository:
    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            data_path = os.path.join(os.path.dirname(__file__), "..", "data", "sample_projects.json")
        self.data_path = data_path
        self._projects: Dict[str, Dict[str, Any]] = {}
        self._load_data()

    def _load_data(self):
        if os.path.exists(self.data_path):
            with open(self.data_path, "r", encoding="utf-8") as f:
                projects_list = json.load(f)
                for p in projects_list:
                    self._projects[p["id"]] = p

    def get_all(self) -> List[Dict[str, Any]]:
        self._load_data()
        return list(self._projects.values())

    def get_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        self._load_data()
        return self._projects.get(project_id)

    def save(self, project_data: Dict[str, Any]) -> Dict[str, Any]:
        self._load_data()
        project_id = project_data["id"]
        self._projects[project_id] = project_data
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(list(self._projects.values()), f, ensure_ascii=False, indent=2)
        return project_data
