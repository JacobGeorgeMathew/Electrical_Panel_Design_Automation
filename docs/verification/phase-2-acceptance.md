# Phase 2 editable document acceptance

P2-T14 · 2026-11-16 · independent quality review. Human acceptance remains required.
Attempt 2 remediation and unresolved scope are recorded below; no lifecycle state or human
decision is changed by this evidence.

## Scope and authority

Prototype Distribution Board (DB) workflows only. CEM owns electrical intent;
PDM owns physical arrangement; schematic pages own presentation referencing stable
electrical identities. Published revisions and managed assets are immutable.
Save never implicitly regenerates, reroutes or publishes. Nonzero rotation remains
unavailable. This review does not establish manufacturing or standards compliance.

## Execution evidence

Baseline: branch `phase_2`, commit `07aec1ef02fc14eb51d12ddc18b76e89164da419`.
Entry retained attempt 1's uncommitted documentation/browser work. Root AGENTS.md was read; a hidden-file search
found no nested AGENTS.md/AGENTS.override.md. The lifecycle was read without edits.
Architecture notes and prerequisite reports were checked against the operation
registry, document service, generation adapter, stores and actual viewer bindings.
Backend and frontend specialists implemented bounded corrections; the quality
engineer independently inspected their final changes and executed final profiles.

| Profile | Command and working directory | Result |
| --- | --- | --- |
| Focused frontend | `frontend/`: focused persistence, Questionnaire, WorkspaceShell, commandStore and operationActions Vitest | Exit 0; 55 passed across five files. After the title typing correction, WorkspaceShell passed 14/14. |
| Frontend unit | `frontend/`: `npm test` | Final exit 0; 108 passed across 25 files, no skips. |
| Frontend build | `frontend/`: `npm run build` | Final exit 0; TypeScript and Vite passed. Initial new tooltip typing failure was corrected; existing large-chunk warning. |
| Browser | `frontend/`: `npm run test:e2e` | Exit 0; 10/10 passed in 1.2 min, no retries/skips. Real Chromium/software WebGL, HTTP and disposable PostgreSQL; cleanup PASS `panel_e2e_82abd588c17f46b081c10e40c55fec5f`. |
| Focused backend | `backend/`: baseline/proposal unit, then phase1/proposal PostgreSQL tests using `.venv/bin/python` | Exit 0; 25 passed/3 database opt-in skips in unit mode; explicit PostgreSQL 17 passed/no skips. |
| PostgreSQL full suite | `backend/`: `PANEL_RUN_POSTGRES_TESTS=1 .venv/bin/python -m tools.run_ci_postgres --junitxml=/tmp/panelflow-p2-t14-attempt02-postgres-full.xml` | Exit 0; 588 passed, 2 opt-in timing skips, 262.95s. Disposable database teardown audit PASS; browser started only after audit completed. |

The PostgreSQL launcher invokes the same backend interpreter with `-m pytest -ra`
against fixture-owned disposable `panel_integration_test_<uuid>` databases and
temporary managed assets. It uses a configuration-only placeholder database and
maintenance access, never application/development data. The interpreter check
printed this repository's `backend/.venv/bin/python` and `backend/.venv` prefix;
pytest reported Python 3.14.8. No environment or dependencies were changed.

The browser profile includes harness type-checking. Prior attempt 1's wire
reselection timeout remains recorded with trace/screenshot/context at
`/tmp/panelflow-p2-t14-browser-initial/`. Independent trace review found a wait for
the SVG edge after replacement while the selected conductor properties were
already visible. React Flow rebuilds nodes/edges and asynchronously measures
replacement handles. The helper now explicitly waits for the rendered path and
bounds each coordinate evaluation before actual pointer clicks. No real pointer
or authoritative-model assertion was removed; readiness is the supported
explanation, not proof that intermittent failures can never recur.

## Workflow coverage

