# P0-T02 isolated baseline verification

PanelFlow prototype Distribution Board designer. Verification evidence for human
review; this document does not grant task acceptance or engineering approval.

**Result:** all four required profiles passed. Backend unit profile: 74 passed,
19 intentional PostgreSQL skips. PostgreSQL-enabled full suite: 93 passed,
zero skips. Frontend: 61 passed; TypeScript/Vite build passed. No blocking product
defect was observed. Initial sandbox failures and their approved retries remain
recorded below. Verification finished on 2026-11-12.

## Scope and environment

Attempt 01 on 2026-11-12, branch `phase_1`, HEAD
`6e85b6b2918aaee2587e2c473584d076486d636e`. Repository root:
`/home/jacobGM/Desktop/Engineering/s7/Project/Electrical_Panel_board_design/Electrical_Panel_design_automation`.
Working directories below are relative to that root. Existing untracked
`docs/architecture/current-contracts.md` belongs to P0-T01 and was preserved.

Read root `AGENTS.md` (the only discovered repository instruction file), the
read-only lifecycle's P0-T02 and quality-engineer responsibilities, the accepted
P0-T01 report and architecture inventory, and `docs/database/OPERATIONS.md`.
Verified isolation/configuration claims against the actual fixture, migration
test, settings loader, database adapter and application lifespan. The operations
document's opening migration-head statement is historical; source requires
`0004_projects`. No management initialization/import command was run against a
configured application database.

| Item | Observed environment |
| --- | --- |
| OS | Linux `7.2.11-arch1-1-x86_64`, x86_64, glibc 2.44 |
| Python | 3.14.8, GCC 16.2.1; backend interpreter only |
| Interpreter | `<root>/backend/.venv/bin/python`, symlink to `/usr/bin/python` |
| `sys.prefix` | `<root>/backend/.venv` (confirmed virtual environment) |
| Backend runner | pytest 9.1.1, pluggy 1.7.0, anyio plugin 4.15.1 |
| Node/npm | v24.18.0 / 12.2.2, under `~/.nvm/versions/node/v24.18.0/bin/` |
| Frontend tools | Vitest 1.6.1, TypeScript 5.9.3, Vite 5.4.21, jsdom 24.1.3 |
| PostgreSQL | Local Unix-socket peer access; server version number `180006`; current role has `CREATEDB` and superuser capabilities |
| Time | UTC date 2026-11-12; runner display timezone Asia/Kolkata (UTC+05:30) |

`DATABASE_URL` and `PANEL_DATABASE_URL` were absent at preflight;
`PANEL_RUN_POSTGRES_TESTS` was unset. Only presence booleans were printed. No
credentials or connection strings are recorded here.
Subsequent read-only checks established that the existing OS account could
authenticate to the local maintenance database without a password. No private
file or new credentials were needed. The integration launcher supplies test-only
configuration to the pytest child process, without modifying shell/user settings.

## Dependency verification

Reused the existing backend virtual environment and `frontend/node_modules`.
All 11 direct requirements exactly matched `requirements.txt`, including
`psycopg` and the separately checked `psycopg-binary` extra at 3.3.6.
`pip check` exited 0 with `No broken requirements found.` The frontend audit
checked every present non-link lockfile package's installed `package.json`
version: 347 checked, zero mismatches or missing required packages. Platform
optional packages may be absent. Both dependency groups in the root manifest
matched the lockfile root; `npm ls --depth=0` exited 0.

No dependency installation, upgrade, virtual-environment recreation or lockfile
edit was needed. Backend requirements pin direct dependencies, not their full
transitive graph; this is verification of the existing matching environment,
not a claim of a fresh installation or wheel/tarball integrity audit.

Exact diagnostic commands (all exit 0 unless noted) were:

