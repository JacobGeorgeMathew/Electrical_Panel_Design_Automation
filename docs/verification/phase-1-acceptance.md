# P1 document lifecycle and historical invariance

PanelFlow · P1-T11 · quality_engineer · 2026-11-16.

## Recommendation and authority

**Recommend bounded P1 acceptance:** both task criteria and all three required
profiles pass. Human task acceptance remains required; this document is evidence
and a recommendation, never approval or release qualification. The existing
working-open preview gap and unrun platform checks remain explicit below.

Reviewed branch `phase_1`, HEAD `dbf463bce8668fefca74f930df223635e3ed1297`,
including the existing uncommitted P1-T10 integrity implementation. The read-only
[lifecycle](../../planning/development_lifecycle.json) assigns independent
regression, consistency, concurrency and end-to-end acceptance to quality_engineer.
The supplied human acceptance records for P1-T06–T10 were checked against their
report hashes; all five match. No lifecycle/execution state was changed.

This acceptance is bounded to prototype Distribution Board document persistence
and frozen publications. The [approved D01 scope](../decisions/approved-product-scope.md)
and [P0 acceptance](phase-0-acceptance.md) retain later engineering, operation,
native CAD, hosted CI and release obligations. Older ADR/current-contract tables
describe pre-P1 behavior; the source and fresh tests below control this review.

## Exercised lifecycle

The new [acceptance regression](../../backend/tests/test_phase1_acceptance.py)
follows one project through create, first publication, recovery, changed draft
Save, second publication under a changed engine pin, frozen current/historical
reads, restore, export/import, duplicate and tombstone. Backend exercise uses
FastAPI TestClient and actual disposable PostgreSQL/managed asset storage.
Frontend exercise uses jsdom/Vitest with mocked API responses, independently of
the backend. This is not a live browser-to-server acceptance run.

| Action / guarantee | Executed regression evidence |
| --- | --- |
| Create, Save, reopen | New project has no revision. Save retains document/panel identity, increments document sequence and project lock, changes the engineering hash and leaves the current publication unchanged. `test_create_empty_save_reopen_after_backend_restart` reopens saved metadata/answers with a new app instance. |
| Save concurrency | `test_save_open_conflict_and_no_engines` submits two writes at the same project/document fences: one 200, one structured 409, retained losing payload, no-op Save unchanged and no revisions. New acceptance test also rejects stale Save after an existing publication. |
| Recovery and explicit Recover | Backend checkpoint preserves raw unfinished input, original base and independent R; concurrent same-R writes produce one winner/one `RECOVERY_CONFLICT`. Document Save preserves checkpoint/R. New frontend regression explicitly recovers compatible v2 input/transforms, autosaves and Saves with zero routing/generation/export calls. Browser/restart, incompatible bases and late-response regressions also run. |
| Publish and failure | Explicit generation publishes complete snapshots and pins. The new test captures the saved source-document hash and publishes a second revision after changing the engine pin. Existing frontend tests require Save before Publish, pass saved inputs and reject publication of manual overlays. `test_each_database_write_rolls_back_and_publication_has_no_engine_work` and document/project fence tests preserve the prior revision on failure. |
| Open old and current | Both are compared separately to their own captured outputs/hashes/bytes under raising generator, orchestrator and router sentinels; see the next section. Dedicated schematic/CAD/script GETs are covered by `test_historical_reads_use_exact_snapshots_and_original_artifacts`. |
| Restore | One new revision, new revision/artifact metadata IDs, source link and pre-restore parent; exact frozen representations and original asset bytes. Stale restore returns 409 without another publication. `test_restore_adds_one_revision_preserving_all_original_hashes` compares all original revision/model/output/artifact rows. |
| Import and duplicate | New project/document/panel/revision/artifact identities; stable CEM components/terminals/nets/connections and PDM routes remain intact. Output and artifact hashes are retained where ownership does not change. Cross-installation package test uses separate disposable databases and asset roots with generators disabled. |
| Delete | Stale lock rejected; fresh delete tombstones the source, hides it from listings/routes, retains original bundles/bytes and leaves the duplicate usable. Integrity tests inspect retained rows and audit tombstoned history. |
| Corruption / atomicity | Revision/package/integrity suites reject missing anchored bundles, hostile references/pins/schemas, altered hashes/artifacts and unsafe paths with structured redacted errors. Invalid packages create no project/assets; injected later database failure rolls back project history, possibly retaining verified unreferenced blobs. |

