# P0-T03 performance baseline

PanelFlow prototype Distribution Boards. Measured evidence and limitations for
human review; no performance target or engineering approval is granted here.

## Hardware and versions

Captured on 2026-11-13, branch `phase_1`, source HEAD
`6e85b6b2918aaee2587e2c473584d076486d636e`, plus the task's new test/harness files.
Existing P0-T01/P0-T02 documentation was preserved. No production source,
dependency, schema or lifecycle edit was needed.

| Item | Observed configuration |
| --- | --- |
| CPU | Intel Core i3-1115G4 @ 3.00 GHz; 2 physical cores, 4 logical CPUs; advertised maximum 4.10 GHz |
| Memory | 7,945,617,408 bytes RAM; 12,562,456,576 bytes swap (0 used at preflight) |
| Graphics | Intel Tiger Lake-LP GT2 UHD Graphics G4; hardware WebGL was not exercised |
| OS | Linux `7.2.11-arch1-1`, x86_64 |
| Power mode | CPU frequency governor `powersave`; no fixed clock, CPU affinity or isolation |
| Python | 3.14.8; `<root>/backend/.venv/bin/python`; confirmed `sys.prefix=<root>/backend/.venv` |
| Geometry/model dependencies | OR-Tools 9.15.6755, Shapely 2.2.0, Pydantic 2.14.1, NumPy 2.5.4 |
| API/database dependencies | FastAPI 0.143.2, SQLAlchemy 2.0.55, Psycopg 3.3.6; local PostgreSQL server version number `180006` |
| Frontend | Node v24.18.0, npm 12.2.2; installed lockfile dependencies; Vite 5.4.21, React 18 |
| Browser | Firefox 159.0, headless; requested outer window 1280 × 900, observed inner viewport 1280 × 814 CSS pixels |
| Engine/export | `db-pipeline-4`; GLB `panelstudio-primitives/3`; FreeCAD-script generator uses the engine version |

Hardware was read through `lscpu`, `free -b`, `lspci`, `uname` and sysfs. The
conventional `/sys/fs/cgroup/cpu.max` path was absent; no cgroup quota is claimed.
No new dependency, browser or driver was installed. Browser automation uses the
installed Firefox WebDriver BiDi endpoint and Node's built-in WebSocket.

## Datasets and comparison rules

Definitions are in [cases.json](../../backend/tests/fixtures/design_baselines/cases.json).
Both boards use 415 V, three phases, 50 Hz, 250 A incomer, IP54, 20% spare and
neutral enabled. Each has one MCCB, SPD, busbar, neutral bar and earth bar, plus
one MCB and terminal block per feeder.

| Case | Feeders | Components | Conductors/routes | Enclosure mm | Rails / ducts / accessories |
| --- | ---: | ---: | ---: | --- | --- |
| `db-12` | 12 | 29 | 44 | 800 × 1200 × 300 | 3 / 6 / 10 |
| `db-16` | 16 | 37 | 56 | 1000 × 1200 × 300 | 3 / 6 / 10 |

These are sampled board sizes, not an approved supported-size range. The 56-route
case reaches the router's present discrete lane count; no scalability claim is
made beyond it. Four failure cases cover oversized placement, an undersized
fixed enclosure, disconnected ducts and an obstructed bridge.

[Fixture documentation](../../backend/tests/fixtures/design_baselines/README.md)
separates generated observations from independent arithmetic/geometric checks.
The full canonical package and each CEM/PDM/schematic/CAD/BOM projection have
SHA-256 pins; actual GLB/script bytes also have hashes and lengths. For example:

| Case | Direct-engine package SHA-256 | GLB bytes | Script bytes |
| --- | --- | ---: | ---: |
| `db-12` | `067e8e8de872e7481051ee5ffbacadc2be2f915de94b3cd7ab93798e68ff3765` | 3,889,060 | 557,856 |
| `db-16` | `6784a159909bb463902dc2ffd760b72f7b10d6a5138c1d8fbb31ba26a376542b` | 4,866,188 | 696,053 |

