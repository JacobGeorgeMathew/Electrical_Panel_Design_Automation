# Project Status Report

Audit date: 2026-10-27. Audited checkout: `a2c94c6`. Scope: tracked application source, tests, migrations, data fixtures, build configuration and documentation. Installed dependency folders, compiled binaries and generated build output are not treated as source implementations. This report is the only intentional tracked-file change made for the audit. No database connection URI is included.

Status meanings:

- **IMPLEMENTED**: working code exists and is connected to the current DB workflow. This does not mean production engineering approval.
- **PARTIAL**: working code exists, but integration, coverage or engineering behavior is incomplete.
- **STUB/MOCK**: illustrative or placeholder behavior/data replaces the real capability.
- **NOT STARTED**: no implementation was found in the audited application. A table, type, dependency or document alone does not count.

**UNVERIFIED** is an evidence qualifier, not a fifth status. Runtime checks and their limits are recorded in section 11. Claims below refer to the named implementations, not to architecture diagrams or proposed features.

## 1. Overview

### What the project does today — five lines

1. **IMPLEMENTED:** creates and saves DB projects and questionnaire answers in PostgreSQL through `ProjectService.create/update` in `backend/app/services/project_service.py`.
2. **PARTIAL:** generates a CEM with fixed-assumption calculations, selected prototype components and terminal connections through `DesignOrchestrator.generate_design` in `backend/app/services/orchestrator.py`.
3. **PARTIAL:** selects an enclosure, solves placement, routes wires and checks simplified geometry through `EnclosureEngine.select_enclosure`, `CPSATPlacementOptimizer.solve`, `JPSThetaStarRouter.route_layout` and `ValidationEngine.validate_pdm`.
4. **IMPLEMENTED:** publishes versioned CEM/PDM snapshots, relational projections and hashed file references through `write_revision` in `backend/app/persistence/revisions.py`; reopening verifies hashes through `ProjectService.load_revision`.
5. **PARTIAL:** displays requirements, schematic, 2D/3D layout, validation, component BOM and catalog in `ProjectPage` in `frontend/src/pages/ProjectPage.tsx`; manual editor changes do not publish a complete revised design.

### Actual technology stack

All entries below are **IMPLEMENTED** dependencies, except the desktop packaging qualification noted separately. Version declarations are from `backend/requirements.txt` and `frontend/package.json`; a range is a package declaration, not an assertion about every installed machine.

| Area | Declared packages | Actual use / evidence |
|---|---|---|
| Backend API and contracts | FastAPI 0.143.2, Pydantic 2.14.1, Uvicorn 0.54.0 | `app.main.create_app`; models in `backend/app/models/`; API routers. |
| Placement and geometry | OR-Tools 9.15.6755, Shapely 2.2.0 | `CPSATPlacementOptimizer._solve_rows`; `ValidationEngine.validate_pdm`; router geometric clearance checks. |
| Graph | NetworkX 3.7 | `GraphEngine.build_electrical_graph` constructs a local directed graph; no graph analysis is returned from that object. |
| Database | SQLAlchemy 2.0.55, Alembic 1.20.1, Psycopg binary 3.3.6; PostgreSQL | `Database`, `Settings.load`, `manage.initialize`, static mappings in `backend/app/persistence/models.py`. PostgreSQL server version is external to requirements.txt. |
| Backend tests | pytest 9.1.1, HTTPX 0.28.1 | `backend/tests/test_backend.py`, `test_postgres.py`, `conftest.py`; FastAPI `TestClient`. |
| Frontend | React/React DOM ^18.3.1, TypeScript ^5.4.5, Vite ^5.2.11, React plugin ^4.2.1 | `frontend/src/main.tsx`, `App`, `ProjectPage`; `frontend/vite.config.ts`. |
| 3D | Three.js ^0.164.1, React Three Fiber ^8.16.2, Drei ^9.105.0 | `Panel3DViewer`, `ComponentMesh`, `AssetObject`. |
| Diagram and state | React Flow ^12.12.0, Zustand ^4.5.2 | `SchematicCanvas`, `buildSchematicGraph`, `useProjectStore`. |
| Styling | Tailwind ^3.4.3, PostCSS ^8.4.38, Autoprefixer ^10.4.19, Lucide ^0.378.0, clsx ^2.1.1 | `frontend/src/index.css`, component JSX and frontend styling configuration. |
| Frontend tests | Vitest ^1.6.1, jsdom ^24.1.3 | `frontend/package.json` test script and `frontend/src/**/*.test.ts*`. |
| Desktop | Tauri API/CLI/shell ^2.12.1; Rust Tauri application | **PARTIAL:** release sidecar lifecycle exists in `frontend/src-tauri/src/lib.rs::run`; installer/platform execution is **UNVERIFIED** in this audit. `backend/panel-backend.spec` is PyInstaller configuration, but PyInstaller is not pinned in requirements.txt. |

**NOT STARTED:** no machine-learning decision engine or NSGA-II implementation was found in `backend/app/`; selection and optimization are ordinary Python and CP-SAT (`ComponentSelector`, `CPSATPlacementOptimizer`).

## 2. Pipeline status table

Paths are relative to the repository root. The requested conceptual order is preserved in this table; section 4 explains the actual call order.

| Stage | Status | File(s) and symbols | What it really does | Limitations |
|---|---|---|---|---|
| Requirements | IMPLEMENTED | `backend/app/services/project_service.py::create/update`; `persistence/repositories.py::ProjectRepository.save_requirements`; `frontend/src/components/requirements/Questionnaire.tsx::Questionnaire` | Loads questionnaire definitions, captures answers, preserves source links and saves project drafts. | Executable panel engine is DB only; eight imported questions, no load schedule. |
| Validation | IMPLEMENTED | `backend/app/services/requirement_engine.py::RequirementEngine.validate_requirements/evaluate_dependencies` | Checks required values, types, options, integer fields, ranges and unknown fields; returns errors/warnings. | Few hardcoded cross-field warnings; not electrical design verification. Questionnaire allows up to 48 feeders, selector allows 24. |
| CEM | IMPLEMENTED | `backend/app/models/cem.py::CanonicalEngineeringModel`; `services/orchestrator.py::generate_design`; `persistence/revisions.py::write_revision` | Typed electrical model with requirements, calculations, components, graph, nets and connection IDs; saved snapshot and projections. | `loads`, `constraints`, `compliance`, `dirty_nodes` are declared but not populated by generation. Several declared CEM states are never assigned. |
| Calculations | PARTIAL | `backend/app/services/calculation_engine.py::CalculationEngine.calculate_db_parameters` | Seven numerical records: capacity, design current, busbar current, average feeder current, conductor area, voltage drop and heat. | Fixed diversity, resistance, equivalent length, current density and heat assumptions; feeder average does not size the chosen breakers. |
| Component Selection | PARTIAL | `backend/app/services/component_selector.py::ComponentSelector.select_components`; `persistence/repositories.py::CatalogRepository.engine_catalog` | Filters/sorts incomer and busbar candidates; adds SPD, feeders, neutral/earth bars and terminals. | Feeder part numbers and repeating mix are hardcoded; catalog restricted to legacy-import provenance; no price/availability/coordination scoring. |
| Electrical Graph | PARTIAL | `backend/app/services/graph_engine.py::GraphEngine.build_electrical_graph`; `models/electrical_graph.py::ElectricalGraphModel` | Builds a DB-specific typed component graph and a local NetworkX DiGraph. | Local NetworkX graph is discarded; neutral/earth typed edges are not added to it. No short-circuit, connectivity or protection analysis. |
| Netlist | PARTIAL | `backend/app/services/netlist_engine.py::NetlistEngine.generate_netlist/validate_netlist` | Makes stable main-phase, SPD, branch, neutral and PE connection records; validates IDs and terminal existence. | DB topology is Python-coded. Three-phase branches group multiple phases in one net and send all three outputs to the same terminal `LEFT`; this is not an electrically separated three-phase terminal model. |
| Schematic | PARTIAL | `backend/app/services/schematic_engine.py::SchematicEngine.generate_schematic_data`; `frontend/src/components/schematic/schematicGraph.ts::buildSchematicGraph` | Places symbols in fixed layers and makes terminal-linked wires; frontend adds fan-out junctions and React Flow curves. | Comment says hierarchical/Sugiyama, but positions are prescribed. Missing symbols/terminals silently skip wires. Frontend fan-out uses net membership, including the branch-net grouping problem. |
| PDM | IMPLEMENTED | `backend/app/models/pdm.py::PhysicalDesignModel`; `services/orchestrator.py::generate_design`; `persistence/revisions.py::write_revision` | Stores enclosure/backplate geometry, components, rails, routes, zones and validation; links each component to CEM. | `ducts`, separate `busbars` and `clearances` have types/projection loops but are not generated. Busbars exist as ordinary placed components. |
| Zoning | PARTIAL | `backend/app/services/zoning_engine.py::ZoningEngine`; `algorithms/layout_config.py::LayoutConfig.zone_of/pref_height`; `orchestrator.py::generate_design` | Solver uses category names and preferred heights; PDM copies enclosure zone rectangles. | Standalone ZoningEngine is not called. Enclosure zones are not hard CP-SAT containment constraints; configured dimensions do not recompute those rectangles. |
| Enclosure Selection | PARTIAL | `backend/app/services/enclosure_engine.py::EnclosureEngine.select_enclosure`; `persistence/repositories.py::MemoryEnclosures.find_best_fit`; `services/project_service.py::configure_enclosures` | Estimates minimum dimensions, filters plate size/heat/IP and chooses the smallest outer area; allows project dimension overrides. | Heuristic width/height; ordinal IP lookup; no depth fit in initial selection, no attempt with a larger enclosure after placement/routing fails, no enclosure co-optimization. |
| CP-SAT Placement | IMPLEMENTED | `backend/app/algorithms/cp_sat_placement.py::CPSATPlacementOptimizer.solve/_solve_rows`, `validate_layout` | Real OR-Tools model: rail-row choices, x/y grid positions, bounds, non-overlap and weighted objective. Independently checks output. | Fixed orientations and z levels; wire objective uses component-center Manhattan distances; heat term only favors height. Stops at first feasible attempted row count. |
| JPS-Theta* Routing | PARTIAL | `backend/app/algorithms/jps_theta_star.py::JPSThetaStarRouter.route_nets/_jps_search/_astar_search/_theta_star_smooth` | Routes each connection around buffered footprints; JPS attempts, grid A* fallback and line-of-sight smoothing; exact terminal endpoints. | Theta* name describes greedy post-smoothing, not a full Theta* search. 2D obstacles, interpolated z, no wire-wire separation, bend-radius or duct-fill constraints. |
| Physical Validation | PARTIAL | `backend/app/services/validation_engine.py::ValidationEngine.validate_pdm`; `api/routes_design.py::validate_placement` | Checks plate bounds, overlaps, spacing, route bounds/endpoints/obstacles and CEM/PDM identity; critical generated violations stop publication. | Axis-aligned footprints ignore rotation; component z/depth containment is not checked; manual endpoint omits CEM argument and does not save/reroute. Touching shapes have zero distance and escape the positive-distance clearance warning. |
| Thermal | PARTIAL | `backend/app/services/calculation_engine.py::calculate_db_parameters`; `services/validation_engine.py::validate_pdm`; `algorithms/cp_sat_placement.py::_solve_rows` | Formula estimate, sum of component heat losses, enclosure capacity filter, heat-per-litre warning and hot-item-height preference. | No temperatures, ambient, convection, hotspot solution or CFD. Two heat estimates differ; 0.45 W/L is hardcoded. |
| Parametric 3D | PARTIAL | `backend/app/services/cad_engine.py::CADEngine`; `persistence/parameters.py::resolve_parameters`; `persistence/assets.py::primitive_glb`; `frontend/src/components/threeD/Panel3DViewer.tsx` | Evaluates dimension parameters, creates boxes/routes, exports real GLB and FreeCAD Python text; frontend assembles previews from PDM. | **STUB/MOCK geometry:** imported equipment is illustrative boxes; GLB wires are line strips. No runtime FreeCAD execution or native feature tree; script enclosure is a solid box. |
| BOM | PARTIAL | `backend/app/services/orchestrator.py::generate_design`; `services/project_service.py::load_revision`; `frontend/src/components/bom/BOMTable.tsx::BOMTable` | One row per selected CEM component, with rating/quantity and PDM lookup. | No enclosure, rail, duct, wire-length procurement, fixings, ferrules, cost aggregation or purchasing export. No dedicated BOM tables were found in the baseline/mappings; rows are reconstructed from CEM. |
| Change Propagation | PARTIAL | `backend/app/services/change_propagation.py::ChangePropagationEngine`; `services/project_service.py::propagate`; `persistence/revisions.py::write_revision` | Regenerates the full design, publishes a new revision and reports before/after summaries; saves dependency records. | Static field-to-stage lists, no transitive graph scheduler or selective recomputation. `dirty_nodes` remains empty. |
| Frontend | PARTIAL | `frontend/src/pages/ProjectPage.tsx::ProjectPage`; `stores/projectStore.ts::useProjectStore`; `api/client.ts::request`; `components/threeD/Panel3DViewer.tsx` | Real API-backed questionnaire, projects/revisions, editors, catalog, validation, BOM and 3D previews. | Draft edits are local; schematic selection is not fully bidirectional; no authentication; browser/installer visual execution is **UNVERIFIED** here. |

