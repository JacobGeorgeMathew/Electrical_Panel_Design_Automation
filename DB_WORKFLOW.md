# Distribution Board workflow

This prototype implements a single DB design flow in the existing FastAPI modular monolith. Runtime catalogs, answers, requirements and project revisions are now PostgreSQL-backed through SQLAlchemy; original JSON files remain explicit import/test fixtures. See [PostgreSQL operations](docs/database/OPERATIONS.md) for migration, import, configuration and packaging instructions.

## Stage map and contracts

| Stage | Existing module | Contract and behavior |
|---|---|---|
| Project and requirements | `app/api/routes_projects.py`, `routes_requirements.py`, `services/requirement_engine.py`, `persistence/` | DB project state, versioned questionnaire sessions and structured requirements are saved in PostgreSQL. Type, option, integer, required, range and unknown-field errors are returned before generation. |
| Calculations and selection | `calculation_engine.py`, `component_selector.py`, `enclosure_engine.py` | Estimates and selected parts are typed CEM data. Selection must meet requested current, poles, breaking capacity, computed busbar current, DB way capacity, and IP enclosure requirements. Missing feasible catalog entries return structured design errors. |
| Electrical graph and netlist | `graph_engine.py`, `netlist_engine.py`, `models/electrical_graph.py`, `models/cem.py` | The CEM carries graph nodes/edges, net IDs, and individual connection IDs. Component and terminal references are checked against the catalog. IDs are deterministic for a given project input. |
| Schematic | `schematic_engine.py` | Consumes the CEM and renders wires from the same connection and terminal IDs as the netlist. The schematic is a diagram layout, not a physical drawing. |
| Placement and routes | `cp_sat_placement.py`, `duct_routing.py`, `jps_theta_star.py`, `panel_assembly.py`, `models/pdm.py` | CP-SAT reserves physical side/inter-row ducts and terminal strip end-stop space. The PDM carries cabinet accessories and actual troughs. Routing preserves exact terminal endpoints, finds local lead-ins, then constrains JPS/A* trunks to the connected physical duct network. Disconnected ducts, collisions and excess estimated fill stop generation. |
| Validation and outputs | `validation_engine.py`, `cad_engine.py` | Validation checks bounds, overlaps, clearances, route references and CEM/PDM identity. Browser primitives and the separate FreeCAD script are both built from the validated PDM. The response also includes a BOM keyed by CEM component ID. |
| Change propagation | `change_propagation.py`, `routes_design.py` | A change is validated and regenerated in memory first. Requirements are persisted only after success. The report names the changed field, before/after values, changed summaries, and downstream stages. |

## API and frontend

- `POST /api/projects` creates a DB project with a name and optional requirements.
- `POST /api/projects/{project_id}/requirements/validate` returns a `RequirementSet` with errors and warnings.
- `POST /api/projects/{project_id}/design/generate` returns `cem`, `pdm`, `schematic`, `cad`, `bom`, and validation violations. Invalid or infeasible input returns HTTP 422 with an `error.code`, message, details, and field errors.
- `POST /api/projects/{project_id}/design/propagate-change` returns the regenerated package and its before/after report.
- The frontend can create a DB project, validate and generate its inputs, display API errors, review requirement changes, inspect schematic/layout/3D routes, BOM placement traceability, and export the FreeCAD script.
- The schematic uses React Flow for symbol selection, dragging, zoom/pan, terminal-level handles, net-labeled edges, fan-out junctions, electrical-property inspection, and draft-level graph checks. Graph edits are in-memory presentation drafts; they do not modify the CEM netlist or downstream exports.
- The lightweight SVG 2D editor supports component dragging, numerical position/orientation, 90° rotation, grid snapping, simple alignment, selection, and clearance highlighting. **Apply & Validate** projects these transforms into the frontend PDM and submits that PDM to `POST /api/projects/{project_id}/design/validate-placement`, which runs the existing physical validator and returns its structured violations. This prototype endpoint validates the submitted PDM but does not persist it to project storage or regenerate routes/BOM/CAD; edited placements can therefore be reported with stale-route violations. Generate Design returns to the backend-generated PDM.
- The React Three Fiber editor continues to support component-tree selection, move/rotate gizmos, numerical transforms, visibility, snapping, undo/redo, and advisory geometry warnings. 3D transform changes remain local viewing drafts and do not update the PDM.

## Simplifications and limits

The calculations use fixed assumptions for diversity, conductor current density, equivalent length, and heat loss. Feeder breaker choices are demo defaults because detailed load schedules and fault-level inputs are not yet represented. Placement clearance and thermal checks are simplified geometric checks. Duct routing uses 2D footprints, explicit trough-depth lanes and estimated insulated-wire area; it does not enforce wire-class segregation, bend radii or full 3D wire packing. Catalog dimensions, fill limits, wire diameters and terminal points are generic assumptions. The React Flow graph and 3D transform edits remain drafts. A validated 2D placement updates only the frontend's in-memory PDM; it does not persist the project or regenerate routes, BOM, or CAD. FreeCAD export continues to use the backend-generated PDM. Draft collision checks use rotated 2D bounding boxes. Warnings and calculations are not evidence of IEC or other standards compliance; this prototype is not production engineering software and does not establish a safe or certified design.

The cabinet now has a hollow steel body, hinged door, gasket, handle, hinges, gland plate, slotted ducts with covers, top-hat DIN rails and detailed terminal/breaker geometry. The 3D viewer opens/closes the door and fits/removes covers. Hardware and duct/rail cut lengths appear in the BOM. See [assembly setup and implementation](docs/PANEL_ASSEMBLY.md). Existing installations can run `python -m app.persistence.manage import-panel-hardware` from `backend/`, restart, and generate a new revision; original saved revisions remain unchanged.

## Checks

From `backend/`, run `python -m pytest`. From `frontend/`, run `npm test` and `npm run build`. Tests use deterministic requirement and geometry fixtures; the frontend tests cover viewport fit, camera reframing, editor warnings, and transform history. `TEST_CASES_FOR_TEACHER.md` includes manual classroom demonstration steps. These checks do not replace manual browser inspection at multiple window sizes.

Alembic adopts the existing SQL schema only after structural verification. Successful generation publishes a CEM/PDM revision and matching relational projections atomically; GET views reopen that revision without regeneration. Project controls save/close/reopen and restore historical designs as new revisions. GLB previews and FreeCAD scripts are hashed and registered in managed storage. Other panel engines, verified manufacturer libraries, richer native CAD adapters and shared deployment infrastructure remain future work.
