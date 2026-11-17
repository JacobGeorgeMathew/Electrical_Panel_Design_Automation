# Document-centric DB MVP acceptance evidence

P3-T14 · quality_engineer · 2026-11-17 · source `2971f6ae189e2761b55a6fe33bb2c7c9a3c994e2`, branch `phase_3`, plus the scoped changes recorded here.

## Recommendation and authority

**Do not accept the complete document-centric MVP yet.** Successful working-draft
generation, movement and recomputation do not complete the required successful
Publish/export path. Current required engineering evidence remains unresolved and
publication correctly fails closed. Both boards also miss the measured cached-open
and job-acknowledgement budgets. These are blocking acceptance gaps; no scope
exception is approved here. This document grants no task acceptance,
engineering release or certification. Human acceptance remains required.

## Scenario evidence

The new [MVP regressions](../../backend/tests/test_mvp_acceptance.py) passed for
both D01 boards in a fresh disposable PostgreSQL fixture: **2 passed**, exit 0,
100.90 s. JUnit with captured evidence: `/tmp/panelflow-p3-t14-mvp.xml`.

Both scenarios run initial automatic recompute and explicit acceptance, commit one
`MoveComponent`, recompute and explicitly accept the candidate, Save, reopen,
attempt protected Publish, export a working project package, then durable undo/redo.
The rightmost DIN component moves +1 mm in X: `QF011` to `(536, 255, 40.5)` mm
for `db-12`, `QF002` to `(676, 260, 45.5)` mm for `db-16`. Inventory assertions
require 29 components/44 routes and 37 components/56 routes respectively. CEM stays identical;
routes, physical validation and CAD each execute once. Calculation and netlist
entry points are replaced by raising sentinels for the movement recompute: **zero
calls**. Candidates leave the working document unchanged until accepted. Reopen
compares the entire resolved aggregate; undo/redo compares complete snapshots.
Physical violations are empty after recompute. The aggregate report is still
`UNRESOLVED`; Publish returns **409 `PUBLISH_STAGE_STALE`**, leaves the document
unchanged and creates **zero revisions**. The package digest is independently
recomputed from its canonical payload, and its entire `working_document` must
equal the saved aggregate. This demonstrates a working-document
package, not a published edited-design CAD export.

| Evidence | `db-12` | `db-16` |
| --- | --- | --- |
| Project | `e4907ba1-c34b-4c6f-9c0a-9619905cdbb5` | `cce1fcc9-afb1-4251-b1b1-c064ef4411f5` |
| Document | `6e32d248-701e-489e-8e0e-4479fb5bd4fe` | `e4b18407-b67b-4940-8507-b63ca6b2b035` |
| Content SHA-256 | `7215b31ef0e29d47f9b0280d75831eda965ebe87d3aef72afb821f8978f1cbc5` | `42e555f41a78d72ec6c750e21860579dcf189dc5e98ccbd6fb04e4d811397085` |
| CEM SHA-256 | `f25cab07bc2d1af55d685e2318ac9d0cefdbb168c092d342998ebecdd05759be` | `2f36571bf15e7dc35a060749d68230d8c2be412e233ac0c951a75d2b6d580bc1` |
| PDM SHA-256 | `d61521acc267d2f6c1c9bc7312587c3f6d45d0138666124e977132a127d3fe28` | `72f6ed2cce2dc4e0444b5635c5a9e4073da49c729d59af226e9c4241ee508ddb` |
| Schematic SHA-256 | `775e3a326b3c33ec7491ceb2947729d4475282dd865c3d097bf0ed1aa771919e` | `f1fee765adb8a02c349a504d01e030b524a46a4c1f6461ed7164b086537aa9ee` |
| Project package SHA-256 | `e31c02b441588874ed2bd02a665780b455871364b0726aa93e18db47e96b8168` | `dbf6773780854b4f98e1409c49b6392acc94b71917779bb0f762ea1e2c99c425` |

