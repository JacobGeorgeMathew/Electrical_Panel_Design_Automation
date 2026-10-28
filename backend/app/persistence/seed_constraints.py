"""Reapply the frozen data seed without changing published versions."""
import importlib.util
from pathlib import Path


def seed_constraints(database):
    path=Path(__file__).resolve().parents[2]/'migrations/versions/0003_constraints.py'
    spec=importlib.util.spec_from_file_location('panel_constraints_0003',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with database.engine.begin() as connection:
        return module.seed(connection)