### Estimated completion

**PARTIAL — approximately 63% of this prototype pipeline checklist.** The explicit rubric is five IMPLEMENTED stages at 1 point and fourteen PARTIAL stages at 0.5 points: `(5 + 14 × 0.5) / 19 = 63.2%`. No stage is entirely absent, but some contain STUB/MOCK data or geometry. Equal weighting is an audit convention, not a measured development schedule. Production engineering completion is **UNVERIFIED**: load schedules, electrical correctness, standards verification, manufacturer assets and manufacturing output are outside what these implemented checks establish. Evidence: stage symbols above; especially `NetlistEngine.generate_netlist`, `CalculationEngine.calculate_db_parameters`, `ValidationEngine.validate_pdm` and `CADEngine`.

## 3. Repository map

Each entry describes existing code/configuration. `[I]`, `[P]`, `[M]` mean IMPLEMENTED, PARTIAL and STUB/MOCK respectively.

```text
Electrical_Panel_Design_Automation/
├── README.md, DB_WORKFLOW.md                    [P] Usage/architecture narrative; not proof of execution.
├── TEST_CASES_FOR_TEACHER.md                    [P] Manual demonstration instructions.
├── LAYOUT_PIPELINE_INTEGRATION_SUMMARY.md        [P] Historical implementation notes.
├── Directory_Structure.txt, Unified_Architecture.txt, Architecture_1.png
│                                               [P] Reference descriptions/diagram, not runtime logic.
├── docs/database/
│   ├── 001_core.sql                            [I] Original PostgreSQL DDL; frozen copy is migration baseline.
│   ├── 002_sample_data.sql                     [M] Illustrative SQL reference catalog/project records.
│   ├── 003_example_queries.sql                 [P] Query examples, not API execution.
│   └── README.md, python_persistence.md, INTEGRATION_PLAN.md,
│       OPERATIONS.md, INTEGRATION_RESULT.md      [P] Schema, historical plans and operational documentation.
├── backend/
│   ├── requirements.txt, alembic.ini            [I] Python pins and migration configuration.
│   ├── desktop_main.py                         [I] Loopback sidecar entry point; watches parent stdin.
│   ├── panel-backend.spec                      [P] PyInstaller recipe; actual packaging UNVERIFIED.
│   ├── migrations/env.py                       [I] Alembic Settings/metadata connection.
│   ├── migrations/versions/0001_baseline.py/.sql [I] Frozen baseline migration.
│   ├── migrations/versions/0002_app.py          [I] Project state/concurrency and conductor endpoint additions.
│   ├── tools/build_schema_models.py            [I] Builds reflected mappings/manifest using a temporary DB.
│   ├── tools/initialize_development.py          [I] Development backup/adoption/import helper.
│   ├── app/main.py                             [I] create_app, lifespan, CORS, error handlers and readiness.
│   ├── app/api/dependencies.py                 [I] Request DB/session/service dependencies.
│   ├── app/api/routes_projects.py              [I] Project/answer/revision CRUD subset.
│   ├── app/api/routes_requirements.py          [I] Questionnaire and input validation.
│   ├── app/api/routes_design.py                [P] Generate, propagate, advisory placement validation.
│   ├── app/api/routes_catalog.py               [I] Catalog, archetypes, rules and enclosure reads.
│   ├── app/api/routes_assets.py                [I] Metadata and verified managed-file downloads.
│   ├── app/api/routes_cad.py                   [P] Primitive/script views and local export jobs.
│   ├── app/api/routes_layout.py, routes_schematic.py, routes_validation.py
│   │                                           [I] Saved revision projections for views.
│   ├── app/models/requirements.py              [I] Question, dependency and resolved-requirement contracts.
│   ├── app/models/cem.py                       [P] Electrical contracts; some collections remain empty.
│   ├── app/models/electrical_graph.py           [I] Typed graph nodes/edges.
│   ├── app/models/pdm.py                       [P] Physical contracts; some structures remain empty.
│   ├── app/models/api.py                       [I] Typed HTTP requests/responses and optimistic versions.
│   ├── app/services/project_service.py         [I] DB reads, pure engine call, files, publish/load/restore/jobs.
│   ├── app/services/orchestrator.py            [I] Engineering stage coordinator.
│   ├── app/services/requirement_engine.py       [I] Questionnaire validation/default/dependency evaluation.
│   ├── app/services/calculation_engine.py      [P] Seven fixed-assumption calculations.
│   ├── app/services/component_selector.py      [P] Filtering plus hardcoded feeder mix.
│   ├── app/services/graph_engine.py            [P] Fixed DB relationship construction.
│   ├── app/services/netlist_engine.py          [P] Terminal connections and reference validation.
│   ├── app/services/schematic_engine.py        [P] Fixed symbol positions and orthogonal paths.
│   ├── app/services/enclosure_engine.py        [P] Heuristic required size followed by fit filtering.
│   ├── app/services/zoning_engine.py           [P] Standalone fixed zones; not called by generation.
│   ├── app/services/validation_engine.py       [P] 2D physical/identity/thermal-density checks.
│   ├── app/services/cad_engine.py              [P] Box primitives and generated FreeCAD script.
│   ├── app/services/change_propagation.py      [P] Static affected-stage lists and summary diff.
│   ├── app/services/design_errors.py           [I] Structured DesignError response contract.
│   ├── app/algorithms/cp_sat_placement.py       [I] CP-SAT model, extraction and independent layout checks.
│   ├── app/algorithms/jps_theta_star.py         [P] JPS/A* routing and greedy visibility smoothing.
│   ├── app/algorithms/layout_config.py         [I] Grid, margins, solver budgets, category maps and weights.
│   ├── app/persistence/config.py, database.py  [I] Secret environment configuration, engine and readiness.
│   ├── app/persistence/models.py               [I] SQLAlchemy table/ORM mappings, not domain CEM/PDM classes.
│   ├── app/persistence/ports.py                [I] Protocol contracts, not additional storage adapters.
│   ├── app/persistence/repositories.py         [I] SQL queries, DTO construction and memory engine adapters.
│   ├── app/persistence/revisions.py            [I] Atomic snapshots, projections, provenance and dependencies.
│   ├── app/persistence/assets.py               [I] Local content-addressed storage and primitive GLB writer.
│   ├── app/persistence/parameters.py           [I] Restricted arithmetic/unit/parameter evaluation.
│   ├── app/persistence/import_legacy.py        [I] Explicit JSON-to-PostgreSQL import and box previews.
│   ├── app/persistence/manage.py               [I] initialize/status/import/asset-audit CLI.
│   ├── app/persistence/schema_tools.py, baseline_manifest.json
│   │                                           [I] Structural verification before adopting an existing schema.
│   ├── app/repositories/                      [P] Old JSON adapters used by direct/default engine calls.
│   ├── app/data/components.json, enclosures.json, panel_templates.json,
│   │   rules.json, sample_projects.json        [M] Prototype fixtures/import sources, not HTTP runtime storage.
│   ├── app/execution_details.txt               [P] Notes, not execution logic.
│   └── tests/test_backend.py, test_postgres.py, conftest.py
│                                               [I] Unit/API/integration tests and isolated database fixture.
└── frontend/
    ├── package.json, package-lock.json         [I] NPM scripts/dependency declarations and lockfile.
    ├── vite.config.ts, tsconfig*.json          [I] Build/types, port 3000 and API proxy.
    ├── .env.development                       [I] Public backend URL only; no DB credentials.
    ├── tailwind.config.*, postcss.config.*     [I] Styling build configuration.
    ├── src/main.tsx, App.tsx, MainApp.tsx       [I] React mount, readiness/retry gate and application shell.
    ├── src/pages/ProjectPage.tsx               [I] Single page with seven conditional tabs.
    ├── src/api/config.ts, backend.ts, client.ts[I] API URL, readiness polling and typed HTTP client.
    ├── src/types/cem.ts, pdm.ts, api.ts         [I] Frontend data contracts.
    ├── src/stores/projectStore.ts             [P] Saved/current design state and local editor history.
    ├── src/components/common/                 [I] Header/tab controls and change-diff modal.
    ├── src/components/projects/               [I] Save/open/restore bar and enclosure parameter inputs.
    ├── src/components/requirements/           [I] Backend-defined questionnaire.
    ├── src/components/catalog/                [I] Filtered/paginated catalog with asset previews.
    ├── src/components/schematic/              [P] React Flow graph, draft edits and local checks.
    ├── src/components/layout/                 [P] SVG layout/editor and advisory validation.
    ├── src/components/threeD/                 [P] PDM viewer, GLB loader, camera and draft geometry helpers.
    ├── src/components/bom/, validation/        [P] CEM item table and implemented-check display.
    ├── src/**/*.test.ts*                      [I] State, API, graph, geometry and component tests.
    └── src-tauri/Cargo.toml, tauri.conf.json, capabilities/, src/lib.rs
                                                [P] Desktop configuration and sidecar lifecycle.
```

**PARTIAL documentation accuracy:** `README.md` still mentions standard/heavy preset buttons and an SVG schematic in feature descriptions. Current `Questionnaire` is server-driven and current `SchematicCanvas` uses React Flow. Documentation was not used to override source evidence.

## 4. End-to-end flow for the requested example

### Real entry point and input