Hashes retain allocated project/document identities, order, geometry and numeric
precision. No field normalization is used and no cross-project hash equality is
claimed. Captured `MVP_ACCEPTANCE` JSON also includes report and per-stage input
signatures, execution statuses/counts and the operation receipt batch ID. Stage
elapsed times are functional evidence rather than D01 latency measurements.

The validation panel's former “All Design Constraints Passed Cleanly!” text has
been replaced by a statement limited to implemented physical checks, with a visible
unresolved-engineering/non-certification notice. A new regression renders the
actual panel with an empty physical violation list and verifies that qualification.
The full frontend suite passes **136/136**. Publication controls remain disabled
for protected documents; the server remains the authority.

The full isolated PostgreSQL suite passed **887 tests**, with **two explicit
opt-in legacy timing skips**, zero failures/errors, exit 0, 1,485.50 s. Evidence:
`/tmp/panelflow-p3-t14-postgres.xml`; disposable database teardown audit **PASS**.
It collected the existing 889 cases before the two new MVP cases were added;
the separate two-case run above verifies those additions. No development database
was substituted. Functional run elapsed times are not latency qualification.

| Additional required scenario | Full-suite evidence |
| --- | --- |
| Historical revision/export | `test_revision_reader.py::test_historical_reads_use_exact_snapshots_and_original_artifacts`: two explicitly seeded legacy historical revisions, changed installed generator pins, raising generation/routing/CAD sentinels, equal canonical CEM/PDM/schematic/CAD/BOM/validation snapshots, equal manifest/package digests and artifact bytes. Export reads both frozen revisions. Separate legacy-missing-output tests require explicit missing/conversion behavior. Seeded history is not successful current runtime publication. |
| Historical restoration | `test_phase1_acceptance.py` and revision/lifecycle tests restore into a new revision and preserve old snapshot/output bundles. No historical revision is rewritten. |
| Recovery/restart | `test_project_lifecycle.py` and `test_phase1_acceptance.py`: unfinished drafts survive application restart; independent L/S/R fences, competing recovery writes, incompatible bases and explicit discard preserve snapshots without generation/routing. Frontend persistence/recovery tests verify browser checkpoints, recover/discard, late responses and conflict retention. A separate real-browser recovery-dialog scenario was not added; browser job-reload recovery is covered above. |
| Concurrency and worker failure | All P3-T13 operation races, lost acknowledgements/restart, stale previews, lease/crash/cancellation recovery and corrupt-cache tests ran successfully in this fresh full profile. Full/incremental comparisons retain expected reconciliation failures and compare retained BOM/CAD rather than omitting them. |

The final full real-browser suite passed **13/13**, exit 0, 4.9 min, with actual
Chromium/software WebGL, one worker, no retries and an isolated backend. Cleanup
passed for owned database `panel_e2e_4ae165cb9a7d47f39f614e2de85bd27a`.

| Required scenario | Actual evidence and boundary |
| --- | --- |
| WebGL movement and linked selection | `e2e/smoke.spec.ts`: actual picking, TransformControls X drag, durable PDM comparison, fullscreen resize, undo/redo, command exact retry and stale-context conflict. `e2e/physical.spec.ts`: 2D, inspector and 3D coordinates, operation counts and Save/reopen. Mesh-only fault injection must fail the same authoritative-PDM oracle. |
| Graphical/electrical edits | `e2e/schematic.spec.ts`: symbol drag preserves net hashes; presentation undo/redo and reopen; real pin gesture with explicit synthetic PE-domain evidence; duplicate endpoints, cancelled edits and unconfirmed changes do not write. Replace/delete preview reports exact route invalidation and emptied nets. This fixture supplies synthetic evidence, not general electrical applicability. |
| Catalog editing | `e2e/catalog.spec.ts`: exact published version, explicit placement, unconnected terminal intent, saved reopen, confirmed dependency closure removal, cancellation and undo. |
| Automatic generation | `e2e/acceptance.spec.ts`: real proposal API, review/explicit acceptance, exact retry, stale rejection, Save/reopen and one shared undo group. This uses API proposal review rather than claiming a complete automatic-generation UI. |
| Durable recompute and reload | `e2e/jobs.spec.ts`: 202 acknowledgement leaves the document unchanged, reload resumes tracking, explicit reviewed Apply, old-base rejection retains a newer physical edit, cancellation and explicit retry. |
| Local session | `e2e/local-session.spec.ts`: real bootstrap/rotation, unauthenticated write rejection and hostile-origin rejection. This is a bounded local boundary, not multi-user authorization. |

