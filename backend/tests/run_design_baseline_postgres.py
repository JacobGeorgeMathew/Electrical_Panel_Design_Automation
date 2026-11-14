"""Local-peer disposable-database profile and optional timing launcher.

From backend: .venv/bin/python -m tests.run_design_baseline_postgres [--measure]
Uses only maintenance metadata here. All DDL is owned by the existing isolated
pytest fixtures. No development database is connected to or used as test data.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import psycopg
from sqlalchemy.engine import URL


def snapshot():
    with psycopg.connect(dbname='postgres', connect_timeout=3) as connection:
        assert connection.execute('SELECT current_database()').fetchone()[0] == 'postgres'
        capabilities = connection.execute(
            'SELECT rolcreatedb, rolsuper FROM pg_roles WHERE rolname=current_user').fetchone()
        assert capabilities and any(capabilities), 'Disposable database creation is unavailable'
        names = {row[0] for row in connection.execute(
            "SELECT datname FROM pg_database WHERE starts_with(datname, 'panel_integration_test_') "
            "OR starts_with(datname, 'panel_policy_upgrade_')")}
        return connection.info.server_version, names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--measure', action='store_true')
    parser.add_argument('--timings-only', action='store_true', help='Run only the opt-in timing tests')
    args = parser.parse_args()
    assert not args.timings_only or args.measure, '--timings-only requires --measure'
    assert Path.cwd().joinpath('tests/conftest.py').is_file(), 'Run from backend/'
    server, before = snapshot()
    print('postgres_server_version='+str(server), flush=True)
    print('disposable_databases_before='+str(sorted(before)), flush=True)
    environment = os.environ.copy()
    # A non-existent validation-only placeholder. Existing fixtures replace the
    # name with postgres or their generated disposable name before connecting.
    environment['DATABASE_URL'] = URL.create('postgresql+psycopg', database='panelflow_test_config_only').render_as_string(hide_password=False)
    environment.pop('PANEL_DATABASE_URL', None)
    environment['PANEL_RUN_POSTGRES_TESTS'] = '1'
    if args.measure:
        environment['PANEL_MEASURE_BASELINE'] = '1'
    else:
        environment.pop('PANEL_MEASURE_BASELINE', None)
    with tempfile.TemporaryDirectory(prefix='panelflow-p0-t03-assets-') as directory:
        environment['PANEL_DATA_DIR'] = directory
        command = [sys.executable, '-m', 'pytest', '-q', '-s']
        if args.timings_only:
            command.append('tests/test_design_baseline_performance.py')
        print('child_interpreter='+sys.executable, flush=True)
        try:
            result = subprocess.run(command, env=environment, check=False)
        finally:
            _, after = snapshot()
            print('disposable_databases_after='+str(sorted(after)), flush=True)
            print('fixture_database_cleanup='+('PASS' if after == before else 'FAIL'), flush=True)
    print('launcher_temporary_assets_cleanup=PASS', flush=True)
    return result.returncode if result.returncode else (0 if after == before else 1)


if __name__ == '__main__':
    raise SystemExit(main())