The corresponding observed JSON files contain complete individual hashes and
identity references. Direct-engine fixtures inject all adapters and use fixed
project IDs. Their JSON catalogs are pinned by file hashes, not SQL UUIDs.
Performance API cases use newly created projects in the existing disposable
PostgreSQL fixture, with its migrations, sample SQL and catalog import. These
are distinct provenance: SQL manifests/artifact hashes can differ from the
direct-engine fixture. Repetition within each API project compares exact
semantic output and preserves all version pins. Cross-run project/revision
UUIDs are never normalized or claimed identical.

Canonicalization sorts object keys only, using existing `canonical_json`.
There are no nondeterministic timestamps in direct-engine output; the timestamp
normalization list is empty. IDs, array order, coordinates, floating-point
precision, warnings and unresolved checks remain in comparisons. API envelope
timestamps are not used as semantic snapshots; saved CEM/PDM and derived
projections are compared exactly. No general field stripping is performed.

## Repeatable measurement procedure

Run each measurement separately, after test/build processes have stopped. The
retained runs used that sequence; unrelated host activity was not controlled.
Each metric retains one first-use warm-up sample separately, followed by five
samples in execution order. Median is the middle sorted sample; nearest-rank
p95 is sorted sample `ceil(0.95 × 5)`, hence the **maximum of five**, not a robust
production percentile estimate. No outlier is removed. Times are milliseconds.

1. From `backend/`, confirm `.venv/bin/python` and `sys.prefix` point at the
   backend environment. Run `.venv/bin/python -m pytest
   tests/test_design_baselines.py -q` to validate pinned inputs, exact output,
   independent relations and failure expectations.
2. On the measured local peer-authenticated PostgreSQL host, run
   `.venv/bin/python -m tests.run_design_baseline_postgres --measure --timings-only`
   from `backend/`. The launcher queries maintenance metadata, supplies private
   child-process configuration, sets `PANEL_RUN_POSTGRES_TESTS=1` and
   `PANEL_MEASURE_BASELINE=1`, and runs the two timing tests. Only existing
   fixtures perform DDL, in `panel_integration_test_<uuid>` databases; teardown
   and before/after name sets verify cleanup. Assets use temporary directories.
   No development database is initialized, imported or read as test data.
3. **Generate interval:** `perf_counter_ns` immediately before TestClient
   `POST /api/projects/{id}/revisions` through complete response receipt. It
   includes validation, catalog input reads, placement, routing, geometry,
   GLB/script creation, short revision publication, saved-design reconstruction
   and response serialization. Project creation, database setup, interpreter
   imports and request JSON parsing in the measurement test are outside it.
   Six sequential revisions are generated per project with the latest
   `expected_version`; every semantic package must have the same SHA-256.
4. **Open interval:** immediate sequential TestClient `POST .../open` then
   `GET .../design`, through complete response receipt. It includes last-opened
   persistence, saved CEM/PDM/hash reads, artifact checks, current projection
   reconstruction and serialization. No regeneration occurs. Each open checks
   the exact saved snapshot hash, semantic payload and unchanged lock version.
   This is an in-process backend interval, not browser navigation/network/open
   latency. JSON assertion work is outside the timed interval.
5. From `frontend/`, run `node scripts/measure-design-baseline.mjs`. It starts a
   loopback Vite development server and a fresh temporary headless Firefox
   profile, then uses BiDi to load the real React `Layout2DViewer`, CSS and
   Zustand store. It generates each full board through the backend interpreter
   outside the timed interval. Imports, browser/Vite startup and Python
   generation are excluded. For each sample, load PDM/CEM into the store, create
   a fresh 1280 × 900 CSS-pixel host/root, start `performance.now`, synchronously
   mount the real viewer, force a layout read and wait for the second
   `requestAnimationFrame` callback. Stop the clock before assertions/unmount.
   Verify every DOM component and conductor ID, visible document state and
   enclosure viewBox. Routes, zones and clearances use the viewer defaults;
   wire visibility is enabled. The browser/profile and server are closed.

The browser interval includes React render, SVG DOM construction and a frame
boundary opportunity; it does not establish GPU completion or display latency.
Headless/dev-mode results must not be substituted for production WebGL, Tauri
or interactive drag measurements. First-use samples are not cold OS-cache or
fresh-process measurements: the setup/import work is already complete.

## Measured results

The final database timing-only run exited 0: **2 passed**, one dependency
deprecation warning, 53.39 s including fixture setup/teardown. Disposable
database sets were `[]` before and after; launcher-owned assets were removed.
Raw samples below are in execution order, with no rounding in the linked
[machine-readable evidence](performance-samples.json).