Primary supporting suites:
[PostgreSQL workflow](../../backend/tests/test_postgres.py),
[project lifecycle](../../backend/tests/test_project_lifecycle.py),
[document API](../../backend/tests/test_documents_api.py),
[revision reader](../../backend/tests/test_revision_reader.py),
[revision publication](../../backend/tests/test_revision_outputs.py),
[portable packages](../../backend/tests/test_project_package.py),
[publication integrity](../../backend/tests/test_revision_integrity.py),
[frontend persistence](../../frontend/src/stores/projectStore.persistence.test.ts).

## Current and historical outputs

The new regression captures r1 from four-feeder input and r2 from five-feeder
input. The installed engine pin changes before r2 publication. After both are
published, installed generators are disabled and the engine pin differs from
both publications. The test separately compares each read's CEM, PDM, schematic,
BOM, CAD, validation, revision digest, full output manifest and manifest digest
with its own original, then verifies downloaded artifact bytes. It does not
compare r1 to r2 as though different designs should have equal hashes.

| Read | Pointer status | Input status | Installed version status | Output |
| --- | --- | --- | --- | --- |
| Current `/design` for r2 | `is_non_current=false` | `is_input_stale=false` | `is_version_incompatible=true` | Exact r2 frozen values and original bytes; COMPLETE. |
| Explicit `/revisions/{r1}` | `is_non_current=true` | `is_input_stale=true` | `is_version_incompatible=true` | Exact r1 frozen values and original bytes; COMPLETE. |
| After saved inputs match r1 again, existing reader regression | r1 still historical; r2 current | r1 no longer input-stale; r2 input-stale | Independently flagged | No reconstruction; currentness and input staleness are independent. |

The backend input-stale flag compares the publication to legacy saved project
answers/configuration. Working aggregate inputs have independent authority: the
frontend also compares saved draft values/source-document hash and overlays to
label dirty output. A document Save does not imply a current engineering output.

Restoration deliberately creates a different revision digest/manifest because
new revision/source/provenance metadata is captured. Import/duplication also
rehash ownership-bearing CEM/PDM/document/manifests. Neither operation promises
the source revision root hash for the new publication. Original rows and hashes
are retained; packages preserve exact source evidence in
`DOCUMENT.portable_source`. Unchanged SCHEMATIC/BOM/CAD/VALIDATION snapshots and
artifact bytes retain their hashes, as tested in the cross-installation suite.

## Supported v1 compatibility

"v1" has several independent meanings; package v1 is not a complete-output
manifest or working-document schema guarantee.

| Boundary | Supported behavior |
| --- | --- |
| Project package `version: 1` | Importable CEM/PDM-only history, explicitly `MISSING_OUTPUTS`, null schematic/CAD/BOM, no transported artifacts and recorded `legacy_package_limitations`. Import never regenerates missing representations. Re-export/reimport through v2 preserves absence. |
| Older database revision without complete bundle | Allowed only when neither output root anchor nor output rows exists. Original CEM/PDM and revision hash remain readable; existing verified script bytes remain available if actually saved. Ordinary restore refuses missing outputs with 409. |
| Explicit compatibility conversion | Version-fenced POST creates a new complete revision using installed generators, records `compatibility_converted_from_revision_id`, retains source snapshots/hash/missing-output status. Newly generated outputs are not claimed as historical bytes. This action is the deliberate exception to generator-free reads. |
| Complete model/output envelopes | Revision/CEM/PDM and per-output envelope integer `1`; manifest schema `1.0.0`; captured working aggregate `1.0.0`. Unsupported envelopes, missing anchored data or hash mismatches fail closed with `REVISION_OUTPUT_INTEGRITY`, rather than being treated as legitimate legacy absence. |
| Legacy recovery and new recovery | Unversioned existing checkpoints remain readable without byte migration; new envelopes/documents use schema `2`. Unknown/incompatible checkpoints stay pending for explicit resolution or Discard. Independent recovery R fences writes; original L/S/revision remain base evidence. |
| Missing working aggregate | Frontend uses the legacy adapter only for explicit `DOCUMENT_NOT_INITIALIZED`. Network, integrity and unknown-schema failures preserve local data and surface errors. |

Actual v1/conversion checks are
`test_v1_import_is_explicitly_incomplete_and_never_regenerates` and
`test_legacy_reads_never_invent_outputs_and_conversion_is_explicit`.
Complete bundles remain readable under changed installed versions when their
saved envelopes are supported. Requests to create a fresh CAD export under an
unavailable pinned generator are separately rejected; existing download/read
access is not replaced with installed output.

