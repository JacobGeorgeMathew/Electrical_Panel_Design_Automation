"""Back up and adopt the existing project DB, then import preserved JSON sources.

No database is dropped or recreated. Secrets are passed to pg_dump via its child
environment, never process arguments or files. Run from backend/.
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy import select,func

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.persistence.config import Settings
from app.persistence.database import Database
from app.persistence.manage import initialize,alembic_config
from app.persistence.import_legacy import import_legacy
from app.persistence import models as m
from alembic import command


def main():
    settings=Settings.load()
    if settings.url.database!='electrical_panel_design':
        raise RuntimeError('This helper is restricted to the electrical_panel_design development database.')
    dump=shutil.which('pg_dump')
    if not dump: raise RuntimeError('pg_dump must be available before adopting the existing development database.')
    backup_dir=Path(__file__).resolve().parents[2]/'.local/backups'
    backup_dir.mkdir(parents=True,exist_ok=True)
    backup=backup_dir/('before-postgres-integration-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.dump')
    child_env=os.environ.copy()
    for key,value in {'PGHOST':settings.url.host,'PGPORT':settings.url.port,'PGUSER':settings.url.username,
                      'PGPASSWORD':settings.url.password,'PGDATABASE':settings.url.database}.items():
        if value is not None: child_env[key]=str(value)
    for key,value in settings.url.query.items():
        env_key={'sslmode':'PGSSLMODE','sslrootcert':'PGSSLROOTCERT','sslcert':'PGSSLCERT','sslkey':'PGSSLKEY','options':'PGOPTIONS'}.get(key)
        if env_key: child_env[env_key]=str(value)
    result=subprocess.run([dump,'--no-password','--format=custom','--file',str(backup)],env=child_env,capture_output=True)
    if result.returncode: raise RuntimeError('Backup failed; no schema changes were attempted.')
    restore=Path(dump).with_name('pg_restore.exe' if os.name=='nt' else 'pg_restore')
    result=subprocess.run([str(restore),'--list',str(backup)],capture_output=True)
    if result.returncode or not result.stdout: raise RuntimeError('Backup archive verification failed; no schema changes were attempted.')
    print('Development backup created and archive checked:',backup)
    db=Database(settings)
    try:
        initialize(db)
        command.check(alembic_config(settings.url))
        print('Imported source data:',json.dumps(import_legacy(db)))
        with db.sessions() as s:
            summary={name:s.scalar(select(func.count()).select_from(table)) for name,table in
                     [('projects',m.projects),('components',m.components),('component_versions',m.component_versions),('archetypes',m.panel_archetypes)]}
        print('Database ready:',db.ready())
        print('Database counts:',json.dumps(summary))
    finally:
        db.close()

if __name__=='__main__':
    try: main()
    except RuntimeError as exc:
        print(str(exc));raise SystemExit(1) from None
    except Exception:
        print('Development database setup failed. Configuration details are hidden; inspect migration status before retrying.')
        raise SystemExit(1) from None