```sh
# cwd backend: interpreter/OS/private-configuration presence; never prints values
.venv/bin/python -c 'import sys,platform,os; print("executable="+sys.executable); print("prefix="+sys.prefix); print("python="+sys.version); print("platform="+platform.platform()); print("db_config_present="+str({key: bool(os.environ.get(key)) for key in ("DATABASE_URL", "PANEL_DATABASE_URL")})); print("postgres_flag="+repr(os.environ.get("PANEL_RUN_POSTGRES_TESTS")))'
# The actual first invocation used backend/.venv/bin/python from repository root.
# cwd backend: audit every nonempty pinned requirement
.venv/bin/python -c 'import importlib.metadata as m, pathlib; pins=[line.strip().split("==") for line in pathlib.Path("requirements.txt").read_text().splitlines() if line.strip()]; mismatches=[]; [(print(name+" expected="+version+" installed="+m.version(name.split("[")[0])), mismatches.append(name) if m.version(name.split("[")[0]) != version else None) for name,version in pins]; raise SystemExit(bool(mismatches))'
.venv/bin/python -c 'import importlib.metadata as m; print("psycopg-binary="+m.version("psycopg-binary"))'
.venv/bin/python -m pip check
.venv/bin/python -m pip list --format=freeze --disable-pip-version-check
# cwd frontend
node --version
npm --version
npm ls --depth=0
node -e 'const fs=require("fs"),crypto=require("crypto"); const path="package-lock.json",raw=fs.readFileSync(path),lock=JSON.parse(raw); let count=0,errors=[]; for(const [p,info] of Object.entries(lock.packages)){if(!p||info.link)continue; const installed=p+"/package.json"; if(!fs.existsSync(installed)){if(!info.optional)errors.push(p+" missing"); continue;}const actual=JSON.parse(fs.readFileSync(installed));count++;if(actual.version!==info.version)errors.push(p+" expected="+info.version+" installed="+actual.version);}console.log(JSON.stringify({lockfileVersion:lock.lockfileVersion,lockSha256:crypto.createHash("sha256").update(raw).digest("hex"),checked:count,errors},null,2));process.exitCode=errors.length?1:0;'
node -e 'const fs=require("fs");let p=JSON.parse(fs.readFileSync("package.json")),l=JSON.parse(fs.readFileSync("package-lock.json")); for(const k of ["dependencies","devDependencies"]){const a=JSON.stringify(Object.entries(p[k]).sort()),b=JSON.stringify(Object.entries(l.packages[""][k]).sort());if(a!==b)throw Error(k+" mismatch");}console.log("manifest-lock agreement: PASS");'
# cwd repository root
sha256sum backend/requirements.txt frontend/package.json frontend/package-lock.json backend/tests/conftest.py
```

| Input | SHA-256 at verification |
| --- | --- |
| `backend/requirements.txt` | `d6db29db39031d4386e5acdb2bb30e9c6ad01db5877c0f60e6c890fc8bdca4af` |
| `frontend/package.json` | `0a0a17756c9350eb122c5c73465424fd6ce95ac9fde37259102f3935731e563f` |
| `frontend/package-lock.json` | `8b064195121e137484784d0bf68a628a316a23fb66d78a57bb143643cf7a8a8d` |
| `backend/tests/conftest.py` | `94c31bddf8befb25a8f7bb3fe8056f7af74762940d647c1a2f595006a0030840` |

Observed backend environment inventory (`.venv/bin/python -m pip list
--format=freeze --disable-pip-version-check`, cwd `backend`, exit 0):

```text
absl-py==2.5.1
alembic==1.20.1
annotated-doc==0.0.5
annotated-types==0.8.0
anyio==4.15.1
certifi==2026.7.22
charset-normalizer==3.5.2
click==8.5.0
docopt==0.6.2
fastapi==0.143.2
greenlet==3.5.6
h11==0.16.0
httpcore==1.0.9
httptools==0.9.0
httpx==0.28.1
idna==3.20
immutabledict==4.3.1
iniconfig==2.3.1
Mako==1.4.3
MarkupSafe==3.0.4
networkx==3.7
numpy==2.5.4
opentelemetry-api==1.45.1
ortools==9.15.6755
packaging==26.3
pandas==3.0.6
pip==26.2.1
pipreqs==0.4.13
pluggy==1.7.0
protobuf==6.33.6
psycopg==3.3.6
psycopg-binary==3.3.6
pydantic==2.14.1
pydantic_core==2.50.1
Pygments==2.21.0
pytest==9.1.1
python-dateutil==2.9.0.post0
python-dotenv==1.2.4
PyYAML==6.0.3
requests==2.34.2
shapely==2.2.0
six==1.17.0
SQLAlchemy==2.0.55
starlette==1.8.0
typing_extensions==4.16.0
typing-inspection==0.4.4
urllib3==2.8.0
uvicorn==0.54.0
uvloop==0.23.0
watchfiles==1.3.0
websockets==17.2
yarg==0.1.10
```

