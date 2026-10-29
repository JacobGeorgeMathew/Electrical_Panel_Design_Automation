# Schematic and physical wiring implementation

## Scope and audit

This change retains FastAPI/Pydantic, NetworkX, OR-Tools, Shapely, PostgreSQL/SQLAlchemy/Alembic, React/TypeScript/Zustand, React Flow and React Three Fiber. No new dependency or service was added. This is a DB prototype wiring improvement, not a manufacturing compliance claim.

The actual connection flow is `NetlistEngine.generate_netlist` -> `ConnectionRef` / `NetRef` in CEM -> `SchematicEngine.generate_schematic_data` and `DesignOrchestrator._physical_design` independently -> `DuctRouter.route_layout` -> PDM `WireRoute` -> `build_wire_geometry` -> `WireMesh`, 2D polylines, `CADEngine` -> GLB / generated FreeCAD script. `write_revision` stores the snapshots and normalized conductor/route projections atomically.

| Original cause | Evidence and change |
|---|---|
| Backend schematic paths discarded | `frontend/src/components/schematic/SchematicViewer.tsx::WireEdge` used `getBezierPath`; now renders backend `svg_path`. Draft-only edges use orthogonal step paths. |
| Invented junction geometry | `schematicGraph.ts::buildSchematicGraph` replaced multi-terminal nets with a centroid star. Now preserves every connection ID and endpoint; only backend shared-terminal junctions are shown. |
| Crowding and missing ports | Old `schematic_engine.py` hardcoded terminal lists and midpoint tracks, silently skipped unmatched ports. Now derives ports from actual CEM terminals and fails explicitly on missing ports. |
| Physical path shortcuts | `DuctRouter` used JPS/Theta shortcuts within troughs and reused eight depth lanes. It now uses orthogonal A* and a bounded 56-lane lateral/depth arrangement. The open-space JPS/Theta implementation remains available. |
| CAD wire discontinuities | `CADEngine.export_freecad_script` created disconnected straight cylinders. It now requests a pipe sweep along the validated sampled centerline and checks the returned shape. |
| Stale routes after moving devices | The store submitted placements with old routes and ignored returned PDM geometry. It now clears routes during edits, calls backend rerouting on apply/release/blur, and consumes the returned PDM. |
| False duct failures at vertical segments | The planar validator buffered a zero-length projected LineString, producing an empty envelope. A depth-only trunk is now tested as a Point footprint and against duct depth separately. |

## Algorithms and contracts

### Schematic

`SchematicConfig` describes configurable column/row spacing, symbol size and port stubs. `SchematicEngine` places DB functional groups in deterministic rows and aligns feeder and terminal columns. The template controls arrangement only; it does not alter CEM topology. This is a template layout, **not a general Sugiyama implementation**.

`algorithms/schematic_routing.py::orthogonal_route` runs direction-aware A* on a compressed rectilinear visibility grid around symbol/label envelopes. Cost includes length, bends and coincident-track congestion. Wires retain CEM connection/net IDs and explicit source/target port IDs, waypoints, SVG path, layer, status, crossings and junctions. A geometric intersection alone never creates a junction, even within a named net: a connected marker requires a shared CEM terminal. Distinct-net crossings use gap markers. Coincident segments remain explicit `COINCIDENT_SEGMENTS` drawing warnings rather than being silently merged. Selected wires show their labels; component IDs/ratings and terminal handle tooltips remain available. React Flow retains zoom, pan, filtering and local draft editing; generated symbol positions are fixed to protect backend route alignment. These are generic terminal symbols, not an IEC symbol library or multi-page drafting engine.

### Physical routing

`DuctRouter` reuses terminal extraction, obstacle processing, collision checks and route utilities from `JPSThetaStarRouter`. Duct trunks use direction-aware Manhattan A* with a bend penalty, because diagonal Theta* shortcuts are unsuitable for orthogonal trough routing. Terminal approaches use a four-neighbor Dijkstra search. The grid remains 5 mm by default. There is no straight-line fallback.

