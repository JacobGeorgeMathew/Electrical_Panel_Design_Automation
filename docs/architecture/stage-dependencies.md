# DB stage contracts and invalidation

P3-T01 defines an executable, validated dependency registry for the prototype DB
designer. [contracts.py](../../backend/app/services/stages/contracts.py) is the
source of truth. `STAGE_REGISTRY.invalidate(changed_paths)` returns a deterministic
plan containing direct consumers, the ordered downstream closure, validation
obligations and any conservative fallback roots. It performs no engineering,
database, file, revision or job mutation.

This is the contract boundary for adapters and execution work. Detached electrical
and physical/documentation adapters are described below. The
[full generator](../../backend/app/services/orchestrator.py) still runs its existing
pipeline, including its enclosure candidate/retry loop. The registry and adapters
do not themselves implement execution scheduling. P3-T05 now provides the
[incremental scheduler and explicit Recompute boundary](incremental-recompute.md),
including verified cache reuse and preview/operation acceptance in place of
propagation's immediate publication. The full generator remains the independent
automatic-generation oracle. The planning lifecycle remains read only.

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
| `routes` | Placement and connected duct network, canonical connections/nets, saved policy | PDM routes, exact wire geometry and duct bundle accounting | placement, connectivity | Duct routing, endpoint identity, finite geometry |
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

## Detached electrical execution adapters (P3-T02)

[electrical.py](../../backend/app/services/stages/electrical.py) wraps the existing
requirements, calculations, selection, connectivity (graph plus netlist), and
schematic algorithms. Each function accepts a frozen Pydantic input and returns a
serializable frozen output. `Snapshot[T]` validates the legacy payload as `T`,
rejects nonfinite values and stores canonical JSON as an immutable string.
`read()` returns a fresh mutable model/value for the existing algorithms; changing
it cannot mutate an input, prior result or another execution.

The caller supplies project/panel identity, engine version, registered algorithm
version, exact archetype/rule versions and template content, and exact component
catalog version and ordered rows. Catalog publication/version resolution belongs
to the caller before execution, outside the stage. No adapter loads a template
file, opens a repository/session or resolves a latest catalog version. Supplied
component/product/CAD model version IDs follow selected components. Catalog order
is retained because existing SPD selection consumes the first candidate.

`DocumentIdentities` carries explicit `(namespace, role, document_id)` bindings.
Roles are the existing generator identifiers, not names, ratings, catalog IDs or
array positions in the working document. Unbound new roles retain legacy IDs;
callers retain bindings for removed roles. Adapters temporarily use role IDs for
the legacy engines' fixed lookups/sorting, then rebind component/module/calculation,
net/connection IDs and schematic endpoint references. Terminal IDs remain local
to supplied component records; `PANEL_ROOT` remains the reserved enclosure
interface. Duplicate/effective ID collisions are rejected. Reversed lexical
document IDs do not reorder feeders, phases, terminal pairs or schematic layout.

Selection accepts explicit pinned component choices, including accepted ratings.
Connectivity accepts explicit authoritative topology and checks references before
returning it without regeneration. Schematic execution produces a generated legacy
engine dictionary; it does not merge a saved `SchematicPresentation` or authorize
overwriting manual drawing intent. The caller must retain manual presentation or
explicitly request regeneration. Calculations continue using requirement-derived
prototype methods; adapters do not reinterpret manual ratings as new engineering
methods. They return owned slices, never mutate a working document, and do not
publish anything. These extraction boundaries do not implement the later scheduler,
cache or manual-intent reconciliation.

The full generator remains unchanged as the independent oracle. Adapter tests in
[test_electrical_stages.py](../../backend/tests/test_electrical_stages.py) compare
both saved baseline boards against full generation and pinned CEM/schematic hashes,
exercise deterministic mapped IDs and reference integrity, serialization/schema,
deep immutability, explicit pins/choices/topology and existing failures. A separate
test poisons file access, repository construction and database transaction/query
entry after input materialization and executes all five stages successfully.
No wire-schema or engine/generator version change is needed for this extraction:
the original algorithms and baseline engineering output remain unchanged.

## Detached physical and documentation adapters (P3-T03)

[physical.py](../../backend/app/services/stages/physical.py) and
[artifacts.py](../../backend/app/services/stages/artifacts.py) expose the existing
algorithms behind frozen, serializable inputs and outputs. These are detached
execution functions; the full generator remains an independent oracle. No HTTP
route, scheduler, cache, persistence transaction or publication flow is changed.

The ten registry stage IDs remain unchanged. Physical substeps have this order:

| Registry stage | Adapter order and inputs | Output |
| --- | --- | --- |
| `placement` | `enclosure_stage`: CEM, pinned enclosure rows, layout, required IP and optional fixed enclosure ID | Ordered feasible candidates |
| `placement` | `zoning_stage`: one candidate, layout and pinned hardware | Existing enclosure zones, category preferences and hard trough reservations |
| `placement` | `placement_stage`: zoning, CEM, generation intent and optional accepted layout | CP-SAT components/rails or retained accepted placement |
| `placement` | `ducts_stage`: placement and its pinned zoning/hardware | Physical ducts, construction and accessories |
| `routes` | `routes_stage`: placed/edited PDM, CEM, layout and route locks | Whole connected duct network, checked wire geometry and bundle accounting |
| `physical_validation` | `physical_validation_stage`: routed PDM and CEM | Zero physical violations plus checked component/wire geometry |
| `bom` | `bom_stage`: CEM selection and assembled PDM | Existing quantities, identities and cut lengths |
| `cad` | `cad_stage`: PDM, CEM, schematic dependency and generator/model pins | Eligible primitive payload and optional FreeCAD script text |

The caller closes catalog/document read transactions before execution and supplies
exact versioned enclosure/hardware rows, context/engine identity and layout.
Substeps use the registered `db-placement-1` algorithm version; other adapters use
their corresponding registry version. Enclosure retry belongs to the caller:
iterate the returned candidates in order and retain the existing retryable error
policy. A supplied fixed enclosure ID filters candidates before feasibility, so
it cannot silently select another enclosure. Zoning means the current metadata
and layout preferences/reservations, not a new zoning solver.

`GenerationIntent.locked_placements` contains CEM component IDs. Locked/manual
placement requires an accepted PDM. The adapter conservatively retains that entire
placement and assembly, validates it against current component geometry/heat and
the selected enclosure frame, and clears routes for explicit network rerouting.
It neither repositions unlocked neighbours nor claims partial fixed-variable
CP-SAT support. Missing locked components, a changed enclosure frame or incompatible
selected components fail. Without an accepted PDM, ordinary generation uses the
unchanged CP-SAT constraints and independent geometry checks. Nonzero rotations
remain unsupported for the existing obstacle model.

`routes_stage` invokes **DuctRouter** for the complete network; routes are never
mixed with an old subset. Saved PDM policy controls clearance/validation. A route
lock blocks full network rerouting with a structured conflict. Disconnected or
obstructed trunks, bad placement, duct collision/fill, missing routes and stale
endpoint/conductor references fail. Opaque document component/net/connection IDs
remain intact; supplied role bindings isolate the legacy main-net diameter/color
heuristics from renamed net IDs. Terminal IDs and exact off-grid endpoints remain
the existing router's responsibility.
The registry explicitly includes duct `route_ids`, `wire_area_mm2` and
`capacity_pct` in the routes result: DuctRouter updates these after whole-network
routing. Placement owns duct geometry/catalog definitions and local component
geometry; routing owns conductor paths/fillets and bundle accounting.

`local_geometry_stage` regenerates component meshes and wire fillets from existing
placements and waypoints after independent physical checks. It never calls a path
router, moves a component, changes a route ID or replaces waypoints. A component
move with stale terminal endpoints requires explicit network rerouting and fails
local geometry validation. Physical validation uses this same geometry boundary.
CAD revalidates current PDM/CEM and rebuilds derived geometry before serialization;
stored validation lists and old wire PASS flags cannot authorize eligible output.
Any computed physical violation, including a warning, blocks CAD. BOM can run after
assembly without waiting for routing, as the registry already specifies.

`LayoutSnapshot` sorts category sets for deterministic JSON round trips.
`PhysicalSnapshot` validates the PDM and retains legacy numeric representation:
the router assigns integer zero to unused duct accounting fields, and ordinary
typed JSON rehydration would turn it into `0.0` and change snapshot hashes. The
snapshot preserves that representation after validation; it does not omit or
normalize any geometry, identity or engineering value. Reads return fresh models.

The adapters produce payloads/script text only. Existing content-addressed assets,
revision writing and compatibility pins remain caller responsibilities. Generator
and model versions must be resolved before calling CAD. No new engine/generator
version is needed for this extraction because baseline output stays unchanged.
Native FreeCAD/STEP execution and electrical/manufacturing qualification remain
unverified; geometry, thermal and duct fill are prototype assumptions.

[Physical adapter tests](../../backend/tests/test_physical_stages.py) compare both
frozen DB baselines, PDM/CAD/BOM hashes, GLB bytes and script bytes; check exact
terminal endpoints, opaque identities, locks, schema round trips and immutable
inputs; poison file/repository/database access after materializing inputs; and
reject invalid physical data before CAD serialization. Verification commands and
limits are recorded in the [attempt report](../../planning/task_reports/P3-T03/attempt-01.md).