## Verification evidence

Fresh checks after the final test edits:

| CWD | Command | Outcome |
| --- | --- | --- |
| `backend/` | `PANEL_RUN_POSTGRES_TESTS=1 .venv/bin/python -m tools.run_ci_postgres --junitxml=/tmp/panelflow-p1-t11-postgres.xml` | Exit 0; 346 passed, 2 optional timing skips, one Starlette deprecation warning; 213.81 s. Disposable database teardown audit PASS. |
| `backend/` | `DATABASE_URL=postgresql+psycopg:///panelflow_test_config_only PANEL_RUN_POSTGRES_TESTS=1 .venv/bin/python -m pytest -q tests/test_phase1_acceptance.py --junitxml=/tmp/panelflow-p1-t11-focused-postgres.xml` | Exit 0; 1 passed, one Starlette deprecation warning; 10.80 s. |
| `frontend/` | `npm test -- src/stores/projectStore.persistence.test.ts --reporter=default --reporter=junit --outputFile=/tmp/panelflow-p1-t11-frontend-focused.xml` | Exit 0; 23 passed. |
| `frontend/` | `npm test -- --reporter=default --reporter=junit --outputFile=/tmp/panelflow-p1-t11-frontend.xml` | Exit 0; 83 passed across 21 files, no skips; 9.97 s. |
| `frontend/` | `npm run build` | Exit 0; TypeScript and Vite production build passed; bundle-size warning. |

The repository JUnit validator passed for both full XML files. With
`--require-postgres`, it confirms 46 required database cases executed without
skips; only the two opt-in timing measurements skipped. Final report structure,
all document links and preserved lifecycle/prerequisite hashes also passed checks.

Backend interpreter preflight confirmed the repository's `.venv/bin/python`
and `.venv` prefix (Python 3.14.8 in executed pytest). No environment or dependency
was installed or altered. PostgreSQL commands use private libpq authentication;
the displayed database URL is a nonexistent configuration placeholder, not an
application/development database. Fixtures alone provision unique
`panel_integration_test_<uuid>` databases and temporary assets. The full-profile
launcher delegates to this interpreter's full `-m pytest -ra` with the profile
flag and audits database names before/after. No development data was used.

The initial sandbox database preflight failed; approved escalation enabled local
socket access. Initial new test setup errors (backend helper import; frontend
workspace fixture missing saved schematic data) were corrected without changing
production code. The [attempt report](../../planning/task_reports/P1-T11/attempt-01.md)
records all exits and final evidence. `/tmp` JUnit files are local execution
artifacts, not versioned fixtures; retain them with the review evidence.

## Boundaries and remaining obligations

No unresolved defect against the two bounded P1-T11 criteria was demonstrated
by the passing full checks. The following existing limits must remain explicit
for later work and human review:

- Publish still combines automatic computation and publication. Separate
  Recompute/Publish services, authoritative manual geometry operations and
  working-state rebase are not delivered by P1. Manual placement/schematic
  overlays cannot silently become engineering publications.
- Document PUT and overlay PATCH are sequential, not atomic. A failed overlay
  write retains advanced document fences and local edits; tests cover this case.
  Document PUT retains server recovery; legacy overlay/full Save and publication
  retain their existing recovery-clearing behavior.
- Current working-view `openProject` still calls placement validation for saved
  transforms, producing a nonpersisting preview reroute. This predates P1 and
  remains a gap against D01's broader no-reroute-on-ordinary-open direction.
  Explicit historical `viewRevision` uses frozen reads and blocks rerouting.
  Save, autosave and explicit Recover themselves invoke no reroute. This review
  does not claim every working-view open is computation-free.
- No live browser/backend workflow, interactive WebGL, packaged Tauri installer,
  native FreeCAD/STEP execution, hosted CI, Windows/macOS/ARM, performance budget
  or deployment database-role qualification was run. Functional tests use the
  existing Linux environment; optional timing tests are not latency evidence.
- Application immutable-write guards cover supported SQLAlchemy paths, not
  privileged raw SQL/filesystem administrators. Session/tenant authorization
  remains absent and separately scheduled; CORS is not authentication.
- DB calculations, catalogs, thermal/fill assumptions and generated previews
  remain prototype evidence. Physical validation and preserved hashes establish
  neither engineering approval nor manufacturing/standards compliance.

Human review should assess the bounded P1 criteria and retain the working-open
preview gap for the document/open lifecycle work before claiming D01/MVP
completion. No subsequent lifecycle task was executed or authorized here.