| Case | Interval | Warm-up ms | Five retained samples ms (display rounded to 3 decimals) | Median ms | Nearest-rank p95 ms |
| --- | --- | ---: | --- | ---: | ---: |
| `db-12` | Generate API | 3489.900 | 3402.613, 3398.497, 3505.453, 3524.497, 3416.646 | 3416.646 | 3524.497 |
| `db-12` | Saved open API | 161.699 | 260.631, 156.900, 159.059, 158.641, 166.087 | 159.059 | 260.631 |
| `db-16` | Generate API | 4184.274 | 4267.817, 4292.503, 4284.129, 4325.508, 4321.764 | 4292.503 | 4325.508 |
| `db-16` | Saved open API | 244.607 | 243.173, 249.540, 245.029, 242.428, 243.264 | 243.264 | 249.540 |

The final Firefox harness run exited 0. Every rendered component and conductor
ID matched its generated package. No verification/build/database benchmark ran
alongside these retained browser samples.

| Case | Interval | Warm-up ms | Five retained samples ms | Median ms | Nearest-rank p95 ms |
| --- | --- | ---: | --- | ---: | ---: |
| `db-12` | SVG mount → second frame callback | 40 | 16, 16, 26, 22, 26 | 22 | 26 |
| `db-16` | SVG mount → second frame callback | 15 | 19, 24, 21, 18, 20 | 20 | 24 |

Firefox reports these samples with millisecond timer granularity. Board order
is always 12 then 16 in one browser session; later samples can benefit from
JIT/module warming. These small samples do not imply a size/performance curve.

The semantic hashes and GLB/script hashes in the raw API timing records identify
this particular fixture-created project per board. Repeated revisions in that
project matched exactly. A newly allocated project in a future run can have a
different semantic hash; it must not be normalized into a claimed identical
historical revision. The fixed-ID direct-engine artifact pins remain the
cross-run regression authority.

## Verification and limitations

The focused reference suite passed 13 tests. The complete backend unit profile
passed 87 tests with 21 intentional skips (19 existing database tests and 2
new opt-in timing tests), one dependency warning. The complete PostgreSQL
profile with measurement enabled passed **108 tests, zero skips**, one warning,
149.36 s; it exercised both disposable-fixture paths and verified no matching
database remained. Its interleaved exploratory timings are excluded from the
table above because other verification/browser processes overlapped that run.
No failing performance sample was hidden by these exclusions: it had no
threshold, and all semantic assertions passed. Final timing-only data above
used a separate sequential run after verification processes stopped.

Frontend focused editor/persistence/routing tests passed 13 tests; full Vitest
passed 61 tests in 19 files. `npm run build` passed TypeScript and Vite
compilation, with the existing >500 kB chunk-size warning. Two early browser
harness runs failed (module loading and then top-level asynchronous evaluation);
both were fixed before any final render sample was recorded. These are harness
failures, not evidence of product latency or a product test regression.

The initial database launcher attempt failed at the sandbox-denied Unix socket,
before creating any database. The approved retry and final timing-only run used
the same backend interpreter outside that restriction. The local-peer launcher
is intentionally specific to this measured host. On another host with private
configuration, use the existing isolated fixture with the opt-in flags; never
point a timing test at a development database or provision data outside it.

No approved latency threshold exists here. The lifecycle's proposed cached-open,
drag-frame and job-acknowledgement targets require later human decisions and
precise acceptance methods. None is labeled achieved by these measurements.
In particular, a five-sample backend-open maximum is not an end-to-end cached
document-open p95, and SVG mount timing is not a drag-frame budget.

**Unmeasured:** cold OS-cache/process startup, network/browser end-to-end open,
3D/WebGL render and frame pacing, actual GPU/display completion, Tauri/installer
behavior, native FreeCAD/STEP, concurrent-user performance, memory peaks and
boards beyond these two cases. Headless dev-mode timing is not a production
renderer benchmark. No human approval or engineering certification is implied.

Exact commands, exit statuses, initial failures and remaining scope are in the
[attempt report](../../planning/task_reports/P0-T03/attempt-01.md). No production
code, schema, lifecycle state, execution history or user project was changed.
