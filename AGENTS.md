# Repository guidance

This file applies to the entire repository. Inspect the relevant implementation before changing it; some architecture and status documents describe earlier versions.

## File creation rules

- Never create or modify files using shell heredocs (`cat <<EOF`), `echo`, or `printf` with large content.
- Use the `apply_patch` tool to create and edit files.
- For long documents, create the file with a short skeleton first, then add sections in separate patches of under ~500 lines each.

## Project and code map

Electrical Panel Design Automation is a modular monolith for prototype Distribution Board (DB) design. FastAPI coordinates requirements, calculations, catalog selection, electrical connectivity, schematics, physical placement, duct routing, validation, BOM and CAD output. React provides the project dashboard and CAD workspace. DB is the implemented engineering archetype; do not imply support for other panel types or certified electrical design.

The main contracts are the Canonical Engineering Model (CEM) for electrical intent and the Physical Design Model (PDM) for physical geometry. PostgreSQL stores projects, versioned catalogs, immutable design revisions and artifact metadata; generated files use a managed content-addressed asset store.

| Location | Responsibility |
| --- | --- |
| `backend/app/main.py`, `backend/app/api/` | FastAPI setup, readiness, routes and dependency wiring. |
| `backend/app/models/` | Pydantic requirements, API, CEM, electrical graph and PDM contracts. |
| `backend/app/services/project_service.py` | Application orchestration, database units of work and revision publication. |
| `backend/app/services/project_lifecycle.py` | Project documents, import/export, duplication and recovery. |
| `backend/app/services/orchestrator.py` | Design-stage coordination through `DesignOrchestrator`. |
| `backend/app/services/`, `backend/app/algorithms/` | Engineering stages, OR-Tools CP-SAT placement, duct routing, geometry and validation. |
| `backend/app/persistence/` | Runtime PostgreSQL repositories, mappings, revisions, imports and managed assets. |
| `backend/app/repositories/`, `backend/app/data/` | Legacy JSON adapters and explicit import/unit-test fixtures. These are not an HTTP runtime fallback. |
| `backend/migrations/` | Alembic history and frozen baseline/seed files. |
| `backend/tests/` | Pytest unit and optional PostgreSQL integration tests. |
| `frontend/src/api/`, `frontend/src/types/` | Central HTTP client, readiness checks and TypeScript contracts. |
| `frontend/src/stores/`, `frontend/src/hooks/` | Zustand project/workspace state and recovery behavior. |
| `frontend/src/pages/`, `frontend/src/components/` | Dashboard, questionnaire, workspace, schematic, 2D/3D views, BOM and validation UI. |
| `frontend/src-tauri/` | Active Tauri 2 Rust wrapper, configuration and sidecar lifecycle. The root `src-tauri/` only contains a binaries directory. |

## Setup and development

Use Python 3.10+ and a Node/npm environment compatible with `frontend/package.json`. Backend dependencies are pinned in `backend/requirements.txt`; frontend dependencies use `frontend/package-lock.json`. Match existing formatting and dependency patterns.

Backend commands below run from `backend/` using an activated virtual environment. Create one with `python -m venv .venv` if needed; on Linux activate it with `source .venv/bin/activate`.

```sh
python -m pip install -r requirements.txt
```

Configure `DATABASE_URL` or `PANEL_DATABASE_URL` privately in the process environment. The backend does not automatically load `.env` files. `DATABASE_URL` must target an application PostgreSQL database. When only `PANEL_DATABASE_URL` targets the maintenance database `postgres`, settings select `electrical_panel_design` instead. Do not log or commit connection strings or credentials.

For an intended database setup or upgrade, with a PostgreSQL database already provisioned:

```sh
python -m app.persistence.manage initialize
python -m app.persistence.manage import-legacy
python -m app.persistence.manage seed-constraints
python -m app.persistence.manage status
```

`initialize` upgrades to Alembic head; the inspected head is `0004_projects`, following `0003_constraints`. `import-legacy` includes panel hardware. These commands write to the configured database: use them for setup/upgrade tasks, not as incidental validation for unrelated edits. Preserve existing data and back up valuable databases before migration.

Start the backend from `backend/`:

```sh
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8731
```

`/health` checks process liveness; `/ready` checks database availability and migration readiness. OpenAPI is available at `/docs`.

Frontend commands run from `frontend/`:

```sh
npm ci
npm run dev
```

Vite serves port 3000. `VITE_API_BASE` configures the API client and should include `/api`; the fallback is `http://127.0.0.1:8731/api`. Vite also proxies relative `/api` requests to port 8731. Restart Vite after changing its environment configuration.

For desktop development, run `npm run tauri dev` from `frontend/` and start the backend separately. Release builds launch the packaged `panel-backend` sidecar; they still require PostgreSQL configuration. Sidecar packaging uses `backend/desktop_main.py` and `backend/panel-backend.spec`.

`PANEL_DATA_DIR` controls managed application storage; assets live in its `assets/` directory, defaulting to `~/.panelstudio/assets`. Keep normal runtime assets outside the source tree. Do not commit virtual environments, dependency directories, build output, generated sidecar binaries, backups or private configuration.

## Implementation conventions

