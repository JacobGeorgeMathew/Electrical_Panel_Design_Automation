# DB stage contracts and invalidation

P3-T01 defines an executable, validated dependency registry for the prototype DB
designer. [contracts.py](../../backend/app/services/stages/contracts.py) is the
source of truth. `STAGE_REGISTRY.invalidate(changed_paths)` returns a deterministic
plan containing direct consumers, the ordered downstream closure, validation
obligations and any conservative fallback roots. It performs no engineering,
database, file, revision or job mutation.

This is the contract boundary for subsequent adapters and execution work. The
[full generator](../../backend/app/services/orchestrator.py) still runs its existing
pipeline, including its enclosure candidate/retry loop. This task does not extract
algorithms, implement a cache/scheduler, replace propagation's current full
generation/publication behavior, or claim incremental/full semantic equivalence.
Those are separate P3 tasks. The planning lifecycle remains read only.

## Registry invariants

Each frozen Pydantic `StageContract` registers:

- An existing v1 `DirtyStage` ID and explicit algorithm version.
- Named inputs and consumed document field paths; a produced input names its
  prerequisite stage and output. Authoritative manual/document/catalog inputs
  have no producer reference.
- Named serializable output boundaries and their field paths.
- Execution prerequisites and validation obligations.

`StageRegistry` rejects duplicate stage IDs, undefined prerequisites, unknown
stage IDs, cycles (including self-cycles and disconnected cycles), undefined typed
document field paths, missing output
references, unpaired producer/output references, producer references outside the
prerequisite set, and inputs unrelated to the referenced output's paths. Named
inputs, outputs, prerequisites and obligations must be unique within their scope.
Frozen tuples and a read-only stage lookup protect the validated definition.

Topological order is deterministic; declaration order breaks ties. A changed
downstream stage does **not** invalidate its prerequisites. A future executor must
load valid prerequisite results or explicitly establish missing/invalid inputs
before execution. An invalidation plan alone is neither an executable job nor
evidence that a stage's checks passed. Validation obligations remain unresolved
until an authorized execution performs them.

## Stage boundaries verified against current source

The ten stage IDs match backend `DirtyStage` and
[TypeScript](../../frontend/src/types/document.ts) without a wire-schema change.
Coarse boundaries preserve the existing document vocabulary. In particular,
`connectivity` includes both electrical graph and netlist; there is no unregistered
`NETLIST`, `CALC_001` or `ENCLOSURE` stage.

| Stage | Main inputs | Output boundary | Prerequisites | Principal obligations |
| --- | --- | --- | --- | --- |
| `requirements` | Answers, archetype and rule version pins | Validated requirement result | None | Requirement rules and finite units |
| `calculations` | Validated answers, explicit DB calculation fields, manual component ratings | CEM calculations | requirements | Finite units; retain prototype assumptions |
| `selection` | Calculations, answers, exact component/product choices | CEM components and module assignments | calculations | Published catalogs, identities, requirement rules |
| `connectivity` | Components, canonical connection/net intent, supply/phase answers, explicit terminal-domain evidence and enclosure interfaces | CEM graph, nets and connections | selection | Terminal references, netlist integrity, electrical consistency |
| `schematic` | Connectivity, components, saved symbols/wires/junctions, manual presentation intent | Schematic presentation | connectivity | Reference integrity; preserve manual presentation |
| `placement` | Components and connection pairs, enclosure geometry/catalog, assembly catalog, locks and saved policy | Selected enclosure/plate frame, components, zones, rails, ducts, accessories, construction, heat loss and policy | selection, connectivity | Hard physical constraints, locked placements, enclosure mm |
| `routes` | Placement and connected duct network, canonical connections/nets, saved policy | PDM routes and exact wire geometry | placement, connectivity | Duct routing, endpoint identity, finite geometry |
| `physical_validation` | Placement, routes, CEM intent and saved policy | Physical/thermal validation results | placement, routes | Empty physical violation list, including warnings |
| `bom` | Electrical components, accessories, rails and ducts | BOM rows | selection, placement | Stable IDs, catalog quantities and cut lengths |
| `cad` | Validated physical geometry, schematic presentation, generator/model pins | CAD/output descriptors | physical_validation, schematic | Strict validation, stable references and managed asset integrity |