| Workflow | Evidence and observed boundary |
| --- | --- |
| Move / Save / reopen / undo | `physical.spec.ts`: actual SVG drag, one operation on release, unchanged document during gesture; inspector and 3D fields reach identical enclosure-mm PDM coordinates. Save/reopen retains positions and route bytes and emits no generation requests. Undo restores previous PDM. |
| WebGL picking / grouped gesture | `smoke.spec.ts`: real raycast selection and TransformControls drag, one server undo group, unchanged untouched axes, durable PDM read through an independent HTTP GET, undo/redo. Canvas survives fullscreen/resize. |
| Mesh-only negative control | `acceptance.spec.ts`: deliberately shifts the live Three.js object by 25 mm without touching stores or HTTP. Saved PDM and history remain unchanged; the same oracle used by the positive gizmo test rejects the displacement. Reopen removes it. |
| Symbol movement | `schematic.spec.ts`: actual React Flow drag changes page coordinates, preserves CEM hash and PDM, and survives undo/redo and Save/reopen including rendered node coordinates. |
| Electrical connections | `schematic.spec.ts`: real pin drag plus explicit preview/Apply creates a CEM conductor. Duplicate endpoints are rejected without a write. Replace/delete previews identify exact route invalidation and emptied nets; undo restores snapshots. Synthetic endpoint-role evidence qualifies only the fixture. |
| Catalog add/remove | `catalog.spec.ts`: exact published version, unconnected terminal intent and explicit placement; insertion/reopen, preview cancellation and blocked unconfirmed removal; confirmed closure removal and undo restore all models. |
| Automatic proposal | `acceptance.spec.ts`: real API proposal leaves the document/revision list unchanged; explicit acceptance installs the exact candidate in one batch. Exact retry returns the same receipt; stale acceptance is 409. Production viewer Save/reopen and shared undo restore the input-only base, with no publication. This is API acceptance, not a proposal UI test. |
| Concurrency | `smoke.spec.ts`: independent browser contexts race a shared base; loser gets 409, retains local document/proposal and cannot overwrite the winner. Backend operation persistence/history/generation tests also exercise row-lock rechecks, rollback and idempotency. |
| Immutable history / Save purity | Reconciled phase1 tests retain pure Save/recovery/read sentinels and frozen current output after rejected publication. A separate untouched legacy fixture retains two distinct publications, frozen bundles/artifact bytes, restore-to-new-revision, import/duplication and tombstones. No historical assertions were waived. |
| Unsupported rotation | Browser physical controls are disabled. Backend physical-operation tests reject nonzero rotations and attempts to override saved geometry/policy, including invalid placement no-ops. |

## Findings and limits

The independent mutation audit uses the loaded working aggregate as its scope;
the explicit `DOCUMENT_NOT_INITIALIZED` compatibility adapter still retains legacy
overlays and is not claimed to be a shared-operation engineering editor.

| Mutation path | Authority and durable boundary | Fences, history and recovery |
| --- | --- | --- |
| Physical gestures and coordinate fields | PDM; MoveComponent batch, server result installed only after acceptance. Transient mesh/field preview is not durable geometry. | Document ID/S, project L, base revision and PDM hash; one release/field group, shared undo/redo; rejected proposal retained. Recovery can retain unfinished preview, Save cannot promote it. |
| Schematic movement, labels and junction presentation | Schematic page operations referencing CEM identities; no electrical connectivity change. | Same base fences plus schematic hash; one group, exact snapshot history and Save/reopen. |
| Electrical connect/replace/delete | CEM plus dependent page/PDM invalidation; preview then explicit Apply. | All affected model hashes/base fences; retained proposal/key on rejection, exact history snapshots on undo. |
| Component insertion/removal | CEM/PDM/page operations; exact published catalog choice and placement; removal closure requires confirmation. | Affected-model hashes/base fences, one accepted group; cancellation has no write, only returned snapshots installed. |
| Requirement/enclosure input submission | Local unfinished values; explicit input-only document PUT, then metadata PATCH. No CEM/PDM replacement. | L/S and independent recovery R; changed Save advances versions, no operation group. Failed second write retains advanced fence/local input; recover/discard explicit. |
| Automatic proposal | Read-only pipeline candidate; dedicated exact-candidate acceptance writes one shared operation batch. | Candidate digest, document/S/L/base/model fences, idempotency receipt; stale requests rejected, manual models and placement locks retained; no revision/artifact output. |
| Undo/redo and Save/reopen | Server operation history; Save retains accepted snapshots, reopen reads without generation. | Content hash and base fences; durable groups survive reopen, changed input Save can conflict with older history. |
| Display preferences and lifecycle compatibility | Camera/visibility/selection/grid/docks remain display state; metadata/recovery and explicit untouched legacy combined generation use their documented boundaries. | Independent preference persistence or project/recovery fences; not engineering operation groups. Legacy overlays are never presented as authoritative PDM edits. |