**IMPLEMENTED:** `frontend/src/main.tsx` mounts `App`; `App` calls `waitForBackend` (`frontend/src/api/backend.ts`) before `MainApp` renders `ProjectPage`. `useProjectStore.initializeProjects` loads projects/archetypes; it prefers `PROJ_DB_DEMO_001`, otherwise a DB project. Opening does not generate a design. `Questionnaire.handleValidate` calls `validateCurrentRequirements`, then `runDesignPipeline`. The Header can also call the generation action.

**IMPLEMENTED:** for a new project, `api/client.ts::createProject` calls `POST /api/projects` → `routes_projects.create_project` → `ProjectService.create`. For an existing project, `generateDesign` normally posts the following body to `POST /api/projects/{project_id}/revisions` (real `lock_version` is supplied from the project response):

```json
{
  "expected_version": 1,
  "requirements": {
    "supply_voltage": 415,
    "phases": 3,
    "frequency": 50,
    "incomer_rating": 250,
    "num_feeders": 12,
    "spare_capacity_pct": 20,
    "ip_rating": "IP54",
    "neutral_required": true
  },
  "configuration": {}
}
```

**IMPLEMENTED:** `routes_projects.create_revision` passes requirements/version/configuration to `ProjectService.generate`. The older `/design/generate` endpoint is also connected, but the version-aware frontend path uses `/revisions` (`frontend/src/api/client.ts::generateDesign`).

### True call order

The rows follow actual source order. Samples are literal input/ID/formula examples; measured scenario output is recorded after the trace.

| Step / status | File and function | Input → output and concrete sample |
|---|---|---|
| 1 IMPLEMENTED | `backend/app/services/project_service.py::ProjectService._inputs` | Project ID → saved requirements/configuration, pinned questionnaire, published imported component rows, enclosures, CAD definitions, rule versions and `LayoutConfig`. `DB_LAYOUT_CONFIG` and `DB_ENGINE_V1` are required. SQL read session closes before solving. |
| 2 IMPLEMENTED | Same file, `validate`, `configure_enclosures`, `generate` | Merge saved requirements with overrides; compare optimistic version; validate answers; optionally evaluate enclosure dimensions. `{}` configuration means automatic enclosure choice. No override here. |
| 3 IMPLEMENTED | `backend/app/services/orchestrator.py::DesignOrchestrator.generate_design`; `requirement_engine.py::validate_requirements` | Memory adapters from DB inputs → another validated `RequirementSet`. Sample item: `id="num_feeders", value=12, state="CONFIRMED", source="USER"`. No JSON persistence is requested (`persist_requirements=False`). |
| 4 IMPLEMENTED | `orchestrator.py::generate_design`; `models/cem.py::CanonicalEngineeringModel/FunctionalModule` | Resolved requirement items/template modules → CEM state `REQUIREMENTS_VALIDATED`, `panel_id="DB-<project_id>"`, modules such as `MOD-INCOMER`. Neutral module remains required for this example. |
| 5 PARTIAL | `services/calculation_engine.py::calculate_db_parameters` | 415 V / 3 / 250 A / 12 / 20% → seven calculation records. Capacity 179.70 kVA; design current 225 A; busbar record 312 A after Python rounding; average feeder 16.7 A; conductor area 113.6 mm²; voltage drop about 0.27%; heat estimate 80 W. CEM becomes `ENGINEERING_CALCULATED`. |
| 6 PARTIAL | `services/component_selector.py::select_components`; `orchestrator.py::generate_design` | Requested 250 A and calculated busbar record → `QF001` incomer, `BUS001`, `SPD001`, twelve `QF002..QF013`, `NBAR01`, `PEBAR01`, twelve `X001..X012`. Every fourth feeder is a 40 A 3P model; even remaining feeders use 32 A; odd use 16 A. Modules get only the first matching component ID. CEM becomes `COMPONENTS_SELECTED`. |
| 7 PARTIAL | `services/graph_engine.py::build_electrical_graph` | Selected components → typed nodes/edges. Example edge: `QF001 → BUS001`, relation `FEEDS`, wire class `POWER`; panel root is `PANEL_ROOT`. |
| 8 PARTIAL | `services/netlist_engine.py::generate_netlist/validate_netlist`; `orchestrator.py::generate_design` | Graph argument plus components/voltage/phases → nets and individual connections; validation verifies references. `NET-MAIN-L1-C01` connects `QF001.L1_OUT` to `BUS001.IN_L1`. Orchestrator flattens `cem.connections` and adds net IDs to typed graph edges; CEM becomes `NETLIST_VALIDATED`. Netlist topology actually derives from component categories, not traversal of the graph argument. |
| 9 PARTIAL | `services/schematic_engine.py::generate_schematic_data` | CEM → symbol/wire arrays on 1200×700 canvas. `QF001` symbol at x=550,y=50,width=100,height=70. Connection ID becomes wire ID; orthogonal path uses a midpoint y. CEM becomes `SCHEMATIC_GENERATED`. |
| 10 PARTIAL | `services/enclosure_engine.py::select_enclosure`; `persistence/repositories.py::MemoryEnclosures.find_best_fit` | Sum widths of MCCB/MCB/SPD/BUSBAR and sum all selected heat → heuristic plate requirements; IP54/heat filter → smallest feasible enclosure. Heat comes from catalog components here, not CALC_007. There is no preceding `ZoningEngine` call. |
| 11 IMPLEMENTED | `algorithms/cp_sat_placement.py::CPSATPlacementOptimizer.solve/_solve_rows` | Components + chosen outer width/height + non-root component connection pairs + adjusted margins → placements and DIN rails. Positions are lower-left-front mm. `_mk` produces `id="PDM-QF001", cem_component_id="QF001"`; plate z=20, DIN z=30 by default. It does not use enclosure zone rectangles as constraints. |
| 12 PARTIAL | `algorithms/jps_theta_star.py::route_layout/route_nets` | Placement, nets and enclosure → one route per connection. For each terminal pair: build obstacles/corridors, try JPS with/without preference, A* if needed, smooth, restore exact terminal endpoints and validate path clearance. Example route ID `ROUTE-NET-MAIN-L1-C01`, linked to `NET-MAIN-L1`. |
| 13 IMPLEMENTED | `services/orchestrator.py::generate_design`; `models/pdm.py::PhysicalDesignModel` | Enclosure + placements/rails/routes + copied zones + catalog heat → PDM `id="PDM-<project_id>"`, `panel_id` matching CEM. This construction occurs after routing, not before zoning/enclosure selection. |
| 14 PARTIAL | `services/validation_engine.py::validate_pdm` | PDM, CEM and layout configuration → violations; mutates `thermal_density_index = heat / litres`. CRITICAL violations cause `PHYSICAL_VALIDATION_FAILED`. Warnings do not stop generation. There is no independent later thermal solver. |
| 15 PARTIAL | `services/orchestrator.py::generate_design`; `cad_engine.py::generate_parametric_geometry` | Validated PDM → `cem.physical_design_id=pdm.id`, CEM `FINAL_VALIDATED`, CAD primitive list with `units="mm"`; e.g. component box includes CEM/PDM IDs, centre position and dimensions. Component-only BOM is built from CEM. |
| 16 IMPLEMENTED | `services/project_service.py::generate/generate_files` | Engineering package → component/product/CAD version IDs and preview metadata; pinned rule/model/input-hash manifest; real GLB bytes through `primitive_glb`, FreeCAD text through `export_freecad_script`. `AssetStore.put` writes files before DB publication. |
| 17 IMPLEMENTED | `persistence/revisions.py::write_revision` | Package/answers/manifest/file records → published revision, CEM/PDM JSON snapshots, terminals/nets/conductors, physical projections, validation, dependencies and artifact records in one DB transaction. `check_version` locks project row; `touch` advances revision pointer and version. |
| 18 IMPLEMENTED | `services/project_service.py::load_revision` | New revision ID → verified snapshots plus regenerated schematic/primitives/BOM views, revision number, manifest, artifact URLs and stale flag. It does not rerun placement/routing. Snapshots are preserved; these derived views use the currently installed view-generation code. |
| 19 PARTIAL | `frontend/src/stores/projectStore.ts::runDesignPipeline`; `ProjectPage`; `Panel3DViewer` | HTTP package → saved-design state and tabs. 2D/3D use PDM placements; schematic/BOM use CEM-linked IDs. GLB files load through asset URLs; local transforms remain editor drafts. |

**PARTIAL calculation detail:** `round(incomer_rating * 1.25, 0)` turns 312.5 into 312.0 for the busbar calculation. The sample still selects the next available adequate busbar, but this rounding weakens the stated lower bound for a catalog rating near that boundary (`CalculationEngine.calculate_db_parameters`, `ComponentSelector.select_components`).

### Executed example evidence

**IMPLEMENTED runtime trace:** an ephemeral Python audit harness used the existing `tests/conftest.py::postgres_database` fixture and `TestClient(create_app(db))` to exercise the real create/revision/propagation routes. It loaded migrations, the SQL reference fixture and unchanged JSON imports. Assets were temporary; test databases were removed by the fixture. The harness was supplied on stdin and added no source file. All values below came from the returned baseline HTTP 201 package, not from an invented layout.

| Output / status | Observed baseline data | Producer |
|---|---|---|
| CEM — IMPLEMENTED | `state=FINAL_VALIDATED`; 29 components, 30 graph nodes, 29 typed graph edges, 20 nets, 44 connections. | `DesignOrchestrator.generate_design`, `GraphEngine.build_electrical_graph`, `NetlistEngine.generate_netlist` |
| Selected equipment — PARTIAL | `QF001.catalog_id=MCCB_250A_3P_36KA`; 250 A, 36 kA, 3 poles, 105×165×85 mm; `BUS001.catalog_id=BUSBAR_TPN_400A`. | `ComponentSelector.select_components` |
| Enclosure — PARTIAL | `ENC_800_1000_300`, 800×1000×300 mm, IP54. | `EnclosureEngine.select_enclosure`, `MemoryEnclosures.find_best_fit` |
| Placement — IMPLEMENTED | `PDM-QF001`: `(305,790,20)` mm, rotation 0°, no rail, zone INCOMING; 3 rails overall. | `CPSATPlacementOptimizer.solve/_mk` |
| Main L1 net — PARTIAL | `NET-MAIN-L1`, nominal voltage 415; `NET-MAIN-L1-C01`: `QF001.L1_OUT → BUS001.IN_L1`. | `NetlistEngine.generate_netlist` |
| Route — PARTIAL | `ROUTE-NET-MAIN-L1-C01`: 458.3 mm, 4 bends; endpoints `(322.5,790,62.5)` and `(80,505,35)` mm; 44 routes overall. | `JPSThetaStarRouter.route_nets` |
| Schematic — PARTIAL | 30 symbols and 44 wires; root symbol accounts for the extra symbol beyond purchased CEM parts. | `SchematicEngine.generate_schematic_data` |
| Thermal — PARTIAL | CALC_007 = 80 W; catalog component total = 117.5 W; density = 0.490 W/L. One THERMAL WARNING exceeds 0.45 W/L; publication still succeeds. | `CalculationEngine.calculate_db_parameters`, `ValidationEngine.validate_pdm` |
| Geometry/artifacts — PARTIAL | GLB and PY artifact metadata both READY; incomer preview is a 1,672-byte GLB. | `ProjectService.generate_files`, `AssetStore.put`, `primitive_glb` |
| Unpopulated models — PARTIAL | `loads`, `constraints`, `compliance`, `dirty_nodes`, `ducts`, separate `busbars`, `clearances` all have length zero. | `CanonicalEngineeringModel`, `PhysicalDesignModel`, `DesignOrchestrator.generate_design` |

