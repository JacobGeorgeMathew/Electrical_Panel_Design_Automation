"""Compare installed PostgreSQL structures before adopting an existing baseline."""
import json
from pathlib import Path
from sqlalchemy import inspect


def signature(engine):
    inspector = inspect(engine)
    result = {}
    for table in sorted(set(inspector.get_table_names()) - {"alembic_version"}):
        columns = [{"name": c["name"], "type": str(c["type"].compile(dialect=engine.dialect)),
                    "nullable": c["nullable"], "default": c.get("default")}
                   for c in inspector.get_columns(table)]
        def ordered(records):
            return sorted(records, key=lambda record: json.dumps(record, sort_keys=True, default=str))
        result[table] = {"columns": columns, "primary_key": inspector.get_pk_constraint(table),
            "unique": ordered(inspector.get_unique_constraints(table)),
            "checks": ordered(inspector.get_check_constraints(table)),
            "foreign_keys": ordered(inspector.get_foreign_keys(table)),
            "indexes": ordered(inspector.get_indexes(table))}
    return json.loads(json.dumps(result, default=str))


def verify_baseline(engine, manifest_path=None):
    path = manifest_path or Path(__file__).with_name("baseline_manifest.json")
    expected = json.loads(path.read_text(encoding="utf-8"))
    actual = signature(engine)
    differences = [name for name in set(actual) | set(expected) if actual.get(name) != expected.get(name)]
    if differences:
        raise RuntimeError("Database does not match baseline; no stamp performed. Differing tables: " + ", ".join(sorted(differences)))