## Commands and results

Commands were invoked through the execution tool with the stated working
directory, without switching to the orchestrator/system Python. No test
expectations, skip conditions, constraints or source behavior were edited.

| ID | Cwd | Exact command | Exit | Evidence |
| --- | --- | --- | --- | --- |
| F1 | `frontend` | `npm test -- src/stores/projectStore.persistence.test.ts` | 0 | Focused prerequisite: 1 file, 10 tests passed; 1.23 s |
| F2 | `frontend` | `npm test` | 0 | 19 files, 61 tests passed; no skips; 9.37 s |
| F3 | `frontend` | `npm run build` | 0 | `tsc && vite build`; 2,280 modules; Vite 6.82 s |
| B1 | `backend` | `.venv/bin/python -m pytest` | 130 | Initial sandbox run interrupted after stalling at readiness TestClient startup; no final summary |
| P1 | `backend` | `PANEL_RUN_POSTGRES_TESTS=1 .venv/bin/python -m pytest` | 130 | Initial sandbox run interrupted at the same test; fixture setup errors preceded the stall; no final summary |
| D1 | `backend` | `timeout --signal=INT --kill-after=5s 30s .venv/bin/python -m pytest tests/test_postgres.py::test_readiness_failure_is_safe -vv -o faulthandler_timeout=15` | 137 | Sandbox diagnostic: stack dump at 15 s, eventual forced timeout termination |
| D2 | `backend` | `timeout --signal=INT --kill-after=5s 30s .venv/bin/python -m pytest tests/test_postgres.py::test_readiness_failure_is_safe -vv -o faulthandler_timeout=15` | 0 | Approved execution outside sandbox: 1 passed, 1 warning, 0.80 s |
| B2 | `backend` | `.venv/bin/python -m pytest` | 0 | Approved execution outside sandbox: 74 passed, 19 skipped, 1 warning; 26.22 s |
| P2 | `backend` | `.venv/bin/python /tmp/panelflow-p0-t02-postgres.py` | 0 | Approved launcher; pytest child exit 0: 93 passed, no skips, 1 warning; 60.48 s; cleanup passed |

The PostgreSQL retry is launched as `.venv/bin/python
/tmp/panelflow-p0-t02-postgres.py` from `backend`, with approved execution outside
the sandbox. Its child runs exactly `.venv/bin/python -m pytest` with
`PANEL_RUN_POSTGRES_TESTS=1`, `PANEL_DATA_DIR` pointing to a launcher-owned
temporary directory, and a process-only `DATABASE_URL` built from local peer
authentication plus a validation-only database-name placeholder. The audited
fixtures replace that name with maintenance/disposable names before connecting.
No application database connection is made to that placeholder. The launcher
checks maintenance metadata before and after the child; it makes no DDL changes
itself. Its source hash is
`ba470f7fac373b5ec360ad3d5cf79ad282898302576e440204976534e2a46721`.
The full launcher source is preserved below so reproduction does not depend on
the temporary file surviving. No pytest arguments or expected outputs were
changed by the launcher.

P2 terminal evidence:

```text
postgres_server_version=180006
disposable_databases_before=[]
temporary_panel_data_dir=/tmp/panelflow-p0-t02-assets-rao3yt3b
child_command=.venv/bin/python -m pytest
collected 93 items
=================== 93 passed, 1 warning in 60.48s (0:01:00) ===================
pytest_exit_code=0
disposable_databases_after=[]
new_disposable_databases_remaining=[]
fixture_database_cleanup=PASS
launcher_temporary_assets_cleanup=PASS
```

Additional access diagnostics: local `psql`, `pg_isready` and `postgres` were
available at `/usr/bin/`; `/run/postgresql` existed; no libpq PGHOST/PGPORT/PGUSER/
PGSERVICE/PGSERVICEFILE/PGPASSFILE variable was set. A maintenance-only Psycopg
probe exited 1 inside the sandbox (`Operation not permitted` on the Unix
socket); its identical approved retry outside exited 0, reporting role
capabilities `(True, True)` for CREATEDB/superuser and server version `180006`.
Neither probe performed writes or used a development database.

B2 collected 93 tests. The 19 skips all depend on `postgres_database` (directly
or through `api`), whose exact skip reason is:
`Set PANEL_RUN_POSTGRES_TESTS=1 to exercise a unique isolated PostgreSQL database.`
The opt-in flag was unset for this unit profile, as intended. Skip breakdown:

| File | Skipped |
| --- | ---: |
| `tests/test_constraints.py` | 2 |
| `tests/test_panel_assembly.py` | 1 |
| `tests/test_postgres.py` | 10 |
| `tests/test_project_lifecycle.py` | 5 |
| `tests/test_questionnaire_choices.py` | 1 |

```text
================== 74 passed, 19 skipped, 1 warning in 26.22s ==================
```

F2 terminal summary:

```text
Test Files  19 passed (19)
     Tests  61 passed (61)
  Duration  9.37s
```

F3 produced ignored `frontend/dist/` output, including a 1,568.94 kB minified JS
bundle (454.13 kB gzip). Vite warned that chunks exceed 500 kB. This was a build
warning, not a compilation failure; no bundle threshold was changed.

D1's stack dump showed the main thread waiting in AnyIO
`run_sync_from_thread` / `start_task_soon`, called by
`starlette.testclient.TestClient.__enter__` at `tests/test_postgres.py:187`;
the portal thread was in `selectors.select`. This test injects `BrokenDB` and
does not need PostgreSQL. D2 passed with unchanged code/dependencies outside the
sandbox. This supports an execution-environment limitation; it does not establish
the underlying sandbox mechanism. B1/P1 were stopped with tool Ctrl-C (exit 130).

The D2 warning was `StarletteDeprecationWarning`: HTTPX use with Starlette
TestClient is deprecated in the installed pinned stack. No dependencies were
changed to suppress it. Pip also warned that its home cache was not writable and
disabled that cache; both pip diagnostics still exited 0.

## PostgreSQL isolation and cleanup

Source review: [`postgres_database`](../../backend/tests/conftest.py) first
requires `PANEL_RUN_POSTGRES_TESTS=1`, then loads private settings. Its admin
connection explicitly selects maintenance database `postgres`. It generates and
regex-checks `panel_integration_test_<32 hex>` before `CREATE DATABASE`, replaces
the application URL database with that generated name, and uses a pytest
temporary asset root. Only then does it initialize migrations, execute the
checked-in SQL sample fixture and import checked-in legacy fixture data. The
comment about matching development data describes fixture content; it does not
read the live development database.

An additional test,
[`test_existing_0002_database_migrates_without_rewriting_history`](../../backend/tests/test_constraints.py),
creates a separately regex-checked `panel_policy_upgrade_<32 hex>` database from
the same maintenance connection, upgrades it from `0002_app` to head and checks
preserved history. It depends on the session fixture, so cannot run when that
fixture is skipped or fails. Unlike the session fixture, it inherits the settings
asset root; provision `PANEL_DATA_DIR` to temporary storage for a future isolated
run of this test too.

Both paths close their database engine, then `DROP DATABASE IF EXISTS` for their
generated name `WITH (FORCE)` in `finally`, then dispose the admin engine. These
are cleanup implementations, not proof that a database was created and removed
in an interrupted or unconfigured run.

**Runtime evidence from P2:** both disposable-fixture test paths passed. The
launcher queried `pg_database` on maintenance database `postgres` before and
after the entire child, including session fixture teardown, for both literal
prefixes `panel_integration_test_` and `panel_policy_upgrade_`. Both lists were
empty; no new matching database remained. The actual generated UUID names were
not instrumented or recorded. The launcher-owned `PANEL_DATA_DIR`
`/tmp/panelflow-p0-t02-assets-rao3yt3b` was removed on exit, covering the migration
test's inherited asset root as well. The main session fixture used its own
pytest-managed temporary asset directory, which pytest may retain as normal
diagnostic temp data; no claim is made that all pytest temp files were deleted.

No development database was migrated, imported, truncated or used as test data.
No application-management command was run manually. Migrations/imports occurred
only inside the two source-reviewed generated-database paths. The runner's
maintenance probes were SELECT-only; local peer access eliminated the need to
read a private configuration file. The full integration pass covers existing
snapshot/projection reopening, rollback, lifecycle/recovery conflict handling,
catalog consistency, schema and asset checks; it does not add independent
parallel-writer or platform acceptance scenarios.

## Defect triage