Trimmed **real returned data** (`PhysicalComponent`, `WireRoute`), with no credential or machine-local asset path:

```json
{
  "component": {
    "id": "PDM-QF001",
    "cem_component_id": "QF001",
    "position": {"x": 305.0, "y": 790.0, "z": 20.0},
    "width": 105.0,
    "height": 165.0,
    "depth": 85.0,
    "zone_name": "INCOMING"
  },
  "route": {
    "id": "ROUTE-NET-MAIN-L1-C01",
    "net_id": "NET-MAIN-L1",
    "waypoints": [
      {"x": 322.5, "y": 790.0, "z": 62.5},
      {"x": 322.5, "y": 775.0, "z": 62.5},
      {"x": 50.0, "y": 540.0, "z": 53.3},
      {"x": 45.0, "y": 535.0, "z": 44.2},
      {"x": 40.0, "y": 505.0, "z": 35.0},
      {"x": 80.0, "y": 505.0, "z": 35.0}
    ],
    "length_mm": 458.3,
    "bend_count": 4
  }
}
```

The first waypoint equals the component origin plus terminal-local `(17.5,0,42.5)` mm. This is actual endpoint traceability, but does not correct the electrical net semantics discussed above. Positions are observations from this run, not a guarantee of bit-identical optimizer results on every platform (`JPSThetaStarRouter._component_terminal`, `CPSATPlacementOptimizer._solve_rows`).

## 5. Data models and ID links

### CEM — IMPLEMENTED contract, PARTIAL engineering content

Source: `backend/app/models/cem.py::CanonicalEngineeringModel`, `ComponentRef`, `ConnectionRef`, `NetRef`, `CalculationResult`, `FunctionalModule`; populated by `DesignOrchestrator.generate_design`.

| Fields | Actual meaning / limitation |
|---|---|
| `project_id`, `panel_id`, `panel_type`, `revision`, `state` | Project/panel identity; panel type DB. `revision` defaults to string `1.0.0` and is not the database revision counter. Actual history is `project_revisions.revision_no` (`write_revision`). |
| `requirements` | Resolved `RequirementItem` values, units, state, source and messages. |
| `modules` | Template categories; `assigned_component_id` points to the first selected component of the category, not all feeders. |
| `components` | Logical `id`, `catalog_id`, optional pinned component/product/CAD UUIDs; ratings, dimensions, mounting, heat, source CAD name, quantity and terminal dictionaries. |
| `electrical_graph` | Typed nodes/edges/properties; root includes `PANEL_ROOT`. |
| `nets`, `connections` | Nets have ID/name/voltage/class and connection list. Connection has own ID, net ID and from/to component and terminal IDs. Flat connections mirror nested net connections. |
| `calculations` | Seven formula/value/unit/status records from the calculation engine. |
| `physical_design_id` | Link to PDM string ID after physical validation. |
| `loads`, `constraints`, `compliance`, `dirty_nodes` | **PARTIAL:** declared collections, left empty by this generator. Their presence does not mean a load model, compliance engine or incremental scheduler exists. |

### PDM — IMPLEMENTED contract, PARTIAL structure generation

Source: `backend/app/models/pdm.py::PhysicalDesignModel`, `PhysicalComponent`, `DINRail`, `WireRoute`, `PhysicalZone`, `ValidationViolation`; built in `DesignOrchestrator.generate_design` and enriched in `ProjectService.generate`.

| Fields | Actual meaning / limitation |
|---|---|
| `id`, `project_id`, `panel_id`, `enclosure_id` | Physical/project/panel and selected catalog enclosure identifiers. |
| `enclosure_width/height/depth`, `ip_rating` | Millimetre dimensions and declared catalog IP value. No IP certification check. |
| `mounting_plate_x/y/z/width/height` | Backplate origin and planar dimensions in the enclosure frame. |
| `components` | `id="PDM-<CEM ID>"`, `cem_component_id`, lower-corner `position`, dimensions, z-rotation, rail/zone, heat, terminal dictionaries, CAD model UUID and preview asset. |
| `rails` | Generated horizontal DIN rails; ID, position, length and fixed/default profile dimensions. |
| `routes` | Route ID, net ID/name, endpoint component/terminal IDs, class, waypoints, length, bends and color. |
| `zones` | Copied enclosure rectangles; not authoritative solver partitions. |
| `validation_results`, `total_heat_loss_watts`, `thermal_density_index` | Validator output, component heat sum and whole-enclosure W/L. |
| `ducts`, `busbars`, `clearances` | **PARTIAL:** schema/default lists and persistence support exist; orchestrator leaves them empty. Virtual routing corridors are not physical duct objects. |

**IMPLEMENTED ID chain**, from `CPSATPlacementOptimizer._mk`, `NetlistEngine.generate_netlist`, `JPSThetaStarRouter.route_nets` and `write_revision`:

```text
catalog code MCCB_250A_3P_36KA -> CEM instance QF001
QF001 -> PDM-QF001 (cem_component_id = QF001)
QF001.L1_OUT -> NET-MAIN-L1-C01 -> BUS001.IN_L1
NET-MAIN-L1-C01 -> ROUTE-NET-MAIN-L1-C01
PDM-QF001 -> CAD-PDM-QF001 (primitive metadata)
BOM.component_id = QF001
```

**IMPLEMENTED persistence separation:** `write_revision` creates fresh relational UUIDs for a revision while storing these logical IDs as `stable_key`/`conductor_code`. `pdm_component_instances.cem_component_instance_id` is an FK; conductor endpoint UUIDs reference `cem_terminal_instances`; routes reference conductor/net UUIDs. `PANEL_ROOT` gets an enclosure-interface projection, without becoming a purchased CEM/BOM component. Hashes and pinned versions are recorded in snapshot/revision tables. There is no universal SQL trigger enforcing immutable published rows; the application APIs/writer preserve history by publishing new revisions (`persistence/revisions.py::write_revision`, migrations `0001_baseline.sql`, `0002_app.py::upgrade`).

## 6. Twelve key code blocks

Snippets are trimmed excerpts of existing code. An ellipsis means omitted lines, not missing code in the repository. Related functions are grouped to cover both the application boundary and the engineering pipeline.

### 1. IMPLEMENTED — application boundary and orchestrator

`backend/app/services/project_service.py::ProjectService.generate`:

```python
engine=DesignOrchestrator(project_repo=MemoryProjects(project),comp_repo=MemoryComponents(rows),
    enclosure_repo=MemoryEnclosures(enclosures,selected),req_engine=RequirementEngine(templates={'DB':template}),layout_config=layout)
result=engine.generate_design(project['id'],values,persist_requirements=False)
```

`backend/app/services/orchestrator.py::DesignOrchestrator.generate_design`:

```python
cem.calculations = self.calc_engine.calculate_db_parameters(values)
...
graph = self.graph_engine.build_electrical_graph(project_id, components)
...
violations = self.validation_engine.validate_pdm(pdm, cem, plate_cfg)
...
cem.physical_design_id = pdm.id
cem.state = CEMState.FINAL_VALIDATED
cad_data = self.cad_engine.generate_parametric_geometry(pdm)
```

Database reads are materialized before the pure engine runs. Validation gates output, and persistence happens afterward in the service. The API does not use the orchestrator's default JSON repositories.

### 2. IMPLEMENTED — requirement validation

`backend/app/services/requirement_engine.py::RequirementEngine.validate_requirements`:

```python
effective_values = {q.id: q.default for q in questions}
effective_values.update(values)
visible_questions = self.evaluate_dependencies(questions, effective_values)
...
for unknown in sorted(set(values) - known_ids):
    errors.append(f"Unknown requirement field '{unknown}'.")
...
"number": lambda x: type(x) in (int, float) and math.isfinite(x),
```

Defaults and visibility determine applicable questions. Type/option/range checks create explicit errors before calculation. Unknown dependency operators are not explicitly rejected by the backend evaluator, while frontend `dependencyMatches` returns false for them (`Questionnaire.tsx`): their general consistency is **PARTIAL**.

### 3. PARTIAL — calculations and component selection

`backend/app/services/calculation_engine.py::CalculationEngine.calculate_db_parameters`:

```python
diversity_factor = 0.75  # Standard DB diversity factor
design_load_current = incomer_rating * diversity_factor * (1.0 + spare_capacity)
...
busbar_rating = incomer_rating * 1.25  # 125% safety margin rule
...
conductor_area_mm2 = incomer_rating / 2.2
```

The formulas execute, but the comments do not prove these constants apply to a real installation. Actual cable type, derating, ambient and fault data are absent.

`backend/app/services/component_selector.py::ComponentSelector.select_components`:

```python
mccb_candidates.sort(key=lambda item: (item["current_rating"], item["width"], item["id"]))
...
if i % 4 == 0 and phases == 3:
    template_mcb = mcb_40a_3p
elif i % 2 == 0:
    template_mcb = mcb_32a
else:
    template_mcb = mcb_16a
```

Incomer selection is filter-and-sort. Feeders are a repeating demonstration pattern, not the result of each feeder's load calculation.

### 4. PARTIAL — netlist generation

`backend/app/services/netlist_engine.py::NetlistEngine.generate_netlist`:

```python
endpoints = [(busbar.id, f"IN_L{p}", mcb.id, f"L{p}_IN")
             for p in range(1, min(phase_count, phases) + 1)]
endpoints += [(mcb.id, f"L{p}_OUT", terminal_id, "LEFT")
              for p in range(1, min(phase_count, phases) + 1)]
...
add_net(f"NET-BRANCH-{mcb.id}", f"Branch Circuit {mcb.id} to {terminal_id}",
        branch_voltage, "POWER", endpoints)
```

Connections get stable IDs and valid terminal references, but all three outputs share the same terminal and branch net. `validate_netlist` checks references, not electrical separation or the meaning of a net across a breaker. This is a major correctness gap.

### 5. PARTIAL — unused standalone zoning

`backend/app/services/zoning_engine.py::ZoningEngine.get_default_zones/classify_zone`:

```python
PhysicalZone(name="INCOMING", x_min=30, x_max=width-30, y_min=height*0.75, y_max=height-30),
...
if category == "MCCB":
    return "INCOMING"
```

These are fixed rectangles/category labels. There is no call to this class from the current generation path. Active labels/preferences come from `LayoutConfig.zone_of/pref_height`; PDM rectangles come from the enclosure record (`DesignOrchestrator.generate_design`).

### 6. IMPLEMENTED — CP-SAT model and objective

`backend/app/algorithms/cp_sat_placement.py::CPSATPlacementOptimizer._solve_rows`:

```python
m = cp_model.CpModel()
...
m.AddExactlyOne(b)
...
m.AddNoOverlap(row_iv[r])
...
m.AddNoOverlap2D(xs, ys)
...
terms.append(cw * (dx + dy))
...
terms.append(coef * (Hg - cy[c.id]))
...
terms += [zc * t for t in zone_terms]
if terms:
    m.Minimize(sum(terms))
```

DIN devices choose one rail row; plate devices occupy non-overlapping rectangles outside rail bands. The weighted sum combines wire-distance proxy, upward heat preference and category-height deviation. It is not a Pareto search or a temperature solution. Solver result extraction is real, with an independent geometry pass in `validate_layout`.