A conservative eroded duct network reserves room for lateral lanes and estimated wire radii. Deterministic lateral/depth slots preserve individual conductor IDs. `_finalize` removes redundant collinear grid detours without introducing a new path outside the original segments. Duct area/fill is counted across the bundle and overflow fails explicitly. If a duct supplies `allowed_wire_classes`, incompatible routing fails. Empty eligibility data means segregation is unconfigured, not certified. There is no global congestion rip-up/retry solver; all routes are recomputed together after edits. The current lane arrangement supports at most 56 conductors and the existing DB-sized troughs; larger/other cable systems require configurable packing.

`ConnectionRef` accepts optional material, cross-section, insulation type/diameter and minimum bend radius. `WireRoute` adds `conductor_id`, dimensional provenance, minimum bend radius, routing algorithm/configuration/status, validation checks and `WireGeometry`. Existing keys and endpoint references remain. Coordinates reject NaN/infinity. Terminal coordinates are required; component rotation is applied about the same body center as the viewer. Draft routing explicitly refuses rotated-device obstacle layouts because the router's body obstacles remain axis aligned.

The catalog currently lacks complete conductor sizing and manufacturer bend data. Existing generic 3/4/6 mm insulation diameter estimates remain explicitly labelled `generic-preview-estimate`; they are **not ampacity-derived conductor sizes**. The old panel-earth endpoint is still a derived virtual anchor near the duct, not a manufacturer-defined cabinet stud. No new electrical connection or terminal is fabricated to hide that limitation. Multicore cables, ferrules, termination capacity and new branched splice hardware are not implemented.

### Wire geometry

`services/wire_geometry.py::circular_centerline` removes consecutive duplicates and redundant collinear points, preserves endpoints, detects reversals, and constructs circular fillets using tangent distances. A declared minimum radius must fit adjacent segments; otherwise generation fails. When the radius is absent, bounded preview fillets fit the available space and the manufacturer-radius check remains `UNRESOLVED`. Sampling uses at most 7.5 degrees per step. No Catmull-Rom smoothing or schematic coordinates are used.

`build_wire_geometry` checks sampled swept envelopes in 3D against component AABBs and enclosure bounds, with the declared wire-clearance envelope and a 0.03 mm sampling allowance. Rounded duct trunks are reclassified with explicit centerline entry/exit indices and checked against the eroded trough interior and available depth, including wire radius. Only local endpoint lead regions can enter their endpoint device. This is broader than a planar intersection check but does not model exact screw bores or catalog solid shapes. `WireGeometry.status=PASS` describes these geometric checks only. Its individual `checks` explicitly retain unresolved manufacturer bend limits and wire segregation. It does not mean manufacturing approval.

`PanelAssembly.tsx::WireMesh` builds a Three.js TubeGeometry from the backend centerline using the route diameter, memoizes it and disposes obsolete geometry. It supports wire selection and connected-component/net highlighting. The 2D layout projects the same centerline onto the backplate; a projected crossing never implies a physical connection. `WireInspector` exposes conductor IDs, terminal pair, length, bend count, diameter provenance, status and unresolved checks in all three views. Physical wire visibility is shared; existing per-view filters remain.

