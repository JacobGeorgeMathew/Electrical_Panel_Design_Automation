# Questionnaire choices, suggestions and fullscreen viewers

## Changes

1. Numeric questions with declared options now render typed dropdowns. Bounded feeder and spare-percentage questions receive explicit choices from the backend. Unsupported saved values remain visible as a prompt to choose a supported value; they are not silently replaced.
2. The backend resolves a read-only questionnaire view from published questions, component selection, terminal/netlist validation and the current duct conductor limit. The same resolved questions are used by validation, project saves and generation. Direct API requests cannot bypass the choices shown in the questionnaire.
3. Feeder-based incomer suggestions are calculated by a read-only API. A **Use suggestion** button applies a suggestion only when clicked. The user can subsequently select another supported rating. Planning estimates and calculation assumptions are shown separately from the saved answer.
4. The schematic has persistent **+**, **−**, zoom percentage and **Fit** controls inside the canvas, so they remain accessible in fullscreen. Wheel/pinch/double-click zoom are enabled. The zoom range is 2%–800%; fit can show wide feeder diagrams below the old 20% minimum. Canvas pan no longer competes with left-drag box selection.
5. Schematic, 2D layout and 3D panel canvases have fullscreen controls, including launchers in the view toolbars. Native browser fullscreen is used when available, with an in-app maximized fallback. Escape and **Exit fullscreen** restore the prior view. The existing canvas is retained rather than recreated. Small-screen property/component panes are drawers, giving the design the available viewport by default.

## Current supported choices

`backend/app/services/questionnaire_choices.py::resolve_choices` produces these choices from the present DB catalog:

| Question | Offered choices |
|---|---|
| Supply voltage | Published values: 230, 400, 415, 690 V |
| Phases | 3; no compatible single-phase incomer/terminal netlist is available |
| Frequency | 50, 60 Hz |
| Incomer rating | 100, 250 A |
| Feeders | Integers 4–16 |
| IP rating | Published values: IP31, IP42, IP54, IP65 |
| Spare capacity | Integers 0–50% |
| Neutral bar | Yes/No, subject to the published dependency |

300 A is outside the published rating choices. The catalog has no 160 A or 630 A incomer. Its 400 A incomer requires a busbar of at least 500 A under the existing sizing calculation, but its largest busbar is 400 A. These ratings are therefore not offered as currently supported designs. No new electrical component is invented to make an option appear valid. The 16-feeder limit reflects the existing router's 56-conductor capacity and current automatic feeder mix; bar-way capacity is checked too.

Valid questionnaire choices do not guarantee every combination fits a fixed enclosure. Placement, duct capacity and thermal validation still run during design generation. Existing saved answers are preserved until the user changes them; historical revisions remain intact. Single-phase configurations previously accepted as answers could not form a complete supported design; current application validation rejects those unsupported choices.

## Suggestions and authority

`questionnaire_choices.py::suggest_requirements` uses the actual existing automatic 16 A / 32 A / 40 A feeder pattern and phase allocation. It sums per-phase breaker ratings, applies the existing prototype diversity factor of 0.75 and the selected spare percentage, then suggests the next supported incomer rating above the maximum phase estimate.

| Feeders | Spare | Estimated maximum phase demand | Suggested incomer |
|---|---:|---:|---:|
| 4 | 20% | 64.8 A | 100 A |
| 12 | 20% | 165.6 A | 250 A |
| 16 | 20% | 230.4 A | 250 A |

This is a planning estimate based on the software's feeder mix, not measured demand or a compliance calculation. The UI warns when the user's selected incomer is below the estimate. If demand exceeds every supported incomer, the API reports that fact and does not fabricate a suitable rating. Supply voltage and ingress protection are not inferred from feeder count. Spare feeder spaces are calculated with `ceil(feeders × spare% / 100)` for planning; extra physical bays are not automatically generated.

Read-only endpoints:

```text
POST /api/projects/{project_id}/requirements/suggestions
POST /api/archetypes/{archetype_id}/suggestions
```

Example body:

```json
{"num_feeders": 4, "phases": 3, "spare_capacity_pct": 20}
```

The response contains `suggestions`, `estimates`, `assumptions` and `message`. Requests do not update project requirements, revisions or lock versions. Frontend requests are debounced and aborted when inputs change; stale responses cannot overwrite newer estimates or selected answers.

## Files

- `backend/app/services/questionnaire_choices.py`: new catalog-capability resolution and estimate service.
- `backend/app/persistence/repositories.py`: resolve the runtime questionnaire without mutating published records.
- `backend/app/persistence/import_legacy.py`: bootstrap imports use the published questionnaire before the hardware catalog is fully initialized.
- `backend/app/algorithms/duct_routing.py`: expose the existing conductor capacity as a shared constant.
- `backend/app/api/routes_requirements.py`, `routes_catalog.py`: read-only suggestion endpoints.
- `frontend/src/components/requirements/Questionnaire.tsx`, `api/client.ts`, `types/api.ts`: typed choices, explicit suggestions and API contracts.
- `frontend/src/components/common/DesignViewport.tsx`: shared native/fallback fullscreen behavior and toolbar launcher interface.
- `frontend/src/components/schematic/SchematicViewer.tsx`: zoom controls, fullscreen and responsive properties.
- `frontend/src/components/layout/Layout2DViewer.tsx`, `threeD/Panel3DViewer.tsx`: fullscreen canvases and responsive drawers.
- `backend/tests/test_questionnaire_choices.py`, updated `test_postgres.py`: capability enforcement, suggestion immutability and API tests.
- `frontend/src/components/common/DesignViewport.test.tsx`, `schematic/SchematicViewer.test.tsx`, updated `requirements/Questionnaire.test.tsx`: fullscreen lifecycle/fallback, persistent zoom controls, numeric choices and user-controlled suggestions.

## Database and teammates

No database schema, published questionnaire, rule seed or asset-library record was changed. Options are derived at runtime from existing catalog versions and the existing algorithms. No new migration or seed data is required. Fresh imports still use the normal migration/import workflow; the database head remains `0003_constraints`.

Teammates should pull the matching source changes and restart the backend/frontend. Run from `backend/` with the existing private PostgreSQL configuration:

```powershell
.\venv\Scripts\python.exe -m app.persistence.manage status
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8731
```

From `frontend/`:

```bash
npm run dev -- --host 127.0.0.1
```

Linux teammates can use their activated environment's `python` for the same backend module commands.

## Verification

Results: 87 backend regression tests passed, including PostgreSQL integration tests, followed by a passing additional four-feeder / 100 A generation test. All 34 frontend tests passed, and the production TypeScript/Vite build passed. Existing Starlette/AnyIO deprecation and large JavaScript chunk warnings remain.

Automated coverage includes rejected 300 A/unsupported choices, derived demand, no mutation of user answers, no fabricated above-catalog recommendation, project-write rejection, fresh database import, native fullscreen exit events, rejected/absent fullscreen API fallback, Escape restoration, canvas identity, external fullscreen launchers and schematic zoom actions.

Live API checks confirmed supported incomers `[100, 250]`, suggestions for 4/12/16 feeders, server rejection of 300 A and an unchanged saved project after requesting suggestions. Live visual browser verification was blocked by a browser-tool initialization failure; no successful interactive visual check is claimed for this update.