These are owned slices of resolved snapshots/results, not permission to replace
whole CEM/PDM snapshots or allocate fresh logical IDs. Calculations consume a
manual rating change conservatively; the existing DB calculation implementation
still derives its values from requirements. Later adapters must reconcile that
intent without overwriting an accepted manual rating.

Source verification:

- `DesignOrchestrator.generate_design` validates answers, calculates, selects,
  creates graph/netlist and schematic, then tries feasible enclosures.
- `_physical_design` passes connection pairs to CP-SAT, builds ducts, calls
  `DuctRouter`, constructs assembly/geometry, rejects **all** physical violations,
  and builds exact wire geometry. The registry combines these internal steps into
  placement, routes and validation contracts; adapters must preserve the existing
  ordering and both placement and route/geometry checks.
- `assembly_bom` currently consumes components/accessories/rail/duct cuts. It does
  not consume route lengths, so an isolated device move need not invalidate BOM.
- Schematic movement updates pins and wire endpoints locally. Its remaining
  schematic layout/check work stays dirty; CEM connectivity remains authoritative.
- The current CAD engine generates physical primitives. The `cad` contract also
  fences schematic outputs for later artifact adapters; it does not add a new
  schematic CAD exporter in this task.

## Consumed paths and conservative fallback

Paths are relative to the resolved document: `cem`, `pdm`, `schematic` and
`requirements` address snapshots; `pins`, `configuration`, `generation_intent`
and `enclosure_interfaces` address document metadata. `results` identifies
detached stage outputs. `algorithms.<stage_id>` identifies changes to the
registered algorithm version, rather than a new working-document field.

Dot-separated `*` matches one collection member. A parent path overlaps its
descendants in either direction: replacing `pdm.components` changes every
consumed child. A declared subtree consumes all its contents, including terminal
and conductor metadata. Typed paths are checked against the current Pydantic
document/snapshot fields, including nested models. Unknown typed children such as
`pdm.components.*.future_geometry` trigger the conservative PDM closure even when
a consumer reads all components. Open dictionaries remain consumed subtrees.
Concrete collection positions may be supplied, but plans
must never derive, normalize or replace opaque stable IDs from those positions.
Requirement paths such as `requirements.items.incomer_rating.value` are logical
paths keyed by requirement identity; array-index paths also conservatively overlap
the declared `requirements.items` subtree.

Every declared consumer is invalidated, followed by its transitive dependants.
If no specific path/subtree declares the change, invalidate **producers and
consumers** of the affected snapshot root and their downstream closure. A bare
whole-model reader cannot hide an otherwise unknown model field. Thus unknown
PDM fields invalidate the physical closure; unknown CEM fields invalidate the
electrical/physical closure; unknown schematic fields invalidate schematic/CAD.
Unknown requirements invalidate the entire DAG. Unknown namespaces,
configuration fields, catalog pin names, manifest hashes and unrecognized display
fields conservatively invalidate the entire DAG. An empty change collection
means no changes; a single unrecognized/empty path conservatively invalidates all.

Only known transient display subtrees (`display.camera`, `selection`, `visibility`,
`grid`, `snap`, `explode`, `panels`, `tool`) are exempt. The `display.` prefix applies
to each entry. A replacement of the whole `display` root is conservative because
it may contain unknown fields. Saved symbol positions and labels are schematic
presentation, not transient display state. Callers must classify paths from
server-owned operation definitions, never accept a client's display-only claim as
authority to skip checks.

## Invalidation matrix

The following lists the scheduled **contract closure**, not stages actually run
by the current full generator. Existing dirty stages accumulate during Apply;
display edits do not clear prior dirty state. Independent edits union their plans.