### 7. PARTIAL — routing search and smoothing

`backend/app/algorithms/jps_theta_star.py::JPSThetaStarRouter.route_nets`:

```python
raw_grid_path = self._jps_search(start_grid, goal_grid, blocked, preferred,
                                  enclosure_w, enclosure_h)
if not raw_grid_path:
    raw_grid_path = self._jps_search(start_grid, goal_grid, blocked, set(),
                                      enclosure_w, enclosure_h)
if not raw_grid_path:
    raw_grid_path = self._astar_search(start_grid, goal_grid, blocked, set(),
                                        enclosure_w, enclosure_h)
...
smoothed = self._theta_star_smooth(raw_grid_path, blocked)
```

The route searches a bounded occupancy grid. `_theta_star_smooth` chooses the furthest visible later node from each anchor; it is greedy path simplification after search. `_route_is_clear` independently checks physical buffered segments before accepting the route.

### 8. PARTIAL — physical and thermal checks

`backend/app/services/validation_engine.py::ValidationEngine.validate_pdm`:

```python
poly = box(c.position.x, c.position.y, c.position.x + c.width, c.position.y + c.height)
...
if inter_area > 0.01:
    violations.append(ValidationViolation(
        type="OVERLAP",
        severity="CRITICAL",
        ...
    ))
...
thermal_index = pdm.total_heat_loss_watts / max(1.0, (enc_w * enc_h * pdm.enclosure_depth) / 1000000.0)
pdm.thermal_density_index = round(thermal_index, 3)
```

Shapely checks 2D rectangles and buffered routes. The thermal value is whole-volume W/L, not temperature. Rotations/depth are not included in those component rectangles. Generated routes also get identity/terminal checks when the orchestrator supplies CEM.

### 9. PARTIAL — change propagation

`backend/app/services/change_propagation.py::ChangePropagationEngine.identify_dirty_nodes`:

```python
dirty = set()
dirty.add(modified_field)
downstream = self.DEPENDENCY_DAG.get(modified_field, [])
for node in downstream:
    dirty.add(node)
return dirty
```

`backend/app/services/project_service.py::ProjectService.propagate`:

```python
new=self.generate(key,{field:value},version)
return {'new_design':new,'diff_report':ChangePropagationEngine().compute_diff(...)}
```

The affected-stage report is a static lookup; actual execution regenerates everything. Persisted `revision_dependencies` provide trace records, but are not queried as an execution scheduler.

### 10. IMPLEMENTED — revision publication

`backend/app/services/project_service.py::ProjectService.generate` and `backend/app/persistence/revisions.py::write_revision`:

```python
files=self.generate_files(result)
with self.db.sessions.begin() as s:
    saved=write_revision(s,project,template,reqs,values,result,manifest,files,project['lock_version'])
```

```python
row=repo.check_version(project['id'],expected_version)
...
cem_hash,pdm_hash=content_hash(cem),content_hash(pdm)
...
repo.touch(row,current_revision_id=rid,configuration=project.get('configuration',{}))
```

All database projections/snapshots belong to one transaction and a checked project version. Files are outside that transaction, so a failed commit can leave unreferenced files. `manage audit-assets` reports them without deleting history.

### 11. IMPLEMENTED — frontend API client

`frontend/src/api/client.ts::request/generateDesign`:

```typescript
const response = await fetch(API_BASE.replace(/\/$/, '') + path, { ...options, signal: controller.signal,
  headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
...
version ? request<DesignPackage>('/projects/' + id(projectId) + '/revisions',
  json('POST', { requirements: overrides, expected_version: version, configuration }), 90000) :
  request<DesignPackage>('/projects/' + id(projectId) + '/design/generate', json('POST', overrides), 90000);
```

Calls use one configured backend base URL, cancellation and normalized errors. Generation gets a 90-second client timeout; ordinary requests default to 30 seconds. A timeout is not proof the server rolled back, as the timeout message correctly explains.

### 12. PARTIAL — PDM-based 3D viewer and assets

`frontend/src/components/threeD/Panel3DViewer.tsx::ComponentMesh`:

```tsx
const scale = 0.01;
...
(transform.x + comp.width / 2) * scale,
(transform.y + comp.height / 2) * scale,
(transform.z + comp.depth / 2) * scale + explodedZOffset,
...
<AssetObject url={assetUrl(comp.preview_asset.url)} scale={10}
  fallback={<mesh><boxGeometry args={[w,h,d]}/><meshStandardMaterial color={comp.color_hex}/></mesh>}/>
```

`frontend/src/components/threeD/AssetObject.tsx::LoadedAsset`:

```tsx
const {scene}=useGLTF(url);
return <Clone object={scene} scale={scale}/>;
```

PDM dimensions are mm and preview meshes are centred; glTF metres need ×10 in the viewer's 100 mm world unit. The loader clones scene nodes, provides loading/error fallback, and does not mutate cached source geometry. Imported meshes are still prototype boxes; an asset URL does not make them detailed manufacturer models.

## 7. Algorithms actually used

| Algorithm / status | Where | Inputs → outputs | Actual behavior and limits |
|---|---|---|---|
| CP-SAT — IMPLEMENTED | `backend/app/algorithms/cp_sat_placement.py::solve/_solve_rows` | Selected component rectangles, outer size, component-pair connections, LayoutConfig → feasibility/status, placements, rails, internal objective/bound. | Integer grid with optional row intervals and plate rectangles; minimizes weighted proxy sum. Status can be FEASIBLE, not proven OPTIMAL; API package does not expose the complete LayoutResult diagnostics. |
| JPS — PARTIAL | `backend/app/algorithms/jps_theta_star.py::_jps_search/_jump/_jump_exists/_has_forced_neighbour/_pruned_directions` | Start/goal cells, blocked cells/corridors and limits → grid path or empty list. | Real custom jumping/forced-neighbor code; second attempt removes corridor preference, then A* fallback. Global shortest-path/optimality guarantee is **UNVERIFIED**; Euclidean heuristic plus discounted corridor moves is not demonstrated as admissible in tests. |
| A* fallback — IMPLEMENTED | Same file, `_astar_search` | Same grid inputs → eight-neighbor path; prevents diagonal corner cutting. | Bounded by enclosure grid, not a real-time deadline. It is used when JPS fails, so not every successful route proves JPS succeeded. |
| Theta* — PARTIAL | Same file, `_theta_star_smooth/_line_of_sight` | Existing grid path/blocked cells → fewer visible waypoints. | Greedy post-processing with grid ray checks, not a full parent-relaxing Theta* search. |
| NetworkX — PARTIAL | `services/graph_engine.py::build_electrical_graph` | Components → local `nx.DiGraph`; separately built typed graph returned. | No shortest path, cycle/connectivity analysis, graph traversal-based netlist or protection analysis. Neutral/PE additions appear only in the typed lists. |
| Shapely — IMPLEMENTED | `services/validation_engine.py::validate_pdm`; router `_route_is_clear` | Component rectangles and route segments → intersection areas/distances/violations. | Real 2D geometry operations. Does not represent full 3D solids or apply component rotations in the backend validator. |
| Thermal model — PARTIAL | `calculation_engine.py::calculate_db_parameters`; `validation_engine.py::validate_pdm`; CP `_solve_rows` | Incomer/feeders/catalog heat/dimensions → estimated W, W/L and height preference. | Fixed heat formula, separate catalog heat sum, hardcoded threshold. No thermal network, temperature rise or airflow model. |
| Selection scoring — PARTIAL | `component_selector.py::select_components`; `MemoryComponents.filter_candidates`; `MemoryEnclosures.find_best_fit` | Rating/poles/breaking/IP/geometry limits → first sorted part or minimum enclosure area. | Lexicographic sorting and fixed feeder IDs, not a learned/weighted multi-criteria component score. No costs or stock inputs. |
| Dependency graph — PARTIAL | `change_propagation.py::DEPENDENCY_DAG/identify_dirty_nodes`; `persistence/revisions.py::write_revision`; `ProjectService.propagate` | Field → listed stages; revision data → dependency records; old/new packages → diff. | Static direct lookup, not recursive DAG traversal or incremental scheduling. Full generation still runs. |
| Parameter dependency evaluation — IMPLEMENTED | `persistence/parameters.py::resolve_parameters/expression` | Parameter definitions/overrides/dependency names → validated values. | Repeatedly resolves ready derived values; rejects unresolved/cyclic definitions, fixed overrides, invalid units/types/ranges. AST allows arithmetic, not arbitrary stored Python. Imported box models currently use only basic dimension definitions. |

**NOT STARTED in the audited application:** NSGA-II/Pareto optimization, machine-learning selection, full Theta* search, electrical power-flow/short-circuit/protection-coordination solvers, CFD/temperature simulation, manufacturing CAD kernel execution and a generic executable electrical-template interpreter. Evidence boundaries: `CPSATPlacementOptimizer._solve_rows` uses one weighted objective; `NetlistEngine.generate_netlist` is Python-coded despite imported template metadata; `CADEngine` serializes primitives/scripts; `ProjectService` invokes no external CAD or thermal solver. No corresponding implementation was found by source search in `backend/app/` or frontend calls. Functions bearing related comments/types are not counted as implementations of these absent capabilities.

## 8. API endpoints

**IMPLEMENTED route inventory** from `backend/app/main.py::create_app` and `backend/app/api/routes_*.py`. Each row names the handler so its behavior can be checked. Engineering completeness remains as classified above. `{p}` means `{project_id}`, `{r}` revision ID, `{c}` component ID, `{a}` archetype ID.

