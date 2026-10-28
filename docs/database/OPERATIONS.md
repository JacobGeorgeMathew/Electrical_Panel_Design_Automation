# PostgreSQL runtime integration

Current migration head is `0003_constraints` (a data-only rule-policy update). Existing installations must run `manage initialize`, `manage import-legacy`, then `manage seed-constraints` before starting the updated backend. See [strict-constraint rollout](../CONSTRAINT_POLICY_UPDATE.md) for Windows/Linux commands, rule versions and preservation of historical designs. Older `0002_app` backups remain restorable but require this forward upgrade with the current code.

The FastAPI application now uses PostgreSQL repositories. The original JSON files remain import sources and explicit unit-test fixtures; HTTP requests do not fall back to them. React continues to call FastAPI and never receives database connection settings.

## Configuration and startup

Install the existing backend dependencies with `backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt`. The pinned additions are SQLAlchemy 2.0.55, Alembic 1.20.1, Psycopg 3.3.6 and HTTPX 0.28.1. There is no backend lockfile in this repository; requirements.txt is the dependency source.

Configure `DATABASE_URL` for the application database, or reuse `PANEL_DATABASE_URL`. If the latter points to the `postgres` maintenance database used during provisioning, the application targets `electrical_panel_design` on that same server. An explicit DATABASE_URL must already target an application database. Configuration reads process environment variables and, on Windows, user environment variables. Neither the app nor management commands print the URI. Files named `.env` are not loaded automatically.

Optional variables: `DATABASE_POOL_SIZE` (5), `DATABASE_MAX_OVERFLOW` (5), `DATABASE_CONNECT_TIMEOUT` (5 seconds), and `PANEL_DATA_DIR` (default `{user_home}/.panelstudio`). Assets live under `{PANEL_DATA_DIR}/assets`. Use a data directory outside the source checkout for normal use. Credentials stay in environment configuration outside the executable and repository.

From `backend/`:

```powershell
.\venv\Scripts\python.exe -m app.persistence.manage initialize
.\venv\Scripts\python.exe -m app.persistence.manage import-legacy
.\venv\Scripts\python.exe -m app.persistence.manage status
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8731 --reload
```

From `frontend/`, run `npm ci` if dependencies are not installed, then `npm run dev`. Vite uses the existing port 3000. `npm run tauri dev` uses the development backend you start yourself. The existing release sidecar starts FastAPI on loopback port 8731, sets PANEL_DATA_DIR to the Tauri app data directory, and inherits connection configuration. Its packaging includes the PostgreSQL driver/dialect imports. Rebuild the sidecar with the existing PyInstaller workflow when distributing this change.

`/health` is process liveness. `/ready` returns 200 only when PostgreSQL is reachable and Alembic is at the required application revision. React waits for readiness with a bounded timeout, supports retry, and retains unsaved edits when later API calls fail. Missing configuration, unavailable PostgreSQL and missing migrations produce safe 503 responses. HTTP error bodies omit SQL parameters, credentials and internal file paths.

## Database creation and migrations

The development database is `electrical_panel_design`. To create another development database, use PostgreSQL's `createdb` with an interactive password prompt or configured PGSERVICE/PGPASSFILE, then configure the application database URI locally. Do not paste credentials into tracked scripts or command history. Use a separate database owner for administration and an appropriately restricted runtime role for deployments; catalog APIs are read-only and project operations cannot edit published catalog definitions.

There was no pre-existing Alembic history. `0001_baseline` freezes the original `docs/database/001_core.sql`; `0002_app` adds project archetype/current revision/configuration/version fields, a unique draft requirement index, and terminal endpoint FKs on existing conductors. It preserves existing tables and records. There is no automatic `create_all()` and no automatic database recreation.

`manage initialize` handles two cases:

- Empty database: apply the frozen baseline and then later migrations.
- Existing unversioned database: compare every table's column names/types/nullability/defaults, PKs, unique/check constraints, foreign keys and indexes with the baseline manifest. Stamp baseline only when the structures match, then apply the additive migration. A mismatch stops the operation and lists differing tables.

The manifest and static SQLAlchemy mappings are generated from an isolated PostgreSQL database by `backend/tools/build_schema_models.py`. Mappings cover all 78 original tables and the additive fields; selected ORM relationships are declared for projects/revisions, component terminals, CAD parameters and validation results. The SQLAlchemy Core table mappings are also used for efficient DTO queries. Do not edit the generated mapping file independently of the migrations.

