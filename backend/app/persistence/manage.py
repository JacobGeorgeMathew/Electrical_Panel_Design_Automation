"""Run from backend/: python -m app.persistence.manage initialize|status|import-legacy."""
import argparse
import json
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from app.persistence.config import Settings
from app.persistence.database import Database
from app.persistence.schema_tools import verify_baseline


def alembic_config(url):
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    cfg.attributes['database_url']=url
    return cfg


def initialize(database):
    tables=set(inspect(database.engine).get_table_names())
    cfg=alembic_config(database.settings.url)
    if 'alembic_version' not in tables and tables:
        verify_baseline(database.engine)
        command.stamp(cfg,'0001_baseline')
        print('Existing schema exactly matches the frozen baseline; adopted migration history.')
    command.upgrade(cfg,'head')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['initialize','status','import-legacy','import-panel-hardware','verify-baseline','audit-assets'])
    args=parser.parse_args()
    database=Database(Settings.load())
    try:
        if args.action=='initialize': initialize(database)
        elif args.action=='verify-baseline':
            verify_baseline(database.engine)
            print('Baseline structures match.')
        elif args.action=='status':
            command.current(alembic_config(database.settings.url))
            print('Ready:',database.ready())
        elif args.action=='import-legacy':
            if not database.ready(): raise RuntimeError('Apply migrations before importing.')
            from app.persistence.import_legacy import import_legacy
            print(json.dumps(import_legacy(database)))
        elif args.action=='import-panel-hardware':
            if not database.ready(): raise RuntimeError('Apply migrations before importing.')
            from app.persistence.import_panel_hardware import import_panel_hardware
            print(json.dumps(import_panel_hardware(database)))
        elif args.action=='audit-assets':
            from sqlalchemy import select
            from app.persistence import models as m
            from app.persistence.assets import AssetStore
            assets=AssetStore(database.settings.asset_root)
            with database.sessions() as session:
                rows=[dict(r) for table in (m.cad_assets,m.generated_artifacts) for r in session.execute(select(table).where(table.c.generation_status=='READY')).mappings()]
            referenced={r['storage_key'] for r in rows if r['storage_key']}
            stored={p.relative_to(assets.root).as_posix() for p in assets.root.glob('sha256/*/*/*') if p.is_file()}
            print(json.dumps({'referenced':len(referenced),'missing_or_corrupt':sum(assets.availability(r)!='READY' for r in rows),
                              'unreferenced_files':len(stored-referenced),'automatic_deletion':False}))
    except Exception as exc:
        # Database exceptions can include SQL parameters. Keep CLI output safe too.
        from app.persistence.repositories import PersistenceError
        if isinstance(exc,(RuntimeError,PersistenceError)):
            print(str(exc))
        else:
            print('Database operation failed. Check configuration and migration compatibility; connection details are hidden.')
        raise SystemExit(1) from None
    finally:
        database.close()


if __name__=='__main__': main()