- Keep API handlers focused on transport and delegate application/engineering work to existing services. Runtime requests must use PostgreSQL repositories; use explicit fixture adapters for isolated engine tests.
- Keep backend Pydantic models, frontend interfaces in `frontend/src/types/`, API client responses and all affected consumers consistent when changing contracts. Reuse `frontend/src/api/client.ts` for application requests and its normalized errors, cancellation and timeout behavior.
- Preserve stable component, terminal, net, connection and route identities across CEM, schematic, PDM, BOM and revision projections. Physical coordinates use enclosure millimetres; respect the existing mounting-plate offsets and geometry transforms.
- Preserve the placement/routing/validation sequence. The orchestrated physical flow uses `DuctRouter`; disconnected or obstructed duct trunks must fail rather than silently fall back to free-air routing. Keep terminal endpoints and route-to-connection references intact.
- Treat the saved PDM `validation_policy` as the shared policy for backend checks and frontend geometry analysis. Generation requires an empty physical violation list, including warnings. Do not weaken constraints or suppress violations merely to make a design generate.
- Close catalog/project read transactions before optimization, routing or CAD serialization. Publish snapshots, projections, version pins, validation and artifact metadata through the existing short transactional revision writer. A failed generation must preserve the prior revision.
- Saved snapshots and published catalog/model versions are immutable. Reopening reads saved designs without regeneration; restoration publishes a new revision. Keep snapshot hashes and engine/generator version compatibility checks intact. Review version pins when changing generated geometry or engineering behavior.
- Preserve optimistic concurrency using `expected_version`/`lock_version` and the separate recovery version. Conflicts must retain local edits and surface through the existing error path.
- Keep workspace selection, visibility, schematic edits and manual 3D transforms separate from generated engineering revisions. Saving drafts or autosaving recovery must not implicitly regenerate, reroute or publish edited geometry. Preserve browser/server recovery checkpoints and explicit recover/discard behavior.
- Preserve lifecycle semantics: project deletion is a tombstone; import and duplication allocate new identities and verify/rebind historical revisions. Project packages are not database/catalog backups.
- Make schema changes through additive Alembic migrations. Preserve the frozen baseline and historical seed payloads. `backend/app/persistence/models.py` and `baseline_manifest.json` are generated by `backend/tools/build_schema_models.py`; do not edit mappings independently of reviewed migrations. The generator creates an isolated database and requires database administration privileges.
- Keep artifacts in the existing content-addressed asset store, with verified hashes and metadata. Do not replace managed asset URLs with arbitrary filesystem paths or delete historical/shared files. `python -m app.persistence.manage audit-assets` reports asset problems without deleting files.
- Return structured `DesignError`/`PersistenceError` responses through the existing handlers. Keep SQL parameters, credentials and internal filesystem details out of client errors.
- Describe engineering calculations, catalog geometry and thermal/fill limits as prototype assumptions. FreeCAD scripts and GLB previews do not establish manufacturing or standards compliance; native FreeCAD/STEP execution requires separate verification.

## Verification

Choose checks for the changed behavior. For documentation-only changes, verify paths, commands and claims against the source; application test runs are usually unnecessary. For behavior changes, add or adjust focused regression tests and run the relevant suites.

From `backend/`:

```sh
python -m pytest
python -m pytest tests/test_backend.py
```

The first command runs the backend suite; database-dependent tests skip unless explicitly enabled. Unit tests cover model identity, requirements, placement, constraints, wire/duct routing and panel assembly.

To include PostgreSQL API, persistence and lifecycle tests on Linux/macOS:

```sh
PANEL_RUN_POSTGRES_TESTS=1 python -m pytest
```

Use private database configuration and an account allowed to create/drop test databases. `backend/tests/conftest.py` creates a unique `panel_integration_test_<uuid>` database, applies migrations and imports, uses temporary asset storage and removes that database afterward. Never substitute the development database for this fixture. On PowerShell, set `$env:PANEL_RUN_POSTGRES_TESTS='1'` before running pytest.

From `frontend/`:

```sh
npm test
npm test -- src/stores/projectStore.persistence.test.ts
npm run build
```

`npm test` uses Vitest with jsdom; tests live alongside TypeScript/React source. `npm run build` runs TypeScript checking and Vite production compilation. There is no separate configured lint script. For geometry or CAD contract changes, check the affected backend and frontend consumers. Desktop installers, native CAD output and interactive WebGL behavior need relevant platform/manual checks when those areas change.

Report which checks ran, failures and any skipped integration or platform verification. Do not present historical test counts in documentation as current verification.

## Reference documentation

- `README.md`: overview and general workflow; confirm older commands and folder listings against source.
- `docs/PROJECT_LIFECYCLE.md`: current dashboard, saved editor state, recovery, import/export and `0004_projects` migration.
- `docs/CAD_WORKSPACE.md`: workspace layout, menus, viewports and navigation.
- `docs/CONSTRAINT_POLICY_UPDATE.md`: strict placement/thermal policy and seed rollout.
- `docs/PANEL_ASSEMBLY.md`, `docs/WIRING_IMPLEMENTATION.md`: cabinet geometry, duct routing, wire contracts and export details; some version notes are historical.
- `docs/database/OPERATIONS.md`: PostgreSQL configuration, migration/import, revision persistence, assets and integration tests. Its opening migration-head note predates `0004_projects`.
- `ARCHITECTURE_ASSESSMENT.md`, `CODEX_IMPLEMENTATION_ESTIMATE.md`, `PROJECT_STATUS_REPORT.md`: assessments and planning context; verify proposed or historical behavior against current code before implementing it.