Routine migration commands from `backend/`:

```powershell
.\venv\Scripts\python.exe -m alembic current
.\venv\Scripts\python.exe -m alembic history
.\venv\Scripts\python.exe -m alembic revision -m "describe additive schema change"
.\venv\Scripts\python.exe -m alembic upgrade head
.\venv\Scripts\python.exe -m alembic check
```

Review generated/autogenerated migration proposals before applying them. Back up before any potentially destructive migration using `pg_dump --format=custom --file <backup-file> <database-name>` with credentials supplied through PostgreSQL's external configuration. Verify the backup and a restoration plan. Destructive downgrades are deliberately refused by the included migrations. The development migration does not drop/recreate the existing database.

## Legacy data import

`manage import-legacy` imports components, terminals, mounting, clearances, thermal data, enclosures, parametric preview definitions, product identities, the DB archetype/modules, questionnaire/options/dependencies, connection-template roles, rule metadata and the existing saved projects. IDs are stable UUIDs derived from source identities. Original human-readable project codes remain usable in API paths. Import does not change the source JSON files, overwrite an existing project, or mutate an imported published component version. Repeating the import leaves version counts unchanged. A changed component source hash requires an explicitly published new version.

Imported specifications and rule thresholds retain their prototype/unverified provenance. The import generates actual GLB assets using the current box geometry adapter. Old `.step` names in JSON are recorded as source hints; they are not registered as existing files. The earlier SQL-only DB_BASIC example remains preserved as a reference fixture and is disabled in the executable project selector because its snapshots/hashes were illustrative rather than engine output.

## Projects and revisions

Projects retain working answers and engineering requirements separately. Hidden conditional answers are preserved through requirement-source links even when their corresponding requirement is not applicable. A project-specific enclosure configuration is saved under projects.configuration and pinned again in each revision manifest. Configurable prototype enclosure dimensions are validated against their CAD parameter definitions. Purchased fixed parameters are rejected as overrides.

The engine consumes materialized repository data. Read transactions close before optimization, routing or CAD serialization. Revision publication opens one short write transaction that checks the project's expected lock_version, then writes the revision header, answer provenance, requirements, full CEM/PDM snapshots, electrical instances/terminals/nets/conductors, physical placements/routes, model pins, validation runs/results, dependency edges and artifact metadata. A failure rolls back the complete revision. The transaction also updates the current-revision pointer and increments lock_version. Concurrent saves based on an old version return 409.

Snapshots are authoritative at their pinned schema version; projections are derived from the same in-memory DTOs in that transaction. No API independently edits published projections. Reopening verifies canonical JSON SHA-256 and reads the saved snapshots; it does not optimize again. The CEM graph's panel-root terminal interface is projected explicitly without adding a purchased BOM item. Stable logical keys remain the same across revisions while row UUIDs identify revision-specific projections.

Restoring creates a new revision from a verified historical snapshot, preserving old revisions and shared file references. It restores the corresponding answers and enclosure configuration. Electrical or enclosure edits mark the saved design stale until explicit generation publishes the next revision. Visual selection/visibility/explode/editor drafts stay in Zustand and do not trigger electrical optimization. The existing placement validator remains advisory for local editor drafts; it does not publish manually moved geometry or reroute wires.

## API changes

Compatible routes retained: requirement questions/validation, design/generate, design/propagate-change, design/validate-placement, schematic, layout, validation and CAD/freecad-script. GET views now use saved revisions. Missing project GET returns 404 instead of creating demo data. New project IDs are UUIDs; existing imported human-readable IDs remain accepted. POST projects returns 201.

New routes provide paginated component search/filtering/details/versions/CAD/accessories, archetype/questionnaire/template/rule retrieval, project PATCH, answers GET/PUT, structured requirements GET, revision listing/create/read/restore, design GET, catalog asset metadata/content, generated artifact metadata/content, project artifacts, and CAD export jobs. The OpenAPI document at `/docs` describes requests and responses. Mutation requests from React include expected_version; the legacy design/generate route also accepts an optional expected_version query parameter.

