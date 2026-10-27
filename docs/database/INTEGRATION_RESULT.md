# Integration verification

The runtime now uses SQLAlchemy/PostgreSQL repositories, a verified Alembic baseline and additive application migration, imported existing data, managed assets and revision-aware React workflows. The implementation plan is in INTEGRATION_PLAN.md and current operating/deployment instructions are in OPERATIONS.md.

The existing development database was backed up to `.local/backups/before-postgres-integration-20261027T151717280519Z.dump`, and the custom archive was checked with pg_restore --list. Its complete table/constraint/index fingerprint matched the frozen baseline before stamping. Alembic upgraded to 0002_app and its metadata comparison reported no pending upgrade operations. The database was not dropped or recreated.

The import preserved the initial SQL fixture, imported 14 component definitions and four enclosures plus the DB patterns/questionnaire/rules and two saved JSON projects, and left the source files unchanged. Development now has three projects, 24 components/component versions and two archetypes. A pre-existing published INCOMER module version is preserved; the imported module uses a new version under that identity.

Executed checks:

- Full backend suite: 27 passed. The PostgreSQL fixture creates/removes only a unique isolated database, uses temporary managed assets, and exercises migration/ORM consistency, repository and HTTP behavior, snapshots/projections, restoration, rollback, conflicts, parameters, jobs and asset failures.
- Additional PostgreSQL run seeded with the same pre-existing SQL fixture as development: 13 passed, including idempotent import and preservation of published module versions.
- The isolated end-to-end workflow was also run with Node/Three.js GLTFLoader parsing the actual backend-generated GLB: passed. This verifies a real visualization artifact, without mocking its geometry generation or GLB parser.
- Frontend suite: 23 passed across 11 files. TypeScript checking and production Vite build passed. Vite reported its large-bundle advisory; no build error occurred.
- Live FastAPI/Vite checks: readiness READY, three projects, eight questionnaire questions, paginated catalog retrieval, a managed component GLB download with verified SHA-256, restricted CORS origin, and frontend HTTP 200. Missing project GET returned 404 without creating records.
- Git whitespace check completed without errors. Connection values were neither printed nor written/committed to project files. The local backup directory is ignored by Git.

The FastAPI development server was started at http://127.0.0.1:8731 and Vite at http://127.0.0.1:3000 for review. Restart them using OPERATIONS.md if those local processes have stopped.

Verification limits: browser/Windows automation could not initialize because its runtime reported `failed to write kernel assets: The system cannot find the path specified`. No successful visual browser inspection is claimed. DOM tests, live HTTP checks and the actual Three.js loader were used instead. FreeCAD/OpenCascade execution, native STEP/FCStd production, and a rebuilt packaged Tauri installer/sidecar were not exercised; the existing adapter generates primitive GLB previews and FreeCAD Python scripts. Native CAD execution, verified manufacturer geometry, catalog authoring, richer panel engines and durable multi-worker CAD scheduling remain separate extensions. Manual 2D/3D placement edits remain local drafts, as described in OPERATIONS.md.