1. **Source-pin drift was reviewed and reconciled.** Four existing hashes and the
   new proposal-source hash were updated, with no observed-output, artifact-hash,
   solver/runtime/catalog or semantic expectation changes. The exact review table
   is in [baseline evidence](../../backend/tests/fixtures/design_baselines/README.md#p2-t14-source-pin-review-2026-11-16)
   and attempt 2. Changes are operation/proposal contracts and manual-intent guards,
   not solver, geometry or artifact algorithm changes. The absent intent field
   stays excluded from canonical serialization, preserving earlier hashes.
2. **Saved-input publication expectations now match P2.** Changed-input Save must
   receive `GENERATION_PROPOSAL_REQUIRED` from legacy publication. The independent
   historical test uses untouched input-only compatibility publications; it does
   not imply proposal acceptance publishes. All frontend entry points share the
   eligibility guard, with `Publish unavailable` plus explanation for edited,
   CEM-bearing or intent-bearing documents. The eligible compatibility action says
   `Generate & publish revision (legacy)`. No proposal-review UI or P3 Recompute/
   Publish workflow was invented. Acceptance remains API-only and draft-only.
3. **Literal all-mutation coverage is not met.** Placement, schematic, connection,
   catalog and automatic API changes use shared operations. Questionnaire and
   enclosure forms save input drafts through the document PUT rather than
   `UpdateRequirement`/`ResizeEnclosure` history. The current P1 compatibility API
   explicitly retains that boundary. D01's approved target says structurally valid
   Save uses operations, while retaining current endpoints until rollout. Literal
   P2 acceptance cannot silently waive this conflict. `UpdateRequirement` only
   updates an existing item with a scalar value; new projects have empty items and
   questionnaire values can be structured. `ResizeEnclosure` requires an existing
   PDM and exact published dimensions; input-only enclosure/automatic configuration
   does not fit it. Forcing forms into those operations changes supported semantics.
   Display preferences, recovery and legacy publication have separate owners too.
4. **Draft acceptance is not engineering validation.** Dirty routes/CAD and required
   `UNRESOLVED` checks remain visible. Saved placement policy is enforced; mounting,
   oriented geometry, complete electrical applicability and native CAD validity
   are not qualified here. Labels and supported API/UI operations are listed in
   [CAD_WORKSPACE.md](../CAD_WORKSPACE.md) and
   [PROJECT_LIFECYCLE.md](../PROJECT_LIFECYCLE.md).

Opt-in performance measurement, other browsers/GPU drivers, Tauri installers,
native FreeCAD/STEP and qualified electrical review were not run. Software WebGL
interaction does not establish hardware, native CAD or engineering certification.

## Acceptance recommendation

**Defer phase acceptance pending human scope resolution.** Bounded implementation
corrections and all four passing required profiles do not settle the literal
all-user-mutation criterion. Criterion 1 remains FAIL; criterion 2 is PASS with
immutable-history, unsupported-rotation and pure Save evidence. Two concrete
options are: explicitly clarify it covers supported working-document engineering
edits, retaining separately fenced input Save/recovery/display, legacy adapter and
untouched compatibility publication; or approve a separately scoped operation-backed
input submission/Save/history rollout. Neither decision is inferred here. Preserve
manual-intent guards and zero-physical-violation generation policy. Separate P3
Recompute/Publish remains unavailable, and no subsequent task was executed.

The [new mandatory attempt report](../../planning/task_reports/P2-T14/attempt-02.md)
records exact outcomes, cleanup evidence and the machine-readable assessment.
The [prior attempt](../../planning/task_reports/P2-T14/attempt-01.md) remains intact.
This document is evidence for human review, never human approval.