| Change / representative path | Invalidated stages |
| --- | --- |
| Device move or supported rotation, `pdm.components.*.position` / `rotation_deg`, absolute terminal coordinates | routes → physical_validation → cad |
| Rating/catalog substitution, `cem.components.*.current_rating` / `component_version_id` | calculations → selection → connectivity → schematic + placement → routes → physical_validation + bom → cad |
| Connection edit, `cem.connections` / `cem.nets` | connectivity → schematic + placement → routes → physical_validation + bom → cad |
| Symbol move, `schematic.symbols.*.position` | schematic → cad; zero netlist/calculation work |
| Symbol/wire label or junction presentation | schematic → cad |
| Known transient camera, selection, visibility or other listed display path | Zero stages and zero engineering obligations |
| Enclosure identity/dimension/plate change, `pdm.enclosure_width`, `configuration.enclosure_id` / `enclosure_parameters` | placement → routes → physical_validation + bom → cad |
| Requirement answer, including voltage/rating/frequency/IP/spares | requirements and all downstream stages (deliberately conservative at this boundary) |
| Archetype/rule version, `pins.catalog_versions.archetype` / `rules` | Entire DAG |
| Component catalog version, `pins.catalog_versions.components` | selection and all downstream stages |
| Enclosure/hardware catalog version, `pins.catalog_versions.enclosures` / `hardware` | Physical closure including BOM/CAD |
| Generator/CAD model version, `pins.generator` / `pins.model_versions.*` | cad |
| Saved validation policy or policy version | Physical closure including BOM/CAD |
| Algorithm version, `algorithms.routes` | routes → physical_validation → cad; other stage versions follow their own closure |
| Engine version or unknown catalog/manifest change | Entire DAG |

Connection edits include placement because the current optimizer consumes
connection pairs. Recompute must honor locked/manual positions; invalidating
placement does not authorize replacing them. Likewise, schematic invalidation
does not authorize replacing manual symbol positions. Rotation remains bounded
by the existing handler: nonzero rotations are currently rejected, and a zero
rotation no-op schedules nothing.

## Integration and version policy

[ChangePropagationEngine](../../backend/app/services/change_propagation.py) now
delegates to the registry. Its compatibility `identify_dirty_nodes` entry point
accepts legacy bare requirement names or qualified paths and returns only
registered lowercase IDs. `compute_diff.affected_stages` now uses those IDs in
dependency order, without mixing in requirement names or individual calculation
IDs. The UI renders the stage strings directly. Existing saved CEM `dirty_nodes`
remains readable compatibility data; it is not a scheduling input.

[Operation definitions](../../backend/app/services/operations/registry.py) declare
changed field paths instead of copied dirty-stage lists. Their `dirty_stages`
property resolves the registry closure. Apply/preview still only changes a
detached candidate and marks outputs dirty; it does not optimize, route or publish.
No-op operations add no new dirty stages. Operation-specific immediate checks
retain their existing transport vocabulary and remain unresolved in previews.
`ApplyGeneration` imports the retained candidate's dirty state through the existing
generation acceptance boundary rather than treating generated outputs as edits.
History retains its existing exact snapshot/dirty-state restoration semantics.

Contract schema is `1.0.0`; stage algorithm versions start at `db-<stage>-1`.
Change a stage's algorithm version when its consumed semantics or output changes;
invalidate that stage and its downstream closure. Future signatures must include
canonical consumed values, input/output schema and algorithm versions, relevant
catalog/rule/model pins, engine/generator compatibility and saved policy content,
not just its policy label. This task provides no cache reuse guarantee. Existing
engine/generator revision pins remain unchanged because generated engineering
behavior and geometry have not changed.

## Verification boundary

[Registry tests](../../backend/tests/test_stage_contracts.py) exercise graph and
output references, immutable schema round trips, the change matrix, conservative
fallbacks, deterministic closure, version changes, TypeScript ID compatibility and
real move/symbol previews. Existing document/operation contract tests cover shared
JSON fixtures, finite units, stable references and OpenAPI; operation suites cover
bounded mutation and no-op behavior. Actual commands, results, skips and limitations
are recorded in the [attempt report](../../planning/task_reports/P3-T01/attempt-01.md).

Durable execution/cache correctness, PostgreSQL execution, native CAD and platform
verification are outside this task's evidence. Calculations, thermal/fill limits
and catalog geometry remain prototype assumptions, without standards or
manufacturing certification. Task acceptance remains a human decision; the
registry and this document grant no approval.