The centralized TypeScript client provides typed responses, timeouts, cancellation and normalized errors. Zustand distinguishes saved requirements, local edits, revision identity, stale design state and export status. Catalog search uses server filtering and pagination with cancelled obsolete requests. Project controls save, close, reopen and restore revisions. Unsaved edits block opening/closing/restoring until explicitly saved or discarded.

## CAD assets, files and recovery

Detailed cabinet hardware and physical duct routing are available in engine `db-pipeline-2` and primitive generator 2. After updating an existing installation, run `python -m app.persistence.manage import-panel-hardware` from `backend/` with private database environment configuration. Full `import-legacy` also runs this additive hardware import. No new tables or destructive schema changes are required. Version 1 catalog/CAD records and saved revisions remain preserved. Generate a new revision to receive the new geometry and ducts. See [panel assembly details](../PANEL_ASSEMBLY.md).

The file store uses relative content-addressed keys `sha256/aa/bb/<hash>.<format>`. Files are written to a temporary name, flushed, hashed, atomically moved and verified before metadata is registered. Filesystem writes cannot join the DB transaction; a failed database commit can leave a harmless unreferenced content file. `python -m app.persistence.manage audit-assets` reports missing/corrupt and unreferenced files without deleting engineering history. Restore a missing file from backup or regenerate a compatible saved revision. Automatic file deletion requires an explicit retention policy.

Asset/content endpoints resolve UUIDs through database records, restrict resolved paths to the managed root and verify size and SHA-256. Their responses contain application URLs rather than filesystem paths. Metadata alone does not make an asset available. Assets marked READY but absent/corrupt are reported as unavailable and content retrieval returns 404.

The existing primitive exporter produces GLB previews and FreeCAD Python scripts. GLB has node metadata linking the CEM/PDM IDs; GLB vertices are in metres while PDM coordinates remain millimetres. Component preview meshes have their origin at their centre. The current viewer's world unit is 100 mm, so GLB metre coordinates use a scale of 10 when placed in that viewer. Scene nodes are cloned per component and the cached source meshes/materials are not mutated. The saved assembly GLB is available as an optional preview and download; editor state continues to derive from PDM.

POST cad-generation registers a PENDING artifact and returns 202, then the local worker builds from a saved revision, verifies/stores its output, and updates status to READY or FAILED. Polling is bounded in React. Restarted desktop backends mark interrupted pending jobs FAILED so they can be explicitly retried. This worker is intended for one backend process. A shared multi-worker deployment needs a durable job-claim/worker design before enabling multiple processes. No PostgreSQL server or background distributed service is bundled here.

Generated native FreeCAD/STEP solids have not been exercised by this integration. FreeCAD/OpenCascade execution and richer source assets require their own installed adapters. STEP and GLB do not preserve a native parametric feature tree. Historical export regeneration is rejected when its required generator version is unavailable; preserved artifacts can still be downloaded when their files pass integrity checks.

## Checks

From `backend/`, run `python -m pytest` for unit checks and `PANEL_RUN_POSTGRES_TESTS=1` with `python -m pytest` to include the PostgreSQL suite. On PowerShell, set the environment variable in the process before the command. Tests create a uniquely named `panel_integration_test_<uuid>` database, apply migrations/import, use temporary asset storage and remove only that generated database afterward. They never drop or truncate the configured development database. The administrative connection must permit creation of isolated test databases.

From `frontend/`, run `npm test` and `npm run build` (TypeScript checking plus Vite build). Tests cover request failures/timeouts, catalog filters, conditional questionnaire rendering, saved project reopening, optimistic version submission, preservation of unsaved edits and CAD job status in addition to the existing editors. There is no configured separate lint script. Desktop installer/sidecar rebuilds and real FreeCAD execution need platform verification before release.

## Deployment decisions

Development connects to the configured local PostgreSQL service. Desktop deployment requires a separately installed/configured PostgreSQL service and external credentials; a clean machine without that service displays a readiness error. Shared deployment may use a managed or self-hosted PostgreSQL service behind FastAPI. Fully standalone offline desktop distribution without a database prerequisite remains an explicit deployment decision. This integration neither bundles PostgreSQL nor substitutes SQLite. The existing Tauri CSP and loopback sidecar remain in effect; a remote API deployment must explicitly configure its allowed origin/CSP.
