from dataclasses import dataclass
from pathlib import Path
from .io_utils import read_json, digest
from .lifecycle_validator import validate_lifecycle


@dataclass
class Lifecycle:
    path: Path
    schema_path: Path
    data: dict
    schema: dict
    ordered: list

    @property
    def fingerprint(self):
        return digest({"lifecycle": self.data, "schema": self.schema})

    @property
    def tasks(self):
        return {t["id"]: t for _, _, t in self.ordered}

    @property
    def forward_dependencies(self):
        positions = {t["id"]: i for i, (_, _, t) in enumerate(self.ordered)}
        return [(t["id"], d) for _, _, t in self.ordered for d in t["dependencies"]
                if positions[d] > positions[t["id"]]]

    def context(self, task_id):
        return next((p, m) for p, m, t in self.ordered if t["id"] == task_id)


def load_lifecycle(path, schema_path):
    data, schema = read_json(path), read_json(schema_path)
    return Lifecycle(Path(path), Path(schema_path), data, schema, validate_lifecycle(data, schema))
