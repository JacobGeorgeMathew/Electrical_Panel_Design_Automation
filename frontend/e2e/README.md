# Isolated browser command harness

Run from `frontend/` on Linux/macOS with Node 20+, the existing backend virtual environment
and PostgreSQL service. The PostgreSQL role must be able to create/drop disposable
databases. Keep authentication private: use existing `DATABASE_URL` /
`PANEL_DATABASE_URL`, or libpq `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` / `.pgpass`.
With neither URL set, local libpq defaults are used. No development project data
or application database contents are required. Do not change a development database
to make these tests pass.

```sh
npm ci
npx playwright install chromium
npm run test:e2e
npm run test:e2e -- --repeat-each=2
npm run test:e2e -- --headed
npx playwright show-report
```

On a supported clean Linux CI host, `npx playwright install --with-deps chromium`
also installs browser system libraries (requires host package-manager permission).
The harness uses one direct automation dev dependency, `@playwright/test`, pinned
in the lockfile. Its browser binary is installed separately in Playwright's cache.
No browser downloads or dependency installs happen implicitly during a test run.
`npm run test:e2e` also type-checks the harness. `npm test` continues to run jsdom
tests under `src/`; browser specs are never collected by Vitest.

## Ownership and isolation

`setup.ts` launches **only** `backend/.venv/bin/python` with `backend/` as cwd.
Python checks its executable/prefix, creates a random `panel_e2e_<uuid>` database,
migrates it, loads the same sample SQL/catalog fixtures as `tests/conftest.py`,
and starts the real FastAPI app. It never connects to the configured application
database. A temporary directory owns all managed assets. A private seed endpoint,
registered only by `e2e/backend.py`, creates a new project/document per test using
the existing operation-persistence fixture. It retains stable engineering IDs and
nonzero mounting offsets. It is an unresolved prototype working document, not a
published, validated or certified panel.

Both servers bind dynamically allocated loopback ports. Vite proxies the central
client's `/api` requests to this owned backend, avoiding production CORS changes.
An existing development server cannot satisfy setup. Browser contexts start with
fresh storage; `stalePeer` creates an additional independent context. Tests use
one worker, no retries, and a new database on each run.

On success, failure or normal interruption, Playwright teardown closes Vite and
the Python stdin pipe. Python closes the app, drops only its allocated database,
verifies its absence, and removes temporary assets. Look for
`E2E database cleanup: PASS panel_e2e_...`. Cleanup failure makes the run fail.
Closing the parent pipe also stops Python if the test runner disappears. SIGKILL,
host failure or PostgreSQL loss can interrupt cleanup: investigate the exact name
from `E2E allocated` before manually removing anything. Never broadly drop databases
by prefix. Generated traces, HTML reports and screenshots are ignored by Git.

## Reusable fixtures and boundaries

| Helper | Purpose |
| --- | --- |
| `test`, `projectId`, `openHarness` | Owned URL, fresh seeded project, actual `Panel3DViewer` inside `DesignViewport`. |
| `pickComponent` | Front-camera projection guides real mouse clicks; Three.js raycasting and shared selection must identify the component. |
| `panelE2E.gizmoPoint` | Reads the installed Fiber canvas camera/picker to project a hittable X handle after resizing; real pointer events still drive TransformControls. |
| `drag` | Actual pointer down/move/up for SVG, Three.js TransformControls, React Flow symbols and pins. |
| `moveRequest`, `propose` | Fresh operation/batch IDs, current hashes/clocks and a retained idempotency key through the P2-T09 store. |
| `stalePeer` | Independent browser/store holding a stale document; caller closes it in `finally`. |
| `readDocument`, `saveAndReopen` | Read aggregate and use central input Save, then reload and compare persisted content. |

`harness.html` is a separate Vite development entry, absent from production build
inputs. `window.panelE2E` exists only there. It loads server snapshots into the
existing viewer and invokes real stores/clients; it supplies no authoritative
durable CEM/PDM and mocks no API. All gesture bindings come from production components. A locally
served installed Three.js font keeps viewport text offline. Software WebGL in
headless Chromium is real rendering/raycasting, but does not qualify GPU drivers.

The runnable smoke specs prove picking, one committed gizmo drag with durable undo/redo, fullscreen
canvas identity/resizing/focus, non-writing preview, command commit, exact-key
retry, saved aggregate reopen and a real stale-context HTTP 409 with proposal
retention. Command commits remain dirty and routing checks unresolved.
`physical.spec.ts` checks 2D release, inspector and 3D coordinates, operation counts,
undo, rotation disabling and the actual workspace Save command followed by reopen.
`schematic.spec.ts` checks real symbol and pin gestures, net hashes, layout undo/redo,
Save/reopen, compatible conductor creation and rejected duplicate endpoints.
Its optional electrical seed adds explicit synthetic PE endpoint roles using the
existing qualified schematic fixture; production code does not infer those roles.
`catalog.spec.ts` checks exact catalog-version insertion, unconnected terminals,
reopen, dependency review, blocked unconfirmed removal, cancellation and durable undo.

P2-T14 adds `acceptance.spec.ts`: deliberate movement of only the live Three.js
object must fail the same saved-PDM oracle used by the positive gizmo test, leave
server history unchanged and disappear on reopen. This test-only fault injection
does not change production gesture bindings or write snapshots. The automatic
proposal case uses the actual API for review/acceptance/retry/stale rejection,
then the production viewer, Save and shared undo after reopen. It does not claim
an automatic proposal UI exists. See [phase 2 evidence](../../docs/verification/phase-2-acceptance.md).
Tauri, native CAD, other browsers and hardware WebGL remain separate checks.
