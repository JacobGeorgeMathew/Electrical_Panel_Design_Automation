# Layout Pipeline Integration Summary

## Status
The electrical panel application already had the major building blocks in place, but the runtime pipeline was not consistently using the same source of truth across placement and routing. The biggest issue was that the solver and the router were designed to work together, yet the orchestration layer was still calling them in a disconnected way.

## Architecture reviewed

### Engineering model (CEM)
- [backend/app/models/cem.py](backend/app/models/cem.py)
- Represents the canonical engineering model:
  - requirements
  - selected components
  - electrical graph
  - nets
  - calculations
  - compliance state

### Physical design model (PDM)
- [backend/app/models/pdm.py](backend/app/models/pdm.py)
- Represents the physical panel geometry and route data:
  - enclosure dimensions
  - functional zones
  - placed components
  - DIN rails
  - wire routes
  - validation violations

### Placement solver
- [backend/app/algorithms/cp_sat_placement.py](backend/app/algorithms/cp_sat_placement.py)
- Produces a `LayoutResult` with:
  - feasible / status / message
  - placed `PhysicalComponent` entries
  - `DINRail` objects
  - row count and objective values

### Router
- [backend/app/algorithms/jps_theta_star.py](backend/app/algorithms/jps_theta_star.py)
- Uses actual placed geometry, not independently guessed positions.
- Its intended contract is to consume the real `LayoutResult` from the solver.

### Layout configuration
- [backend/app/algorithms/layout_config.py](backend/app/algorithms/layout_config.py)
- This is the intended single source of truth for:
  - grid size
  - margins
  - device spacing
  - duct gaps
  - plate clearance
  - zone preferences
  - preferred component heights
  - DIN/plate categories
  - styling colors

## Actual runtime flow
The intended flow is:

1. Requirements
2. Engineering calculations
3. Component selection
4. Graph / electrical net generation
5. Layout configuration
6. CP-SAT placement solver
7. `LayoutResult`
8. DIN rails + placed components
9. JPS/Theta* routing
10. `WireRoute[]`
11. API response
12. Frontend rendering

The orchestrator was meant to coordinate this chain, and the code already indicates that this is the intended architecture.

## Breakpoint identified
The real issue was in [backend/app/services/orchestrator.py](backend/app/services/orchestrator.py):

- the optimizer was producing a `LayoutResult`, but the orchestrator was not feeding that result into the router as designed;
- the router was being called with incomplete arguments and without the actual placed rail geometry;
- the system therefore behaved like separate subsystems instead of a single end-to-end pipeline.

This meant the final design could look disconnected or inconsistent even though the individual modules themselves were valid.

## Architectural rule that must hold
The correct chain is:

`LayoutConfig -> CP-SAT placement -> LayoutResult -> components + rails -> JPS/Theta* -> WireRoute[]`

This is the contract that should always be respected. The router must not invent component locations or choose rail positions independently.

## What was corrected
I updated the integration so that the orchestrator now:

- runs the solver to obtain the real `LayoutResult`;
- validates feasibility using the solver result;
- uses the actual solver output to route nets;
- passes the real placed components and DIN rails into the router via `route_layout(...)`.

I also centralized and tightened the config semantics in [backend/app/algorithms/layout_config.py](backend/app/algorithms/layout_config.py) so category and zone rules are not scattered across ad hoc logic.

## Impact
This brings the application back to the intended architecture:

- one source of truth for layout behavior;
- one generated placement model consumed by routing;
- coherent PDM output for the frontend;
- realistic panel-like organization instead of arbitrary disconnected geometry.

## Validation
I ran the backend test suite after the integration fix:

- `python -m pytest -q`
- result: `4 passed in 8.60s`

## Current state
The project is now in a coherent integration state where the placement solver and router are connected through the same layout definitions and actual generated geometry, rather than acting as independent components.
