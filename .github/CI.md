# Baseline CI

The `Baseline CI` workflow runs on every pull request, push and manual dispatch.
Its four independent checks are **Backend unit**, **Disposable PostgreSQL**,
**Frontend tests** and **Frontend build**, on GitHub-hosted Ubuntu 24.04 runners.
Python 3.14.8, Node 24.18.0, npm 12.2.2 and PostgreSQL 18.6 are pinned to the
measured baseline toolchain; action references use full commit hashes. The runner
image and transitive Python dependencies are not a fully hermetic environment.
Backend installation uses `requirements.txt`; frontend installation uses
`npm ci` and the committed lockfile. No desktop or native CAD qualification is
implied by these checks.

## Repository setup

Create the Actions repository secret `CI_POSTGRES_PASSWORD` with a random
CI-only password. It authenticates **only** the PostgreSQL service created for
that job. Do not use a development/production password, connection string or
external database endpoint. The workflow fixes the service host to loopback and
uses the dynamically assigned service port. Secrets stay in process environment;
the test database URL contains no password. No GitHub settings are modified by
this implementation.

GitHub does not supply repository secrets to fork or Dependabot pull request
runs. Their database service fails without this secret; it is never reported as
passing or conditionally skipped. To verify such a contribution, review it and
run a same-repository branch PR or manual workflow with the secret available.
Do not switch to `pull_request_target` to execute untrusted PR code with secrets.
See [GitHub's secret availability rules](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

## Database isolation and skip policy

The backend unit job explicitly disables PostgreSQL tests and reports their
skips. The database job explicitly sets `PANEL_RUN_POSTGRES_TESTS=1` and runs the
entire backend suite. It also installs frontend dependencies because an existing
integration test validates a generated GLB using Node and Three.js.

`backend/tools/run_ci_postgres.py` reads maintenance metadata on `postgres` and
passes a nonexistent configuration placeholder to the existing tests. The
fixtures replace that database name before connecting: the session fixture owns
`panel_integration_test_<uuid>`; the migration test owns
`panel_policy_upgrade_<uuid>`. Both have `finally` teardown. The launcher compares
all database names before and after pytest, including failed runs, and fails on
leaks or unexpected removal. It never drops additional databases. GitHub removes
the job-local service after the job, including cancellation; no persistent
database volume or external database is configured.

The collection hook in `backend/tests/conftest.py` records database fixture
dependencies in JUnit. The result guard rejects missing/invalid/empty reports,
test failures, absent required database cases and any skipped required database
case. The existing opt-in timing tests alone may skip, with their exact timing
opt-in reason; all skips appear in the summary. The timing exception cannot
satisfy database coverage. Removing the explicit enablement therefore fails the
job even if pytest itself exits successfully after skipping database tests.

## Results and review

Pytest and Vitest produce JUnit XML; each job publishes a result summary and a
14-day result artifact even after test failure. Build logs are published with
the build outcome. Missing result files fail publication. Reports live under
`runner.temp`; application assets also use temporary directories. No build
output, database dump, virtual environment, dependency tree or credentials are
uploaded. The token has only `contents: read`; checkout does not persist it.

Before accepting P0-T09, configure the CI-only secret and execute a sample PR.
Confirm all four checks run, inspect skip reasons/JUnit artifacts and the
database teardown audit, and attach the run URL to the human review evidence.
Local profile runs and static workflow review do not prove hosted PR execution.

Result/teardown guard regressions run in the backend unit lane and can be run
locally from `backend/` with:

```sh
.venv/bin/python -m unittest discover -s ../.github/scripts -p 'test_*.py' -v
```