The CAD adapter and GLB exporter consume that same centerline. Historic routes with no validated geometry are omitted from read-only CAD previews with explicit UNRESOLVED results. Export refuses those routes instead of silently converting them into straight wires. The generated FreeCAD script uses `makePipeShell` and `shape.isValid()`. Its argument order was checked against the [FreeCAD implementation](https://github.com/FreeCAD/FreeCAD/blob/main/src/Mod/Part/App/TopoShapeWirePyImp.cpp); that source check does not verify actual kernel execution. Script syntax and exported triangle data are tested; actual OpenCascade/FreeCAD execution is **UNVERIFIED** in this environment. Browser preview does not require FreeCAD.

## Synchronization and persistence

`POST /api/projects/{project_id}/design/reroute-placement` accepts an edited PDM, reloads saved CEM connectivity, requires matching project/component IDs and returns `{pdm, validation_results, is_valid, persisted:false}`. It never trusts client routes as electrical connectivity. Failures clear dependent route geometry and return critical violations; they cannot fall back to straight lines. This is an advisory draft operation and does not publish a revision or overwrite saved CAD. The existing `/validate-placement` API remains available for independent checks. Draft edits reroute the entire coupled duct bundle; selective per-conductor recomputation is not implemented. Requirement/connectivity regeneration still uses the existing complete revision pipeline. Label-only schematic drafts do not trigger physical routing.

Async reroute results are ignored after a project/revision/transform change or a newer request. Undo/redo and numeric/gizmo edits reroute on commit; reset restores the saved PDM. The schematic remains independent of physical placement. Shared CEM connection IDs link schematic edges, PDM conductors, geometry and CAD objects.

The engine version is `db-pipeline-4`, generated assembly assets use `panelstudio-primitives/3`. Old snapshots/assets remain immutable and are marked stale for regeneration. New optional fields serialize in existing JSONB snapshots and route constraints; conductor dimensions use existing cross-section/insulation columns. **No SQL schema or catalog/asset-library definition changes were required**, so there is no new migration or seed package for this update. Teammates apply existing migrations/seeds and generate their own versioned project assets from the updated code. Do not copy a live connection URI into source control.

## Files

| Files | Purpose |
|---|---|
| `backend/app/algorithms/schematic_routing.py` (new), `services/schematic_engine.py` | Template, explicit ports, orthogonal drawing router and intersection metadata. |
| `backend/app/models/cem.py`, `models/pdm.py` | Optional conductor specifications, finite coordinates, route and geometry contracts. |
| `backend/app/algorithms/duct_routing.py`, `algorithms/jps_theta_star.py` | Manhattan duct paths, lane reservation, finalization, class/fill rejection, transformed real terminals. |
| `backend/app/services/wire_geometry.py` (new), `services/physical_routing.py` (new) | Fillets, sampled 3D envelope checks and draft rerouting. |
| `backend/app/services/orchestrator.py`, `services/validation_engine.py` | Validate geometry before publication and correctly check depth-only trunk footprints. |
| `backend/app/services/cad_engine.py`, `services/project_service.py`, `persistence/revisions.py` | Shared centerline for exports, versioned artifacts and stored metadata. |
| `backend/app/api/routes_design.py` | Additive draft rerouting endpoint. |
| `frontend/src/components/schematic/{SchematicViewer.tsx,schematicGraph.ts}` | Render backend paths and actual topology, preserve draft tools. |
| `frontend/src/components/threeD/{PanelAssembly.tsx,Panel3DViewer.tsx}`, `components/layout/Layout2DViewer.tsx` | Centerline meshes, projections, selection, rerouting and narrow-view scrolling. |
| `frontend/src/components/common/WireInspector.tsx` (new), `pages/ProjectPage.tsx` | Shared conductor inspection panel. |
| `frontend/src/stores/projectStore.ts`, `api/client.ts`, `types/pdm.ts` | Invalidation, result/race handling and extended contracts. |
| `backend/tests/test_wire_engine.py` (new), `tests/test_backend.py`, `frontend/src/components/schematic/schematicGraph.test.ts`, `frontend/src/stores/projectStore.routing.test.ts` (new) | New algorithm/integration tests and updated CAD/graph contract assertions. |

`backend/tools/export_wiring_example.py` exports a saved local revision into `docs/examples/wiring/DB-schematic.svg` and `DB-wiring.json` for review. The latter includes physical routes, geometry centerlines, dimensional provenance and unresolved checks. These are generated documentation examples, not catalog seed assets.

No source files were removed. No electrical catalog connectivity was changed.

## Run and verify

From `backend/`, with your existing private PostgreSQL configuration:

```powershell
.\venv\Scripts\python.exe -m app.persistence.manage status
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8731
```

Teammates on Linux use their activated environment's `python` for the same module commands. If upgrading an older checkout/database, first follow `CONSTRAINT_POLICY_UPDATE.md` (`initialize`, `import-legacy`, `seed-constraints`). This update keeps database head `0003_constraints`.

From `frontend/`:

```bash
npm run dev -- --host 127.0.0.1
npm test
npm run build
```

Run backend tests from `backend/`:

```powershell
$env:PANEL_RUN_POSTGRES_TESTS='1'
.\venv\Scripts\python.exe -m pytest -q
```

The PostgreSQL tests create and clean up unique disposable databases. Without that environment flag, service-dependent tests are skipped; routing/geometry tests remain deterministic and offline.

Open http://127.0.0.1:3000/, generate the existing 415 V / 3-phase / 250 A / 12-feeder DB example, then inspect Schematic, 2D Layout and 3D Panel. Select a net in the shared inspector and switch views. Select a feeder, move it 5 mm and apply/release: connected route endpoints must change; impossible movement must clear routes and show a failure. Show duct covers off and the door open to see routing. Test 16 feeders via normal regeneration. Existing saved revisions need regeneration for new centerlines.

## Verification results (29 October 2026)

- Full backend suite: **73 passed**, including isolated PostgreSQL workflow, migration and schema checks. One existing Starlette/AnyIO deprecation warning remains.
- Frontend suite: **29 passed** across 12 test files. The production TypeScript/Vite build passed; the existing large JavaScript chunk warning remains.
- Additional final schematic retest covers the revised crossing paint order and shared-terminal junction annotation.
- Both 12- and 16-feeder generation fixtures pass all implemented placement/thermal/routing checks. The retained layouts also produced 44 and 56 checked wire geometries respectively.
- Running application: generated and reopened demo revision **r10**, with 44 routes, 44 geometries and zero physical violations. Engine `db-pipeline-4`; assembly asset generator version `3`.
- Live `reroute-placement`: moved QF002 by +5 mm in Y, returned 44 regenerated routes, zero violations and `persisted:false`; the saved revision stayed intact.
- Inspected the schematic, projected 2D routes, open 3D cabinet and net-inspector data through the computer-use skill. Narrow views can scroll to their canvases; the inspector displays unresolved manufacturer/segregation/dimension checks.
- Generated [schematic SVG](examples/wiring/DB-schematic.svg) and [routing/geometry evidence JSON](examples/wiring/DB-wiring.json) are included. They are example outputs from the current saved demo, not a historical screenshot or a manufacturing drawing.

Regenerate these documentation examples from the running backend with:

```powershell
cd backend
.\venv\Scripts\python.exe tools/export_wiring_example.py --project PROJ_DB_DEMO_001
```

## Known limits and remaining work

- Coincident schematic tracks are detected and reported; complete crossing minimization, line-spacing guarantees, off-page connectors, engineering symbol graphics and general multi-page layout remain unfinished.
- Duct-wall/finger/door swept-solid collision, arbitrary forbidden 3D zones, all conductor-to-conductor collisions, exact terminal entry bores, self-intersecting sweep certification and insulation segregation are not fully validated. The geometric PASS scope above must not be expanded by inference.
- Generic wire diameters and preview bend radii require actual conductor/catalog data before manufacturing. The virtual cabinet earth anchor needs a specified stud/accessory and terminal coordinates.
- No multicore cable subsystem, automatic splice topology, selective reroute graph, packing beyond 56 routes, or global congestion reroute optimization is claimed.
- Placement edits remain local drafts. Publishing manual placement edits as immutable revisions is not implemented; Generate Design runs automatic placement again.
- FreeCAD sweep execution and STEP solid validation remain unverified until run with FreeCAD/OpenCascade. A script/export failure must be treated as failure, not a valid solid.