| Method | Path | What it does | Handler → service/repository called |
|---|---|---|---|
| GET | `/health` | Process liveness; advertises DB/CEM/PDM, does not check DB. | `main.health` |
| GET | `/ready` | 200 only if DB schema revision is `0002_app`; otherwise 503. Does not check imported catalog completeness. | `main.ready` → `Database.ready` |
| GET | `/api/projects` | Paginated project list (default 50, maximum 100). | `routes_projects.list_projects` → `ProjectRepository.list` |
| POST | `/api/projects` | Creates project/validated answers, HTTP 201. | `create_project` → `ProjectService.create` |
| GET | `/api/projects/{p}` | Reads project; missing project is 404. | `get_project` → `ProjectRepository.get` |
| PATCH | `/api/projects/{p}` | Saves name/requirements/enclosure configuration with expected version. | `update_project` → `ProjectService.update` |
| GET | `/api/projects/{p}/answers` | Answer values, lock version and archetype version. | `get_answers` → `ProjectRepository.get` |
| PUT | `/api/projects/{p}/answers` | Validates/saves answer merge with expected version. | `save_answers` → `ProjectService.update` |
| GET | `/api/projects/{p}/requirements` | Structured current draft requirement rows. | `get_requirements` → project lookup + `project_requirements` SELECT |
| GET | `/api/projects/{p}/requirements/questions` | Pinned project's questionnaire. | `routes_requirements.get_questionnaire/template_for` → Project/Catalog repositories |
| POST | `/api/projects/{p}/requirements/validate` | Validates supplied answers; does not publish design. | `validate_requirements` → `RequirementEngine.validate_requirements` |
| GET | `/api/projects/{p}/revisions` | Lists saved history. | `routes_projects.revisions` → `ProjectRepository.revisions` |
| POST | `/api/projects/{p}/revisions` | Generates/publishes revision with requirements/config/version, HTTP 201. | `create_revision` → `ProjectService.generate` |
| GET | `/api/projects/{p}/revisions/{r}` | Reads verified historical package. | `get_revision` → `ProjectService.load_revision` |
| POST | `/api/projects/{p}/revisions/{r}/restore` | Publishes historical design as new current revision, HTTP 201. | `restore_revision` → `ProjectService.restore` |
| GET | `/api/projects/{p}/design` | Reads current saved package; no regeneration. | `routes_design.get_design` → `ProjectService.load_revision` |
| POST | `/api/projects/{p}/design/generate` | Legacy generation route; optional query expected_version. | `generate_design` → `ProjectService.generate` |
| POST | `/api/projects/{p}/design/propagate-change` | Full regeneration plus summary diff. | `propagate_change` → `ProjectService.propagate` |
| POST | `/api/projects/{p}/design/validate-placement` | Validates submitted PDM/project-ID equality only; no persistence. | `validate_placement` → `ValidationEngine.validate_pdm` without CEM |
| GET | `/api/projects/{p}/schematic` | Current saved design's schematic projection. | `routes_schematic.get_schematic` → `load_revision` |
| GET | `/api/projects/{p}/layout` | Current saved PDM. | `routes_layout.get_layout` → `load_revision` |
| GET | `/api/projects/{p}/validation` | Saved violations, relational results, thermal summary. | `routes_validation.get_validation_report` → `load_revision` + validation table SELECT |
| GET | `/api/projects/{p}/cad` | Primitive geometry JSON. | `routes_cad.get_cad_geometry` → `load_revision` |
| GET | `/api/projects/{p}/cad/freecad-script` | Script text/revision ID; refuses stale designs. | `get_freecad_script` → `load_revision`, `CADEngine.export_freecad_script` |
| GET | `/api/projects/{p}/artifacts` | Artifact metadata across project revisions. | `artifacts` → `ProjectService.list_artifacts` |
| POST | `/api/projects/{p}/cad-generation` | Queues GLB or FreeCAD-script artifact, HTTP 202. | `queue_generation` → `ProjectService.queue_artifact/_artifact_worker` |
| GET | `/api/projects/{p}/cad-generation/{job_id}` | Project-owned job/artifact state. | `generation_status` → project/revision ownership SELECT + `asset_dto` |
| GET | `/api/components` | Search/filter/sort/paginate published catalog. | `routes_catalog.components` → `CatalogRepository.search` |
| GET | `/api/catalog/filters` | Categories and manufacturer choices. | `catalog_filters` → SQL SELECT |
| GET | `/api/enclosures` | Imported enclosure definitions/CAD parameters. | `enclosures` → `CatalogRepository.enclosures` |
| GET | `/api/components/{c}` | Component details/CAD/clearances/documents. | `component` → `CatalogRepository.get_component` |
| GET | `/api/components/{c}/versions` | Component version records. | `versions` → `CatalogRepository.versions` |
| GET | `/api/components/{c}/cad-models` | CAD versions/parameters/assets. | `cad_models` → `CatalogRepository.get_component` |
| GET | `/api/components/{c}/accessories` | Recorded compatible catalog items. | `accessories` → `CatalogRepository.accessories` |
| GET | `/api/archetypes` | Published archetypes with supported flag. | `archetypes` → `CatalogRepository.archetypes` |
| GET | `/api/archetypes/{a}` | Template/questionnaire/modules. | `archetype` → `CatalogRepository.template` |
| GET | `/api/archetypes/{a}/questionnaire` | Same handler/template; optional version_id. | `archetype` → `CatalogRepository.template` |
| GET | `/api/archetypes/{a}/electrical-templates` | Stored template metadata, not an executing engine. | `electrical_templates` → `CatalogRepository.template/electrical_templates` |
| GET | `/api/rules` | Published rule records/parameters. | `rules` → `CatalogRepository.rules` |
| GET | `/api/assets/{asset_id}` | Catalog asset metadata/availability. | `routes_assets.asset_metadata` → `asset_row`, `CatalogRepository.asset_dto` |
| GET | `/api/assets/{asset_id}/content` | Verified catalog file download. | `asset_content/content` → `AssetStore.verified_path` |
| GET | `/api/artifacts/{artifact_id}` | Generated artifact metadata/availability. | `artifact_metadata` → `asset_row`, `asset_dto` |
| GET | `/api/artifacts/{artifact_id}/content` | Verified generated file download. | `artifact_content/content` → `AssetStore.verified_path` |

**IMPLEMENTED framework routes:** FastAPI also supplies `/openapi.json`, `/docs`, `/docs/oauth2-redirect` and `/redoc` through `FastAPI(...)` in `create_app`. These are documentation routes, not design stages. **NOT STARTED:** no authentication/authorization dependency is installed on these application routes (`api/dependencies.py::get_database/get_session/get_service`, `main.create_app`). CORS is an origin policy, not user authorization. The manual-placement endpoint does not look up project existence in storage.

## 9. Frontend audit

| Feature / status | Actual implementation and evidence |
|---|---|
| Page structure — IMPLEMENTED | One `ProjectPage`, seven conditional tabs: requirements, schematic, layout2d, threeD, validation, bom, catalog (`frontend/src/pages/ProjectPage.tsx::ProjectPage`, `components/common/Header.tsx::Header`). There is no frontend URL-router page hierarchy. |
| Readiness — IMPLEMENTED | `App` → `waitForBackend`: `/ready` polling up to 30 seconds, per-attempt abort, cleanup and Retry UI (`src/App.tsx`, `src/api/backend.ts`). |
| Projects/history — IMPLEMENTED | `ProjectPersistenceBar` plus `useProjectStore.openProject/saveCurrentProject/restoreSavedRevision` provide saved/open/close/discard/history controls and optimistic versions. Unsaved answers/configuration block certain navigation/restores. Unsupported archetypes are disabled in selectors. |
| Questionnaire — IMPLEMENTED | `Questionnaire` fetches pinned questions, applies defaults/dependencies and renders typed inputs; `validateCurrentRequirements`, `runDesignPipeline` call API. `EnclosureConfigurator` fetches catalog dimension schemas and keeps project overrides separate. |
| Store — IMPLEMENTED | `useProjectStore` in `src/stores/projectStore.ts` separates saved/local requirements/configuration, current project/version/revision, stale flag, artifacts/jobs, CEM/PDM/schematic/CAD and transient selection/editor undo/redo/visibility. It uses Zustand `create`, not localStorage-backed authoritative persistence. |
| API — IMPLEMENTED | `src/api/client.ts::request` centralizes timeout/cancel/errors; public config is `VITE_API_BASE`, default `http://127.0.0.1:8731/api` (`config.ts`). New frontend saves/generation use expected_version. `listProjects` fetches at most 100 and has no UI continuation for further project pages. |
| Schematic — PARTIAL | `SchematicCanvas`, `SymbolNode`, `WireEdge`, `JunctionNode`, `buildSchematicGraph`, `validateSchematicGraph` provide React Flow editing, terminal handles, fan-out, filtering and draft checks. Symbol nodes are labeled boxes, not a complete electrical symbol library; wires render Bezier curves, not the backend orthogonal SVG path. Edits do not update CEM or persist. |
| 2D — PARTIAL | `Layout2DViewer` provides SVG components/routes, drag/numeric/rotation/grid/alignment controls. `useProjectStore.validateCurrentPlacement` copies local transforms to a PDM, posts it for advisory checking and updates frontend PDM only. No publication/reroute is called. |
| 3D — PARTIAL | `Panel3DViewer` constructs enclosure/backplate/rails, maps PDM components through `ComponentMesh`, maps route waypoints to Drei `Line`, supports camera fit, selection, visibility, explode, gizmos and numeric/history controls. PDM remains the assembly source. Optional saved full-assembly GLB view bypasses those per-part scene controls. |
| Mesh loading — IMPLEMENTED | `AssetObject/LoadedAsset` use `useGLTF` and `Clone` with Suspense and error fallback. Parts use preview URL when metadata status is READY, otherwise bounds boxes. GLB metre coordinates use ×10; PDM mm transforms use ×0.01. No STEP loader appears in this view. |
| Catalog — IMPLEMENTED | `CatalogBrowser` uses 250 ms debounced/cancelled backend search, category/manufacturer/sort, page size 12, detail/accessory reads and Canvas preview. No model-upload/editor/publish interface exists. |
| BOM — PARTIAL | `BOMTable` renders `cem.components`, locates PDM parts by CEM ID and offers Highlight plus FreeCAD-script download. It is not a complete procurement BOM or CSV/XLSX export. Download errors are logged with `console.error` in `handleDownloadScript`, without a dedicated visible error state there. |
| Validation — PARTIAL | `ValidationPanel` shows PDM violations and whole-volume heat summary, and can select an object in 2D. Its green wording concerns implemented checks only; no empty compliance collection is converted into proof of engineering compliance. The display also hardcodes 0.45 W/L. |

### Cross-highlighting — PARTIAL

`useProjectStore.selectObject/hoverObject` store shared IDs. `BOMTable` selects `comp.id`; `Layout2DViewer` and `Panel3DViewer` match either `cem_component_id` or PDM `id`. `ComponentMesh` writes the CEM ID on click/hover. `ValidationPanel.handleViolationClick` selects a violation object and switches to 2D.

`SchematicCanvas` writes node IDs to `selectObject` on node/selection events, but reads only `selectObject` from the store. Its visual selection is React Flow's local `node.selected`; it does not subscribe to global `selectedObjectId` or `hoveredObjectId`. Therefore schematic → other views works for component IDs, while BOM/layout → schematic selection is incomplete. Junction IDs such as `JUNCTION:<net>` are synthetic and do not map to a physical component. Route/net-level highlighting is not a complete shared selection contract (`SchematicViewer.tsx::SchematicCanvas`, `schematicGraph.ts::buildSchematicGraph`).

## 10. Data and configuration

### Source/import data

| File / status | Structure | Actual boundary and limitations |
|---|---|---|
| `backend/app/data/components.json` — STUB/MOCK | Array of 14 prototype electrical parts: code/name/category/rating/poles/dimensions/mounting/heat/CAD hint/clearances/terminal local coordinates. | Direct default `repositories/component_repository.py::ComponentRepository` reads JSON. HTTP runtime uses imported published rows through `persistence/repositories.py::CatalogRepository.engine_catalog` and `MemoryComponents`. `.step` strings are hints, not files. |
| `backend/app/data/enclosures.json` — STUB/MOCK | Four enclosure records with outer/plate dimensions, offsets, declared IP/heat capacity and fixed zone rectangles. | `import_legacy` publishes component/CAD records; runtime `CatalogRepository.enclosures` and `MemoryEnclosures` isolate them from the solver. |
| `backend/app/data/panel_templates.json` — PARTIAL | Array with DB archetype, seven module definitions and eight questions/defaults/options/dependencies/ranges. | `RequirementEngine` supports injected templates; runtime rebuilds them from questionnaire/archetype DB tables (`CatalogRepository.template`). No generic panel-generation engine follows arbitrary modules. |
| `backend/app/data/rules.json` — PARTIAL | Four illustrative rules: incomer clearances, voltage drop, busbar multiplier and thermal density. | Old `RuleRepository` only loads/filters JSON and is not used by orchestrator. Imported rule metadata is pinned/exposed, but most matching engineering constants still live in service code. LayoutConfig is reconstructed from the special imported DB_LAYOUT_CONFIG rule (`ProjectService._inputs`). |
| `backend/app/data/sample_projects.json` — PARTIAL | Two projects: `PROJ_DB_DEMO_001`, `PROJ_002`, each with requirements; no generated revision snapshots. | `import_legacy` imports missing projects, preserving existing ones. Old direct `ProjectRepository.save` can write JSON, but the API uses SQL repository/memory adapters and `persist_requirements=False`. |
| `docs/database/002_sample_data.sql` — STUB/MOCK | Illustrative published reference catalog/archetype/project with seed identifiers/metadata. | Separate from executable DB import. Tests intentionally load both SQL sample and JSON import (`tests/conftest.py::postgres_database`); DB_BASIC reference data is not another implemented panel engine. |