## Content signatures and stage cache (P3-T04)

[cache.py](../../backend/app/services/stages/cache.py) registers the typed adapters
above and provides content signatures and PostgreSQL cache/state storage.
`0007_stage_results` adds two empty tables without converting existing documents
or rewriting any revision. Readiness requires that migration; apply it only during
an intended upgrade. Generated mappings come from `tools.build_schema_models`.

`make_signature(adapter, inputs, pins, policy, context)` captures the complete
detached input DTO as canonical JSON, including supplied catalog/template content,
opaque identity bindings and significant array order. Dictionary order does not
affect the signature. Adapter names distinguish the four placement substeps and
local geometry from whole-network routing. Input/output JSON schema fingerprints,
the registry schema and relevant contracts/algorithm versions are part of the key.
Mismatched input types, ownership, engine/catalog pins, CAD pins and saved PDM
policy are rejected. Context must be supplied for zoning/ducts, which lack their
own electrical context field.

Exact version dependencies follow each stage and its registry prerequisites:

| Pin/content change | Signature consumers |
| --- | --- |
| Rules or archetype | All adapters |
| Component catalog | Selection and downstream adapters |
| Enclosure/hardware catalog or saved policy content/version | Placement substeps, routes, physical validation, BOM and CAD |
| Generator or model versions | CAD |
| Engine version or unknown catalog key | All adapters |
| Algorithm/contract change | That stage and downstream adapters |

Policy content is hashed independently of its version label. Whole catalog
manifest hashes are deliberately excluded: exact consumed pins and materialized
content determine eligibility, so publishing an unrelated catalog does not evict
an otherwise eligible result. Unknown catalog keys are conservative. Callers must
resolve published immutable versions before constructing inputs. A version ID is
not proof of publication or approval. Signatures conservatively include the whole
typed adapter input, rather than guessing which attributes its implementation
might ignore. Document sequence, provenance and transient display state are outside
that boundary. Supplying changed typed input content produces a different key.

`StageCache.lookup(signature)` reads the newest matching entry, closes the read
transaction, validates the complete signature, typed output and result/asset
envelope hash, and verifies every managed file's key, size and SHA-256. It returns
`MISSING`, `VALID` or `CORRUPT`; it performs no engineering, repair or writes and
never falls back behind a corrupt newest entry. Asset audits include all cache
asset references, including superseded entries, without deleting shared content.

The caller explicitly registers desired inputs with `observe(document_id,
sequence, signature, blocked_by=...)`. It updates document-local input/output
versions and `DIRTY`, `BLOCKED`, `FAILED` or `VALID` metadata, preserving the prior
accepted output reference. Input versions advance only when the desired signature
changes; output versions advance only when accepted output/asset content changes.
`VALID` describes this adapter's accepted cache result, not whole-document
engineering validity or publication eligibility. Dependency blockers are supplied
by the caller's plan; cache inspection never executes prerequisites.

After explicitly executing `ADAPTERS[name].execute(inputs)` outside transactions,
the caller uses `record_success`, or explicitly uses `accept_cached` for a verified
hit. Both fence completion by current document sequence and registered input
signature and refuse blocked state. `record_failure` stores only a structured code
and retains prior output. `observe` retains same-input failure until explicit
success. Hashing/assets run outside transactions; cache publication and its state
update share a short transaction with project/document locks. Changed document
sequence or desired input signature prevents an old result from becoming current.
These fences do not implement durable worker leases, cancellation or job retries.

Stage results are append-only through the runtime engine. Explicit recomputation
may append a replacement for a corrupt entry; it does not overwrite that entry,
an accepted historical output, a shared asset or a revision. Cache adoption changes
cache metadata only. Working snapshots, revision output manifests, project locks
and recovery checkpoints remain unchanged. No Save/load/generate/propagation route
is wired to execute this cache. P3-T05's explicit Recompute endpoint now uses it;
see [execution and acceptance](incremental-recompute.md). Publication and strict
engineering checks retain their
existing responsibilities and prototype limitations.

[Cache tests](../../backend/tests/test_stage_cache.py) cover the pin matrix, policy
content, schemas, canonical ordering, detached results, corrupt envelopes/typed
payloads/assets, explicit replacement, metadata clocks, completion fences, atomic
rollback and historical row preservation. The
[attempt report](../../planning/task_reports/P3-T04/attempt-01.md) records actual
commands, profile outcomes and remaining verification limits.