| ID | Classification | Evidence and disposition |
| --- | --- | --- |
| P0-T02-ENV-001 | Missing explicit configuration; resolved | Variables were absent at preflight. A later maintenance-only probe confirmed existing passwordless local peer access with permission to create/drop test databases. Test-only launcher configuration resolves the prerequisite without new credentials or development data. |
| P0-T02-ENV-002 | Sandbox execution limitation; resolved for unit profile | B1/P1 stalled at TestClient startup; D1 reproduced with timeout and stacks. D2 and B2 passed outside the sandbox with the same pins/source. Preserve the interrupted attempts in the evidence. |
| P0-T02-OBS-001 | Non-blocking build observation | Vite bundle exceeds its default 500 kB warning threshold; F3 exits 0. Performance acceptance is outside P0-T02. |
| P0-T02-OBS-002 | Non-blocking dependency deprecation | Pinned Starlette TestClient emits an HTTPX deprecation warning. D2/B2 still pass. Review upgrades separately; preserve this baseline. |

## Limits and follow-up

No test expectations or production code were changed. Passing unit checks do not
prove live-database concurrency, true parallel writers, production readiness,
native CAD correctness, interactive browser/WebGL behavior or Tauri packaging.
No native FreeCAD/STEP execution, browser acceptance suite, desktop build or
installer verification was performed; those are not P0-T02 profiles. Software
verification does not establish manufacturing or standards certification.

Human task acceptance remains a separate decision. No lifecycle state, journal,
history, schema, orchestrator configuration or subsequent task was changed.

All required profiles are verified; no remaining blocking defect ID applies to
this baseline. ENV-001 and ENV-002 are resolved environment findings, while
OBS-001/OBS-002 remain non-blocking observations for later review. Do not infer
acceptance of later lifecycle tasks from this result.

## Reproducible local-peer launcher

Saved source of `/tmp/panelflow-p0-t02-postgres.py` used by P2. Run it only
from `backend/` with the authorized backend interpreter and a local account
permitted to create/drop disposable databases. It does not load secrets from a
file and does not provision PostgreSQL. The two fixture implementations remain
unchanged.

```python
"""Temporary P0-T02 launcher: local peer access, disposable data, cleanup evidence."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import psycopg
from sqlalchemy.engine import URL


def snapshot():
    with psycopg.connect(dbname="postgres", connect_timeout=3) as connection:
        assert connection.execute("SELECT current_database()").fetchone()[0] == "postgres"
        capabilities = connection.execute(
            "SELECT rolcreatedb, rolsuper FROM pg_roles WHERE rolname=current_user"
        ).fetchone()
        assert capabilities and any(capabilities), "Test database creation is unavailable"
        names = {
            row[0] for row in connection.execute(
                "SELECT datname FROM pg_database "
                "WHERE starts_with(datname, 'panel_integration_test_') "
                "OR starts_with(datname, 'panel_policy_upgrade_')"
            )
        }
        return connection.info.server_version, names


assert Path.cwd().joinpath("tests/conftest.py").is_file(), "Run from backend"
server_version, before = snapshot()
print(f"postgres_server_version={server_version}", flush=True)
print(f"disposable_databases_before={sorted(before)}", flush=True)
environment = os.environ.copy()
# Validation-only placeholder: the audited fixtures replace the database name
# before opening every connection. No application/development database is used.
environment["DATABASE_URL"] = URL.create(
    "postgresql+psycopg", database="panelflow_test_config_only"
).render_as_string(hide_password=False)
environment.pop("PANEL_DATABASE_URL", None)
environment["PANEL_RUN_POSTGRES_TESTS"] = "1"
with tempfile.TemporaryDirectory(prefix="panelflow-p0-t02-assets-") as assets:
    environment["PANEL_DATA_DIR"] = assets
    print(f"temporary_panel_data_dir={assets}", flush=True)
    print("child_command=.venv/bin/python -m pytest", flush=True)
    result = subprocess.run(
        [".venv/bin/python", "-m", "pytest"], env=environment, check=False
    )
    print(f"pytest_exit_code={result.returncode}", flush=True)
    _, after = snapshot()
    print(f"disposable_databases_after={sorted(after)}", flush=True)
    print(f"new_disposable_databases_remaining={sorted(after - before)}", flush=True)
    cleanup_ok = after == before
    print(f"fixture_database_cleanup={'PASS' if cleanup_ok else 'FAIL'}", flush=True)
print("launcher_temporary_assets_cleanup=PASS", flush=True)
sys.exit(result.returncode if result.returncode else (0 if cleanup_ok else 1))
```