### Persistence, storage and configuration

- **IMPLEMENTED:** baseline has 78 application tables (`backend/migrations/versions/0001_baseline.sql`); Alembic adds its version table. `0002_app.py::upgrade` adds project archetype/current revision/configuration/lock fields, draft uniqueness and conductor endpoint FKs. Table count alone is not feature completion.
- **IMPLEMENTED:** `manage.initialize` uses structural `schema_tools.verify_baseline` before stamping an existing unversioned schema. Empty databases migrate normally. It does not call `metadata.create_all` or recreate a project DB. Downgrades deliberately refuse destructive removal (`0001_baseline.py::downgrade`, `0002_app.py::downgrade`).
- **IMPLEMENTED:** `import_legacy.py::import_legacy/stable` uses stable UUID5 identities, explicit transactions and prototype provenance. Repeating unchanged imports does not replace existing projects or mutate imported component version 1. A changed component source hash is rejected rather than silently updated. Other imported definitions use insert-if-absent behavior, not a general version-publication workflow.
- **IMPLEMENTED:** `Settings.load/environment` prefer DATABASE_URL, otherwise PANEL_DATABASE_URL; process environment is used, plus Windows user registry fallback. PANEL_DATABASE_URL targeting maintenance `postgres` is redirected to `electrical_panel_design`. Explicit DATABASE_URL must name an application database. No automatic dotenv loader exists (`persistence/config.py`).
- **IMPLEMENTED:** `Database` uses Psycopg/SQLAlchemy pool pre-ping, parameter hiding and short connections. Defaults: pool 5, overflow 5, connect timeout 5 seconds. `/ready` only checks required migration revision (`persistence/database.py::Database.ready`).
- **IMPLEMENTED:** `AssetStore.put/verified_path` stores relative `sha256/aa/bb/<hash>.<extension>` files under `{PANEL_DATA_DIR}/assets`, default user home `.panelstudio/assets`; atomic file replacement, hash/size checks and root containment. DB rows hold file references. `routes_assets.content` supports configured LOCAL storage only; no S3 adapter is implemented.
- **PARTIAL:** file writes and DB commit cannot be one transaction. Orphan files can remain; `manage audit-assets` reports without automatic deletion. A database backup alone does not include those asset bytes (`ProjectService.generate_files`, `AssetStore`, `manage.main`).
- **PARTIAL:** release sidecar uses Tauri application data directory, while normal web startup defaults to user `.panelstudio`. Sharing one DB with different asset roots can produce missing-file reports (`frontend/src-tauri/src/lib.rs::run`, `backend/desktop_main.py`, `Settings.asset_root`).
- **PARTIAL:** published snapshot policy is application-level. `load_revision` verifies canonical SHA-256; schema mappings contain few view-only ORM relationships and extensive table mappings. No general permission model or SQL immutability enforcement exists (`persistence/models.py`, `revisions.py::write_revision`, `main.create_app`).
- **PARTIAL:** `ThreadPoolExecutor(max_workers=1)` performs local artifact jobs. Startup marks all PENDING artifacts interrupted/FAILED; multiple backend processes could interfere. No durable worker claiming/distributed queue exists (`main.create_app/lifespan`, `ProjectService.queue_artifact/_artifact_worker`).

## 11. How to run and verification

### Prerequisites and setup — IMPLEMENTED workflow

Run from the repository root. PostgreSQL must already be running, the application database must already exist, and DATABASE_URL or PANEL_DATABASE_URL must be privately set in the backend terminal. No URI is printed or stored by these commands. The migration CLI does not create the database itself (`Settings.load`, `manage.initialize`). Browser development does not require FreeCAD or a Tauri installer.

Windows PowerShell:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m app.persistence.manage initialize
.\venv\Scripts\python.exe -m app.persistence.manage import-legacy
.\venv\Scripts\python.exe -m app.persistence.manage status
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8731 --reload
```

Linux Bash, using an available compatible Python interpreter (this audit uses Python 3.12 on Windows):

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m app.persistence.manage initialize
python -m app.persistence.manage import-legacy
python -m app.persistence.manage status
python -m uvicorn app.main:app --host 127.0.0.1 --port 8731 --reload
```

Second terminal, both platforms:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --strictPort
```

Open `http://127.0.0.1:3000`; readiness is `http://127.0.0.1:8731/ready`; API docs are `http://127.0.0.1:8731/docs`. Ports/base URL originate in `frontend/vite.config.ts`, `frontend/src/api/config.ts`, `.env.development` and CORS origins in `backend/app/main.py::create_app`.

### Test/build commands — IMPLEMENTED

```powershell
# PowerShell: from backend, unit/default checks
.\venv\Scripts\python.exe -m pytest -q

# Include PostgreSQL integration tests; configured role needs CREATE DATABASE.
$env:PANEL_RUN_POSTGRES_TESTS = '1'
.\venv\Scripts\python.exe -m pytest -q
Remove-Item Env:PANEL_RUN_POSTGRES_TESTS

# From frontend
npm test
npm run build
```

```bash
# Linux: from backend with venv active
python -m pytest -q
PANEL_RUN_POSTGRES_TESTS=1 python -m pytest -q

# From frontend
npm test
npm run build
```

`backend/tests/conftest.py::postgres_database` creates a uniquely named `panel_integration_test_<uuid>` database, applies migrations, loads SQL reference data and imports JSON fixtures, then removes only that generated database. Asset files go to temporary storage. It does not drop/truncate the configured development database. Without the opt-in variable, DB-fixture tests skip; pure tests in `test_postgres.py` still run. Frontend tests use jsdom and mocks; they are not live WebGL/browser integration tests (`frontend/package.json`, component test files).

### Audit execution results

Tests were launched from the checkout above. No source repairs were made in response to failures. Linux execution, native FreeCAD execution, Tauri packaging and interactive browser appearance remain **UNVERIFIED** for this audit.

| Check / status | Exact audit execution | Result and limits |
|---|---|---|
| Backend suite — IMPLEMENTED, PASS | From `backend`: `$env:PANEL_RUN_POSTGRES_TESTS='1'; .\venv\Scripts\python.exe -m pytest -q`, with localhost/filesystem access outside the restricted sandbox. | **27 passed**, 1 warning, 195.91 seconds. Includes unit tests and real isolated PostgreSQL migrations/import/API/projection/asset/concurrency/rollback checks. Warning: Starlette TestClient uses deprecated `anyio.abc.BlockingPortal` alias. |
| Restricted default run — PARTIAL, FAILED/INTERRUPTED | From `backend`: `.\venv\Scripts\python.exe -m pytest -q` in the restricted sandbox. | Printed a failure and DB-fixture skips; did not complete and was interrupted. Targeted rerun below reproduced the file-permission failure. This is not reported as a complete passing run. |
| Restricted targeted failure — PARTIAL | `.\venv\Scripts\python.exe -m pytest tests/test_postgres.py::test_asset_integrity_and_traversal -q --tb=short` | **1 failed in 0.84 seconds**: `AssetStore.put` → `os.replace` raised `PermissionError: [WinError 5] Access is denied` in the sandbox temporary asset directory. Same test passes in the unrestricted full suite. Evidence supports an environment-dependent filesystem restriction, not a source fix. Reason the earlier default run stopped progressing is **UNVERIFIED**. |
| Frontend tests — IMPLEMENTED, PASS | From `frontend`: `D:\Appus\javascript\npm.cmd test` | **11 files / 23 tests passed**, 236.63 seconds. Includes API errors, store persistence/editor history, questionnaire/catalog, schematic graph, 2D/3D component behavior and geometry/camera helpers. jsdom/mocked R3F is not real GPU/browser verification. |
| Frontend production build — IMPLEMENTED, PASS with warning | From `frontend`: `D:\Appus\javascript\npm.cmd run build` | `tsc && vite build` succeeded; Vite 5.4.21 transformed 2,256 modules. JS chunk 1,510.37 kB, gzip 438.62 kB; Vite warned about chunks over 500 kB. CSS 42.17 kB. This is a bundle-size warning, not a failed build. |
| Requested example and changes — PARTIAL, mixed results | Ephemeral stdin harness → existing `postgres_database` fixture → `TestClient(create_app(db))` → real create/revision/propagation routes. | Baseline and 16-feeder generation passed; exact 12→16 propagation passed; 400 A, 630 A, 25 feeders and single-phase examples failed with structured 422 responses. Details in section 12. |
| Native CAD/desktop/Linux/visual acceptance — PARTIAL, UNVERIFIED | Inspected `CADEngine`, `desktop_main.py`, `panel-backend.spec`, Tauri configuration/lifecycle and frontend code; did not execute those platforms/tools. | No claim of generated STEP validity, Linux compatibility, installer correctness or interactive visual QA. |

**IMPLEMENTED test evidence:** `tests/test_postgres.py::test_workflow_reopens_snapshots_projections_and_artifacts` checks saved CEM/PDM identity, terminal/conductor FKs, real GLB bytes/hash, and attempts the installed Three GLTFLoader when Node is available. `test_atomic_revision_rollback`, `test_project_dimensions_are_private_and_conflicting_writes_rejected`, `test_background_cad_status_and_missing_assets`, `test_legacy_import_is_idempotent` and `test_orm_metadata_matches_migrated_schema` cover useful persistence boundaries. The optional GLTFLoader subprocess branch's execution was not separately logged in this audit, so that sub-branch is **UNVERIFIED** rather than inferred from suite success.

**PARTIAL test coverage:** passing tests check the current contracts, not full electrical correctness. The three-phase terminal/net issue is not rejected by `test_pipeline_uses_consistent_cem_pdm_schematic_routes_bom_and_cad_ids` or `validate_netlist`. The local virtual environment includes system site packages (`backend/venv/pyvenv.cfg`); a fully clean dependency installation was not performed. There is no configured lint command in `frontend/package.json`; no CI workflow directory was found in this checkout. Fresh-machine installation is **UNVERIFIED**.

## 12. Gaps and demo scenarios

### Major gaps, with code evidence