An earlier run passed 12/13 but timed out waiting for Apply after Vite reloaded the
changed validation component. Its screenshot shows the console on Validation and
the job `SUCCEEDED`, rather than a failed job. Raw failure traces/screenshots are
retained at `/tmp/panelflow-p3-t14-browser-initial/`; the subsequent complete run
passed without retries. A separate attempted rerun was denied a sandbox loopback
listener (exit 1); the approved outside-sandbox rerun supplied the final evidence.

## Performance evidence

The controlling protocol is [D01](../decisions/approved-product-scope.md#approved-reference-limits-and-initial-performance-targets),
including the exact `db-12` and `db-16` reference inputs. The lifecycle still labels
its initial candidates proposed; the recorded human D01 approval supplies the
approved 33 ms / 2,000 ms / 500 ms budgets. Historical P0 timings use different
intervals and cannot satisfy these targets.

The new opt-in [performance profile](../../frontend/mvp-performance.config.ts)
serves the compiled production app, starts only its own loopback backend/database,
and runs visible Chromium at 1440 × 1000 CSS pixels. It contains no test-only
store bridge. For each board it retains one warm-up then 30 sequential opens,
requiring both 2D footprints and actual 3D raycast selection before stopping the
open timer. The interval includes navigation between views and a real selection,
which is conservative relative to initial interaction readiness. A miss in this
interval blocks qualification but does not isolate intrinsic API/render latency
from automation, tab navigation and picking overhead. Tracing/snapshots are enabled
for retained failure evidence; no instrumentation-overhead correction is subtracted.
Startup to the
dashboard is separate, including the app's five-second minimum loading screen;
this is not a cold OS-cache benchmark.

One warm-up plus 30 production-UI job submissions use unique durable IDs, verified
through a separate GET. Queue policy is one job at a time, explicitly cancelled
before the next submission, without accepting any results. Acknowledgement covers
the UI click to parsed receipt in the browser's actual fetch path. Full initial
recompute execution and subsequent cancellation-observation times are separate.
Cancelled executions do not establish successful-job throughput or execution p95.

Five sessions per board hold real 2D pointer drags for at least 30 seconds each.
Capture-phase event receipt starts the timer; an observer waits for the saved
footprint's visual-preview transform to change, then records the next animation
frame callback. Missing feedback is retained as a failure. Raw samples and frame
gaps are retained separately. Sessions cancel transient previews after measurement,
and the saved document hash must remain identical. Background job-status GETs are
recorded; any mutation request during pointer movement fails the no-recompute
boundary. Browser frame callbacks do not establish GPU/display completion.

Run sequentially after functional suites finish, from `frontend/`:

```sh
VITE_API_BASE=/api npm run build
npx tsc -p e2e/tsconfig.json
npx playwright test --config=mvp-performance.config.ts
```

The standard browser suite remains `npm run test:e2e`; measurements are opt-in
`.measurement.ts` files and do not silently run in normal regression checks.
No dependency/browser installation happens implicitly. Visible desktop access,
existing Chromium and disposable PostgreSQL database privileges are required.

### Final measured results

The final corrected run exited **1**, with **two failed board cases** and exactly
two budget failures per case: open and acknowledgement. All readiness, inventory,
durable-ID, drag-feedback, session-length, no-mutation-during-drag and saved-hash
assertions passed. Cleanup passed for `panel_e2e_f287836c1fda4fbf82ae072e3a9b0ee7`.
Both boards used actual visible Chromium **159.0.8154.6**, the production bundle,
and **ANGLE / Mesa Intel UHD Graphics (TGL GT2), OpenGL ES 3.2**. This is distinct
from the software WebGL regression suite.

| Board / metric | Samples | Median ms | Nearest-rank p95 ms | Max ms | Target / result |
| --- | ---: | ---: | ---: | ---: | --- |
| `db-12` cached open, both views/pick interval | 30 | 2,250.65 | 2,393.30 | 2,419.10 | <2,000 — **FAIL qualification** |
| `db-16` cached open, both views/pick interval | 30 | 1,341.55 | 2,506.00 | 2,517.90 | <2,000 — **FAIL qualification** |
| `db-12` durable acknowledgement | 30 | 576.50 | 1,038.70 | 1,080.70 | <500 — **FAIL** |
| `db-16` durable acknowledgement | 30 | 1,080.45 | 1,302.20 | 1,363.40 | <500 — **FAIL** |
| `db-12` 2D drag feedback | 1,768 | 4.90 | 7.80 | 16.70 | ≤33 — **PASS** |
| `db-16` 2D drag feedback | 1,753 | 5.40 | 8.60 | 18.50 | ≤33 — **PASS** |

Each board retains a separately excluded warm-up: opens **2,583.60/2,678.10 ms**,
acknowledgements **326.10/642.40 ms** (`db-12`/`db-16`). The five session lengths
were `30,146 / 30,184 / 30,108 / 30,136 / 30,141` ms and
`30,141 / 30,130 / 30,171 / 30,130 / 30,152` ms respectively. Every sampled event
produced a visual-preview change; no missing or slow sample was discarded. Each
board recorded 9,028 frame gaps, p95 **16.7 ms**, maximum **24.6/16.8 ms**.
During drags only background status reads occurred (147/146 GETs), with **zero
mutation requests**. These timings qualify sampled 2D drag feedback only; the
separate real-browser tests exercise 3D picking/drag behavior without claiming
3D drag-frame latency qualification.

Each board returned **31 unique durable 202 job receipts**, including warm-up,
all verified by independent GET. Cancellation-observation median/p95/max was
**342/749/1,068 ms** and **457/785/846 ms**. Initial full synchronous recompute
execution took **28,688/31,048 ms**, outside acknowledgement timing. These are
observed single executions, not throughput or successful asynchronous-job p95.
Startup through dashboard readiness was **5,776 ms** per board, separately from
cached open. Processes/assets were warmed, but OS-cache cold start was not measured.

Host: i3-1115G4, two cores/four logical CPUs, 7,945,613,312 bytes RAM, Linux
`7.2.11-arch1-1` x86_64, `powersave`, Node **v24.18.0**, existing backend Python
**3.14.8**, local PostgreSQL and no fixed CPU affinity/clock. Before the first
sequential measurement run, available RAM was approximately 3.01 GB, allocated
swap 2.14 GB, load averages `0.75 / 1.81 / 3.00`. These are context observations,
not peak resource measurements. Functional suites had stopped before timing;
unrelated desktop activity was not controlled. No samples were load-corrected.

Raw ordered opens/acknowledgements, all drag samples/frame gaps, queue records,
model hashes and per-board attachments are retained in
`/tmp/panelflow-p3-t14-performance.json` (SHA-256
`9cb90b507675b19971274d6e2cddd1c474c965f99e02fcaeb3170f7232f2e0ee`).
Failure screenshots, traces and assertion contexts remain under
`frontend/test-results/mvp-performance/`. Measured document hashes were
`51b97803d8b81cb6add66ecd46925ed5ec579d93208e6016157ab30066b6f939`
and `e626fe7ce6baa6b467268aef844f6ded054dc6418f0d3389a0565ec5153d2b81`;
each remains unchanged after all jobs and drags.

The first measurement attempt exposed two test-setup mistakes: its open picker
omitted the real viewer's open-door camera bounds, and its supposed db-16 working
inputs were empty, causing default db-12 generation. Both were corrected in the
harness, including explicit working-input Save and component/route assertions;
the entire two-board timing protocol was rerun. Initial report/traces remain at
`/tmp/panelflow-p3-t14-performance-initial.json` and
`/tmp/panelflow-p3-t14-performance-initial/`. Initial API-test JUnit is retained
as `/tmp/panelflow-p3-t14-mvp-initial.xml`; its mislabeled larger-board hash is
superseded by the verified 37-component/56-route evidence above. No product
behavior or budget was changed to resolve these setup errors.

## Prototype engineering and export limits

The supported archetype is prototype Distribution Board (DB). Calculation
assumptions, catalog geometry, thermal density and duct-fill checks do not
establish electrical applicability, manufacturing fitness or standards compliance.
Required C01–C09 engineering checks remain unresolved; an empty physical violation
list is insufficient for publication. See [aggregate validation](../architecture/aggregate-validation.md)
and [protected publication](../architecture/protected-publication.md).

Native FreeCAD/STEP is excluded from the MVP by D01. GLB previews and generated
FreeCAD Python scripts are available representations; script text containing an
export command is not verified native STEP. The retained native geometry defect
and unchanged 0.05 mm reference tolerance belong to the separate qualification gate.
No native execution, installer, other-platform or standards qualification is claimed.

## Blocking defects and unverified scope

| ID | Result / effect on acceptance | Required disposition |
| --- | --- | --- |
| MVP-PUBLISH-001 | **BLOCKING.** No successful edited-document Publish/export path exists for the current prototype evidence. Both reference boards reject with `PUBLISH_STAGE_STALE`; the report is also required-status `UNRESOLVED`. The publisher checks all stage evidence before its independent engineering gate, so the observed error does not mean the engineering report passed. The frontend deliberately exposes `Publish unavailable`. | Implement reviewed publication evidence within authorized scope, or obtain an explicit human scope decision for a draft-centric MVP. Preserve both stage and engineering fences. No exception is approved by this report. |
| MVP-PERF-OPEN-001 | **BLOCKING qualification failure.** The recorded open-to-both-views/picking interval exceeds 2,000 ms p95 for both boards: 2,393.30 / 2,506.00 ms. The conservative interval includes automation/navigation/picking and tracing overhead, so it does not isolate intrinsic product-open latency. | Establish and measure the exact approved readiness boundary and meet D01 without silently changing its budget. Until then cached-open qualification remains failed. Any scope/protocol change requires explicit review. |
| MVP-PERF-ACK-001 | **BLOCKING.** Durable UI acknowledgement p95 is 1,038.70 / 1,302.20 ms against <500 ms under the recorded fixed cancellation queue policy. | Investigate enqueue/input materialization and UI acknowledgement costs; rerun both boards after a reviewed fix. No scope exception or threshold waiver exists. |
| P2 input-operation boundary | Requirement/enclosure forms retain input-only Save rather than shared operation undo. P2-T14 was human-overridden with exceptions; that history does not prove literal all-mutation coverage or approve a new P3 exception. | Keep the explicit compatibility boundary visible. Human scope resolution remains separate. |

Manual intent remains bounded: add/remove/enclosure-resize reconciliation can fail
with `STAGE_COMPONENT_MISMATCH`, `INVALID_NETLIST` or `STAGE_LOCK_CONFLICT`; the
existing conductor example can fail its bend requirement with `ROUTING_INFEASIBLE`.
P3-T13's full/incremental equivalence includes explained failures, not successful
regeneration for every edited draft. Rotation, rail/duct/general CAD editing,
multi-user authorization and engineering applicability are not established.

Native STEP's D01 exclusion is an approved MVP limit rather than an invented test
pass or a newly requested waiver. Platform/installer qualification and hosted CI
execution are not established by this local acceptance run. This task neither
executes later lifecycle work nor changes an earlier human decision.

## Reproduction and evidence

Commands, actual interpreter, results, skips and local artifact paths will be
recorded in the [attempt report](../../planning/task_reports/P3-T14/attempt-01.md).
