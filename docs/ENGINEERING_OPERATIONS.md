# Bounded working-document operations

These commands edit prototype DB working documents. CEM owns electrical
connectivity, PDM owns enclosure millimetres, and the typed single-page schematic
owns drawing millimetres. Accepted draft edits do not establish engineering,
manufacturing or standards approval.

## Boundary and contracts

`POST /api/v1/projects/{id}/document/operations/preview` loads the server-owned
working document and exact published catalog choices, closes its read transaction,
and evaluates ordered commands on a detached copy. The result is a preview,
never permission to apply or publish. Existing single-model requests remain valid.

Every batch carries document ID, document sequence, expected project lock version,
and revision base. Every command carries a UUID, origin and primary snapshot hash.
Multi-model commands additionally require `preconditions.model_sha256` with the
exact hash or null for **each** declared model. Member preconditions describe the
candidate at that member's execution point. Missing or stale fences fail.

`OperationBatchRepository.commit` is the existing internal commit boundary. It
reevaluates commands, checks the base under the project lock, and atomically
stores the document, every affected/intermediate snapshot, ordered members and a
retry receipt. Reusing an idempotency key with identical content returns the
original receipt, including after later edits; different content conflicts.
Errors leave prior state intact. Runtime requests never use JSON fixture catalogs.

The operation service and repository are available for later workspace/API
integration. This scope adds the read-only history route below; it does not add
HTTP commit/undo routes or connect legacy local editor transforms to commands.
The UI's existing local undo remains a separate overlay mechanism.

## Component commands

- `AddComponent` targets the panel and declares CEM/PDM effects. Parameters select
  an exact published `component_version_id`, catalog code and explicit nullable
  `product_version_id`. A non-null product must be a published version belonging
  to that component version. Product selection never follows the latest product.
- Terminal intent must explicitly say `UNCONNECTED` and enumerate every catalog
  terminal exactly once. Adding a device never invents electrical connections.
- Placement specifies absolute enclosure-mm position, an existing zone and an
  explicit nullable rail. DIN devices require a rail. The device must fit its
  zone and pass the saved physical policy, including thermal density, with no
  violations. Adding to rotated layouts is unsupported, as with physical moves.
- Electrical and physical IDs are deterministic UUIDs derived from the operation
  UUID. Local terminal IDs and catalog geometry come from the pinned row. Exact
  component/product versions are retained both on the CEM component and in the
  document's `component:<id>` / `product:<id>` catalog pin map. The original
  generated-base catalog manifest remains retained; these are dirty draft pins.
- `RemoveComponent` without `confirmed_cascade` returns a read-only consequence
  proposal. Its dependency lists and SHA-256 cover affected connections, routes,
  symbols, wires, junctions, assigned modules, recursive accessories, clearances,
  physical diagnostics, functional graph references and explicit topology
  evidence. A module is unassigned rather than deleted. Unrelated conductors and
  devices remain. Empty legacy nets remain dirty for explicit recomputation.
- Commit requires the exact returned confirmation. A different closure or
  dependent content requires a new proposal; overlapping parent identities fail
  as ambiguous. Removing physical routes also removes their duct memberships.
  Pins and topology evidence for the removed component are removed atomically.

## Schematic and connection commands

`MoveSymbol` translates the symbol, absolute pin anchors and attached wire
endpoints. `UpdateSchematicLabel` changes a symbol, pin or wire label. Neither
changes CEM or PDM. Presentation edits dirty CAD. They do not run a router or
certify drawing quality; intermediate wire waypoints remain presentation data.

`UpdateJunctionPresentation` changes visibility/label of a marker at an existing
shared pin. At least two actual conductors in the same CEM net must share that
pin. A graphical crossing cannot create a junction or electrical connection.
The typed `junctions` extension is omitted when empty so earlier canonical
snapshots and their hashes remain readable without reserialization changes.

`ModifyElectricalConnection` supports `CREATE`, `REPLACE` and `DELETE`. Creation
uses a null target and allocates stable conductor/wire IDs from the operation
UUID. Replacement/deletion target an existing conductor. The command requires:

- Explicit terminal endpoints, existing net/class, conductor material, positive
  finite cross-section, insulation diameter/type and minimum bend radius for
  creation/replacement. Terminal capacity limits are checked when available.
- Exact `invalidated_route_ids` and `removed_net_ids`; the latter lists any net
  emptied by this edit. Unrelated routes/nets cannot be included.
- Explicit supply and phase/N/PE role evidence in the working document's
  `configuration.electrical_topology`: `domains` contain `component_id`,
  `terminal_id`, `supply_id`, `role`; optional permanent `equivalences` use the
  existing connectivity checker's evidence contract. Versioned document Save
  validates this typed extension. Legacy project configuration remains bounded
  to enclosure settings.

The P2-T05 checker must resolve the whole candidate topology. Missing domain
evidence, cross-phase/supply/PE conflicts and the legacy virtual earth anchor
block electrical edits. Classes/labels never supply missing role evidence.
An existing schematic requires exactly one pin per endpoint; ambiguity fails
atomically. Flat CEM conductors, net membership, schematic wires and invalidated
physical routes change together. Existing wire IDs/labels survive replacement;
changed wires receive endpoint-to-endpoint draft paths. Connectivity, schematic,
routes, physical validation, BOM and CAD remain dirty until explicit processing.
This is prototype topology validation, not conductor sizing or bonding approval.

`RegenerateSchematic` requires explicit `PROPOSED` status and a proposal ID. It
adapts the existing schematic engine into the typed single-page model. Existing
symbol/pin/wire identities and labels survive; manual positions and existing
wire paths are preserved by default. `replace_manual_positions: true` explicitly
requests a replacement layout **in the proposal**. Preview never constitutes
approval: the commit boundary rejects proposed commands. General proposal
acceptance is reserved for the lifecycle's later acceptance workflow.

## Undo and redo

`GET /api/v1/projects/{id}/document/operations/history` returns eligible undo/redo
batch IDs, document sequence, lock version and current content hash. Lists run
oldest to newest; only the final item is eligible. A batch is one history group.
A drag should use transient previews and submit one final move or one ordered
batch on release. Multiple pointer events must not each be committed separately.

Internal `DocumentService.apply_history` / `OperationBatchRepository.apply_history`
accept `HistoryRequest`: a new batch and operation UUID, action `UNDO` or `REDO`,
target batch UUID, origin, all current version/base fences and
`before_content_sha256`. Clients cannot supply inverse snapshots or raw patches.

The server resolves before/after snapshots from immutable history, verifies
their hashes/references, checks the current semantic state, closes the read
transaction, and prepares an inverse. The existing writer rechecks the document
under lock. Undo/redo append new operation members and versioned receipts; they
restore all model snapshots, configuration, pins and dirty stages while clocks
and provenance advance. Published revisions, assets and prior receipts remain
unchanged. Retries are idempotent.

Undo/redo history is reconstructed from durable batch receipts after reopen or
backend restart. A new accepted change clears the redo branch; retained rows are
never deleted. No-op receipts do not add undo entries or clear redo. A direct Save
that changes inputs/configuration, conversion or a different revision base fences
old history rather than overwriting newer content. A no-op Save retains history.
Metadata-only lock changes require fresh version fences.

## Verification

Focused suites are `test_component_operations.py`, `test_schematic_operations.py`,
`test_operation_history.py`, `test_operation_command_contract.py` and the existing
operation/persistence/physical/engineering suites. Database tests use the existing
fixture-owned disposable PostgreSQL databases. Shared command fixtures live in
`frontend/src/types/fixtures/operation-commands-v1.json`; TypeScript checks and
Vitest cover their client shape. No schema migration or engine/generator version
bump is required: generated engineering and CAD outputs are unchanged.

The attempt report records actual commands and outcomes. Desktop interaction,
HTTP mutation integration, native CAD execution and human engineering review are
not established by these service/contract tests.
