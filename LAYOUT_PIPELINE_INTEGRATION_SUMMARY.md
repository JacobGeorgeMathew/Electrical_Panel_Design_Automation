# Layout pipeline integration

This note records the placement-to-routing integration. For the current DB workflow, API behavior, stage map, and simplification limits, see [DB_WORKFLOW.md](DB_WORKFLOW.md).

The orchestrator uses the CP-SAT solver's `LayoutResult` as the single placement input to the JPS/Theta* router. The router uses placed component terminal coordinates and the same enclosure dimensions. It retries with A* if JPS pruning cannot find a path. Both components use a per-enclosure `LayoutConfig`, in millimetres from the enclosure lower-left-front origin.

The returned PDM carries the chosen enclosure, mounting plate, zones, placed components, rails, and routes. Physical validation checks those outputs and their references back to the CEM before the design is marked final. This remains a prototype geometry pipeline; it is not a standards compliance or production engineering determination.
