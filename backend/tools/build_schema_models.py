"""Regenerate mappings from the frozen baseline plus reviewed Alembic upgrades.

Creates and removes a unique isolated database, never the configured project database.
"""
import json
import sys
from pathlib import Path
from uuid import uuid4
from sqlalchemy import MetaData, create_engine, inspect
from alembic import command
from alembic.config import Config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.persistence.config import Settings
from app.persistence.schema_tools import signature

root = Path(__file__).resolve().parents[1]
settings = Settings.load()
name = "panel_schema_build_" + uuid4().hex
admin = create_engine(settings.url.set(database="postgres"), isolation_level="AUTOCOMMIT", hide_parameters=True)
engine = None
try:
    with admin.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = create_engine(settings.url.set(database=name), hide_parameters=True)
    with engine.begin() as conn:
        conn.exec_driver_sql((root / "migrations/versions/0001_baseline.sql").read_text(encoding="utf-8"))
    (root / "app/persistence/baseline_manifest.json").write_text(
        json.dumps(signature(engine), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cfg = Config(str(root / "alembic.ini"))
    cfg.attributes["database_url"] = settings.url.set(database=name)
    command.stamp(cfg, "0001_baseline")
    command.upgrade(cfg, "head")
    metadata = MetaData()
    metadata.reflect(engine)
    inspector = inspect(engine)
    lines = ['"""Generated from the frozen DDL and Alembic head by tools/build_schema_models.py. Do not hand-edit."""',
             "from sqlalchemy import *", "from sqlalchemy.dialects.postgresql import *",
             "from sqlalchemy.orm import declarative_base, relationship", "metadata = MetaData()", ""]
    for name in sorted(set(metadata.tables) - {"alembic_version"}):
        table = metadata.tables[name]
        lines.append(f"{name} = Table({name!r}, metadata,")
        for col in table.columns:
            args = [repr(col.name), repr(col.type)]
            if col.primary_key:
                args.append("primary_key=True")
            args.append(f"nullable={col.nullable!r}")
            if col.server_default is not None:
                args.append(f"server_default=text({str(col.server_default.arg)!r})")
            lines.append("    Column(" + ", ".join(args) + "),")
        for fk in inspector.get_foreign_keys(name):
            target = [f"{fk['referred_table']}.{col}" for col in fk["referred_columns"]]
            options=dict(fk.get('options', {}))
            if fk['name']=='fk_project_current_revision': options['use_alter']=True
            lines.append(f"    ForeignKeyConstraint({fk['constrained_columns']!r}, {target!r}, name={fk['name']!r}, **{options!r}),")
        for uq in inspector.get_unique_constraints(name):
            lines.append(f"    UniqueConstraint(*{uq['column_names']!r}, name={uq['name']!r}),")
        for ck in inspector.get_check_constraints(name):
            lines.append(f"    CheckConstraint({ck['sqltext']!r}, name={ck['name']!r}),")
        lines.append(")\n")
    for name in sorted(set(metadata.tables) - {"alembic_version"}):
        for index in inspector.get_indexes(name):
            if index.get('duplicates_constraint'):
                continue
            columns=[]
            for col,expr in zip(index['column_names'],index.get('expressions',index['column_names'])):
                expression=f"{name}.c[{col!r}]" if col else f"text({expr!r})"
                for direction in index.get('column_sorting',{}).get(col,()):
                    expression+='.'+direction+'()'
                columns.append(expression)
            options = [f"unique={index['unique']!r}"]
            for key,value in index.get('dialect_options',{}).items():
                options.append(f"{key}=text({value!r})" if key.endswith('_where') else f"{key}={value!r}")
            lines.append(f"Index({index['name']!r}, " + ', '.join(columns+options) + ')')
    lines.append("Base = declarative_base(metadata=metadata)\n")
    for name in sorted(set(metadata.tables) - {"alembic_version"}):
        cls = "".join(part.title() for part in name.split("_"))
        lines.extend([f"class {cls}(Base):", f"    __table__ = {name}", ""])
    lines.extend([
        'Projects.revisions = relationship(ProjectRevisions, foreign_keys=[project_revisions.c.project_id], viewonly=True, order_by=project_revisions.c.revision_no)',
        'CemComponentInstances.terminals = relationship(CemTerminalInstances, viewonly=True)',
        'CadModelVersions.parameters = relationship(CadParameterDefinitions, viewonly=True)',
        'ValidationRuns.results = relationship(ValidationResults, viewonly=True)',
        ''
    ])
    (root / "app/persistence/models.py").write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated mappings and baseline manifest for {len(metadata.tables)-1} tables from isolated database.")
finally:
    if engine is not None:
        engine.dispose()
    with admin.connect() as conn:
        conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin.dispose()
