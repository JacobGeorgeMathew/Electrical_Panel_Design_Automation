"""Disposable browser backend. Run with backend/.venv/bin/python, cwd backend/.

Never connects to the configured application database. Only maintenance metadata
and a newly allocated database are accessed; assets live in TemporaryDirectory.
The private seed route exists only in this process, never in app.main.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import socket
import sys
from tempfile import TemporaryDirectory
from threading import Thread
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
import uvicorn

from app.main import create_app
from app.security.local_session import LocalSession
from app.persistence.config import Settings
from app.persistence.database import Database
from app.persistence.import_legacy import import_legacy
from app.persistence.manage import initialize
from tests.test_operation_persistence import persisted_base
from tests.test_schematic_operations import with_evidence
from app.models.document import SnapshotReference, snapshot_sha256
from app.persistence.documents import DocumentRepository


def main():
    print('E2E interpreter: ' + sys.executable, flush=True)
    print('E2E prefix: ' + sys.prefix, flush=True)
    expected = Path.cwd() / '.venv'
    if Path(sys.prefix).resolve() != expected.resolve():
        raise RuntimeError('Use backend/.venv/bin/python with backend/ as cwd.')
    # Same private configuration as conftest, or libpq PG* authentication as in
    # tools.run_ci_postgres. The placeholder database is never connected to.
    if os.environ.get('DATABASE_URL') or os.environ.get('PANEL_DATABASE_URL'):
        settings = Settings.load()
    else:
        settings = Settings(url=URL.create('postgresql+psycopg',
            username=os.getenv('PGUSER'), host=os.getenv('PGHOST'),
            port=int(os.environ['PGPORT']) if os.getenv('PGPORT') else None,
            database='panelflow_e2e_config_only'))
    name = 'panel_e2e_' + uuid4().hex
    assert re.fullmatch(r'panel_e2e_[a-f0-9]{32}', name)
    admin = create_engine(settings.url.set(database='postgres'),
                          isolation_level='AUTOCOMMIT', hide_parameters=True)
    created = False
    db = None
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
        created = True
        print('E2E allocated: ' + name, flush=True)
        with TemporaryDirectory(prefix='panelflow-e2e-') as storage:
            db = Database(replace(settings, url=settings.url.set(database=name),
                                  asset_root=Path(storage) / 'assets'))
            initialize(db)
            source = Path(__file__).resolve().parents[2] / 'docs/database/002_sample_data.sql'
            sql = re.sub(r'(?m)^(BEGIN|COMMIT);\s*$', '', source.read_text(encoding='utf-8'))
            with db.engine.begin() as conn:
                conn.exec_driver_sql(sql)
            import_legacy(db)
            origin = os.environ['PANEL_E2E_ORIGIN']
            if not re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', origin):
                raise ValueError('Invalid private browser harness origin.')
            session = LocalSession(mode='development')
            # Only this private harness accepts its exact owned ephemeral origin.
            session.origins = frozenset({origin})
            os.environ['PANEL_DATA_DIR'] = storage
            app = create_app(db, local_session=session)

            @app.post('/__e2e__/projects')
            def seed(electrical: bool = False):
                # Reuse the qualified operation storage fixture: stable logical
                # IDs/nonzero offsets, fresh project/document IDs for each test.
                project_id, base = persisted_base(db)
                if electrical:
                    # Explicit endpoint roles qualify only this synthetic fixture.
                    # Production UI cannot infer supply/phase evidence from labels.
                    base = with_evidence(base)
                    third = base.snapshots.cem.components[-1].model_copy(deep=True)
                    third.id = 'PE002'
                    base.snapshots.cem.components.append(third)
                    symbol = base.snapshots.schematic.symbols[-1].model_copy(deep=True)
                    symbol.id, symbol.component_id, symbol.pins[0].id = 'symbol-3', 'PE002', 'pin-3'
                    dx, dy = 500 - symbol.position.x, 300 - symbol.position.y
                    symbol.position.x += dx
                    symbol.position.y += dy
                    for pin in symbol.pins:
                        pin.position.x += dx
                        pin.position.y += dy
                    base.snapshots.schematic.symbols.append(symbol)
                    base.document.configuration['electrical_topology']['domains'].append(
                        dict(component_id='PE002', terminal_id='MAIN_PE', supply_id='supply-1', role='PE'))
                    for kind in ('cem', 'pdm', 'schematic'):
                        setattr(base.document.models, kind, SnapshotReference(sha256=snapshot_sha256(getattr(base.snapshots, kind))))
                    with db.sessions.begin() as session:
                        DocumentRepository(session).store(base)
                return {'projectId': project_id}

            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))

                class HarnessServer(uvicorn.Server):
                    async def startup(self, sockets=None):
                        await super().startup(sockets=sockets)
                        if self.started:
                            print('E2E_READY ' + json.dumps({'port': sock.getsockname()[1]}), flush=True)

                server = HarnessServer(uvicorn.Config(app, log_level='warning', access_log=False))

                def stop_on_eof():
                    sys.stdin.buffer.read()
                    server.should_exit = True

                Thread(target=stop_on_eof, daemon=True).start()
                server.run(sockets=[sock])
    finally:
        try:
            if db is not None:
                db.close()
        finally:
            try:
                if created:
                    with admin.connect() as conn:
                        conn.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
                        assert not conn.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'), {'name': name})
                    print('E2E database cleanup: PASS ' + name, flush=True)
            finally:
                admin.dispose()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Driver exceptions can contain credentials/SQL. Do not forward them.
        print('E2E backend failed. Check backend interpreter, PostgreSQL access, CREATEDB and fixture setup/cleanup.', file=sys.stderr)
        raise SystemExit(1)
