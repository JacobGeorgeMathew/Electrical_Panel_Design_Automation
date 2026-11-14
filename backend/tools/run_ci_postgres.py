"""Run the full PostgreSQL profile using fixture-owned disposable databases.

Run from backend/ with its virtual environment. Connection authentication uses
libpq's PG* environment (CI supplies only job-local service credentials). This
launcher reads maintenance metadata; the pytest fixtures own all database DDL.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

import psycopg
from sqlalchemy.engine import URL


def snapshot():
    with psycopg.connect(dbname='postgres', connect_timeout=5) as connection:
        capabilities = connection.execute(
            'SELECT rolcreatedb, rolsuper FROM pg_roles WHERE rolname=current_user'
        ).fetchone()
        if not capabilities or not any(capabilities):
            raise RuntimeError('The disposable PostgreSQL profile requires CREATEDB.')
        return {row[0] for row in connection.execute('SELECT datname FROM pg_database')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--junitxml', required=True)
    args = parser.parse_args()
    if not Path('tests/conftest.py').is_file():
        parser.error('Run from backend/ using .venv/bin/python.')
    if os.environ.get('PANEL_RUN_POSTGRES_TESTS') != '1':
        parser.error('Explicit PANEL_RUN_POSTGRES_TESTS=1 is required.')

    # A deliberately nonexistent placeholder; fixtures replace it before connecting.
    # Passwords remain in PGPASSWORD, never a URL, command argument or report.
    environment = os.environ.copy()
    environment['DATABASE_URL'] = URL.create(
        'postgresql+psycopg', username=environment.get('PGUSER'),
        host=environment.get('PGHOST'),
        port=int(environment['PGPORT']) if environment.get('PGPORT') else None,
        database='panelflow_ci_config_only',
    ).render_as_string(hide_password=False)
    environment.pop('PANEL_DATABASE_URL', None)
    before = snapshot()
    prefixes = ('panel_integration_test_', 'panel_policy_upgrade_')
    if any(name.startswith(prefixes) for name in before):
        raise RuntimeError('Pre-existing disposable test databases require investigation.')
    cleanup_ok = False
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pytest', '-ra', '--junitxml='+args.junitxml],
            env=environment, check=False,
        )
    finally:
        # Compare all names; never drop an unexpected or pre-existing database.
        cleanup_ok = snapshot() == before
        status = 'PASS' if cleanup_ok else 'FAIL'
        message = 'Disposable database teardown audit: '+status
        print(message, flush=True)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
                summary.write(message+'\n\n')
    return result.returncode or (0 if cleanup_ok else 1)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (psycopg.Error, RuntimeError, ValueError):
        # Driver exceptions may include connection configuration. Keep it private.
        print('PostgreSQL preflight/teardown failed; check service health, CREATEDB and isolation.', file=sys.stderr)
        raise SystemExit(1)