| Status | Gap and practical effect | Evidence |
|---|---|---|
| PARTIAL | Three-phase branches are not electrically separated: all three outputs use one terminal `LEFT`, and several phases/connections share one branch net. Existence checks can pass while the electrical model is wrong. Frontend fan-out can visually join those endpoints. | `backend/app/services/netlist_engine.py::generate_netlist/validate_netlist`; `frontend/src/components/schematic/schematicGraph.ts::buildSchematicGraph` |
| PARTIAL | Neutral/PE are main-trunk connections only; no per-load neutral/PE schedule, SPD earth connection or upstream supply phase terminations are generated. Graph's root→incomer relation does not become equivalent supply-phase connections in the netlist. | `GraphEngine.build_electrical_graph`, `NetlistEngine.generate_netlist` |
| PARTIAL | Fixed feeder mix ignores load schedule, calculated feeder average, cable coordination, diversity per circuit and phase balancing. Terminals are selected by fixed code, not by each circuit's conductor/current needs. | `ComponentSelector.select_components`, `CalculationEngine.calculate_db_parameters` |
| PARTIAL | Questionnaire accepts 4–48 feeders and lists 630 A, but engine limits to 24 ways and lacks some adequate component ratings. Input validation success does not imply feasible generation. | `backend/app/data/panel_templates.json`; `RequirementEngine.validate_requirements`; `ComponentSelector.select_components` |
| PARTIAL | Spare percentage changes design-current/voltage-drop calculation, not reserved rail space, spare outgoing ways, enclosure capacity or an added spare BOM. Frequency is stored/validated but not used by calculation formulas. `power_factor=0.85` is assigned but not used in the returned kVA calculation. | `CalculationEngine.calculate_db_parameters`, `ComponentSelector.select_components`, `DesignOrchestrator.generate_design` |
| PARTIAL | Short-circuit withstand/selectivity, cable ampacity/derating, protective bonding verification and standards compliance are absent. A minimum 25 kA selector filter is hardcoded without a fault-current input. | `ComponentSelector.select_components`, `CalculationEngine.calculate_db_parameters`, empty CEM `constraints/compliance` in `CanonicalEngineeringModel` |
| STUB/MOCK | Catalog dimensions, terminal coordinates, loss values, IP/heat capacities and source CAD names are prototype data, not verified manufacturer evidence. Managed imported previews are real GLB files containing illustrative boxes. | `backend/app/data/*.json`, `persistence/import_legacy.py::import_legacy`, `assets.py::primitive_glb` |
| PARTIAL | Many imported published rule/template definitions are metadata, not executable policy. Changing those records does not necessarily change hardcoded formulas/topology; only the special LayoutConfig rule drives the placement settings. | `ProjectService._inputs`, `CalculationEngine.calculate_db_parameters`, `ValidationEngine.validate_pdm`, `NetlistEngine.generate_netlist` |
| PARTIAL | No hard zone containment or recalculation of zone rectangles after enclosure resizing. Standalone ZoningEngine is unused. | `ZoningEngine`, `ProjectService.configure_enclosures`, `CPSATPlacementOptimizer._solve_rows`, `LayoutConfig` |
| PARTIAL | Enclosure heuristic does not co-optimize actual placement or retry a larger box on placement/routing failure. Thin depth can fail routes, but there is no complete component-solid depth containment check. | `EnclosureEngine.select_enclosure`, `DesignOrchestrator.generate_design`, `ValidationEngine.validate_pdm` |
| PARTIAL | Placement excludes rotation choice, terminal-distance objective and physical duct generation. Rail row search starts from a category/width heuristic, not an exhaustive proof of globally minimum rail count. | `CPSATPlacementOptimizer.solve/_solve_rows/_mk` |
| PARTIAL | Router has 2D occupancy and terminal escape stubs, with interpolated z. It does not prevent wire-wire overlap, enforce class segregation, physical duct capacity or minimum bend radius; independent connections can reuse the same path. | `JPSThetaStarRouter.route_nets/_grid_path_to_3d/_build_duct_grid/_route_is_clear` |
| PARTIAL | Manual-placement API uses caller-supplied PDM only and no CEM argument, so it cannot establish full saved-netlist completeness. Backend physical geometry ignores rotation and component depth. A zero-distance touching pair avoids the positive-distance clearance warning. | `routes_design.validate_placement`, `ValidationEngine.validate_pdm` |
| PARTIAL | Thermal model is only W/L and positional preference, with different CALC_007 and catalog-sum heat values. No ambient/temperature rise/airflow model. | `CalculationEngine`, `ValidationEngine`, `CPSATPlacementOptimizer._solve_rows` |
| PARTIAL | Parametric CAD supports basic dimension arithmetic and box output. FreeCAD script builds solid enclosure/rail/component boxes and line-compound wires, then STEP export text; it does not create a detailed shell, holes, door, native feature tree or run FreeCAD. | `resolve_parameters`, `CADEngine.generate_parametric_geometry/export_freecad_script`, `ProjectService.generate_files/_artifact_worker` |
| PARTIAL | BOM omits enclosure, mounting structures, wires/accessories and costs. There are no dedicated BOM tables in the audited baseline/mappings; BOM is reconstructed from CEM. Many other schema entities have no active pipeline writer; schema breadth is not completed workflow breadth. | `DesignOrchestrator.generate_design` BOM comprehension; `ProjectService.load_revision`; `write_revision`; table inventory in `backend/migrations/versions/0001_baseline.sql` and `persistence/models.py` |
| PARTIAL | Full regeneration is used for changes; static affected-stage list is not an executable dependency DAG. Some lists omit stages actually regenerated (for example incomer change's list does not enumerate CAD). | `ChangePropagationEngine.DEPENDENCY_DAG/identify_dirty_nodes`, `ProjectService.propagate` |
| PARTIAL | Editor transforms/schematic wiring do not publish a consistent revision. 2D Apply & Validate leaves routes/artifacts stale; 3D gizmos are presentation drafts; cross-selection does not flow back into React Flow visual selection. | `useProjectStore.validateCurrentPlacement/updateEditorTransform`, `SchematicCanvas`, `Panel3DViewer`, `Layout2DViewer` |
| PARTIAL | No generic catalog/model authoring UI/API or other executable panel archetype; engine catalog excludes published parts lacking the legacy-import marker. Existing accessory lookup does not mean accessories are automatically selected. | `CatalogRepository.engine_catalog/accessories/archetypes`, `ProjectService.validate`, `routes_catalog.py`, `CatalogBrowser` |
| PARTIAL | Snapshot reads preserve CEM/PDM, but schematic, CAD primitives and BOM are reconstructed using installed code; those derived views may change after code upgrades. Revision CEM string version remains default, distinct from DB history. | `ProjectService.load_revision`, `CanonicalEngineeringModel.revision`, `write_revision` |
| PARTIAL | Local asset/DB roots, backup/restore and orphan handling require operational care; local export worker is not safe as a shared durable multi-worker service. Readiness can succeed before catalog import. | `AssetStore`, `ProjectService.generate_files`, `Database.ready`, `main.create_app/lifespan` |
| NOT STARTED | Authentication, user/project authorization and shared multi-user deployment controls. No PostgreSQL server is bundled with desktop app. | `main.create_app`, `api/dependencies.py`, `frontend/src-tauri/src/lib.rs::run`, `backend/desktop_main.py` |
| NOT STARTED | NSGA-II, full Theta* search, thermal simulation, a generic executable template interpreter and native CAD-kernel generation. | Actual implementations are `_solve_rows`, `_theta_star_smooth`, `validate_pdm`, `generate_netlist`, `CADEngine`; no alternatives were found in the audited source. |

### Demo scenario verification

A successful prototype generation means the implemented code accepted/generated/published the package. It does not resolve the electrical-model gaps above. The audit does not equate green physical validation or `FINAL_VALIDATED` with electrical correctness.

All cases used 415 V, 50 Hz, IP54, 20% spare and neutral required, with the specific changed field noted. Fixtures include the SQL reference seed and current application import. Generation/propagation came through `routes_projects.create_revision` / `routes_design.propagate_change` → `ProjectService.generate/propagate`, not a mocked orchestrator.

| Scenario | Status | Observed result | Actual reason / code |
|---|---|---|---|
| 250 A, 12 feeders | PARTIAL — working prototype | HTTP 201; 29 parts, 20 nets, 44 connections/routes, 3 rails; 800×1000×300 enclosure; 117.5 W; 0.490 W/L; THERMAL WARNING; GLB/PY READY. | `ProjectService.generate`, `DesignOrchestrator.generate_design`, `ValidationEngine.validate_pdm`; warnings permit publication. |
| Change 12 → 16 feeders through revision generation | PARTIAL — works | HTTP 201; 37 parts, 24 nets, 56 connections/routes, 3 rails; same enclosure; heat 135.4 W, density 0.564 W/L, THERMAL WARNING. | `ComponentSelector.select_components`, CP solver, router and validator all completed. |
| Exact change 12 → 16 through propagation endpoint | PARTIAL — works | HTTP 200, revision 2; diff says 12→16 MCBs, 44→56 routes, 117.5→135.4 W; incomer and enclosure unchanged. | Separate isolated run: `ProjectService.propagate` → full `generate` → `ChangePropagationEngine.compute_diff`. |
| Change 250 → 400 A with 12 feeders | PARTIAL — fails | HTTP 422 `NO_FEASIBLE_COMPONENT`, category BUSBAR, minimum current 500 A. | `calculate_db_parameters`: 400×1.25=500 A; `select_components` cannot find adequate busbar. Imported JSON has only 250/400 A busbars (`components.json`). |
| Change 250 → 400 A with 16 feeders | PARTIAL — fails | Same HTTP 422 / minimum 500 A busbar. Exact propagation attempt also returned 422. | Failure occurs in selection, before new placement/routing/publication (`ProjectService.generate`). |
| Saved state after failed 400 A propagation | IMPLEMENTED — preserved | Current revision unchanged and saved incomer requirement remained 250 A. | Audited with GET project after failed `ProjectService.propagate`; write transaction is reached only after successful generation. |
| 25 feeders | PARTIAL — fails despite questionnaire range | HTTP 422 `NO_FEASIBLE_COMPONENT`, requested 25, available ways 24. | Explicit `num_feeders > 24` guard in `ComponentSelector.select_components`; question max is 48. |
| 630 A | PARTIAL — fails despite listed option | HTTP 422 `NO_FEASIBLE_COMPONENT`, no suitable MCCB for 630 A/3 poles/25 kA. | `ComponentSelector.select_components` and current imported MCCB ratings. |
| Single phase, 250 A | PARTIAL — fails despite listed option | HTTP 422 `NO_FEASIBLE_COMPONENT`, required 1-pole MCCB absent. | `ComponentSelector.select_components` requests `poles=1`; imported incomers are 3-pole. |
| Propagate 16 → 16 (unchanged input) | PARTIAL — no-op still regenerates | HTTP 200 with all summary `changed=false`; a generation request is still made. | `ProjectService.propagate` does not short-circuit unchanged values. This separate observed no-op was not used as evidence of a real 12→16 change. |
| Native STEP/manufacturing output, larger/custom layouts, other panel types | PARTIAL / NOT STARTED — UNVERIFIED beyond named code | Not executed. Other archetypes have no implemented engineering pipeline. | `CADEngine.export_freecad_script`, `ProjectService.validate`, `resolve_parameters`; no native CAD invocation. |

**PARTIAL display wording:** the diff labels route count as “Wire Nets” even though it counts `pdm.routes`, and the modal title says “Incremental Change Propagation Report” although execution is full regeneration (`ChangePropagationEngine.compute_diff`, `frontend/src/components/common/ChangePropagationModal.tsx::ChangePropagationModal`).

**PARTIAL overall outcome:** the current 250 A / 12-to-16-feeder DB software demonstration runs and persists real artifacts, with thermal warnings. The stock 400 A demonstration does not run with the current busbar catalog. Electrical net semantics, load-based selection, rotation/depth checks, meaningful thermal/CAD models, complete BOM and publishable manual edits remain the largest implementation gaps, as evidenced by the specific functions above.
