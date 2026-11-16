# Design document storage

`0005_design_documents` adds storage for the
[versioned document contract](../architecture/versioned-document-contract.md).
It creates four tables and changes no existing project, revision, snapshot,
catalog or asset row. Run the existing migration workflow with private database
configuration for an intended installation upgrade. Application readiness now
requires this head. Destructive downgrade is refused.

| Table | Stored values and identity |
| --- | --- |
| `design_documents` | One working aggregate per project: opaque text document/panel IDs, aggregate schema version (`1.0.0` initially), nonnegative bigint document sequence, optional base revision, document JSON and engineering content SHA-256. Project identity remains a PostgreSQL UUID. |
| `design_document_snapshots` | Referenced requirements, CEM, PDM and schematic values keyed by document ID, model kind, positive integer snapshot envelope schema and SHA-256. Multiple values of one model kind can coexist across working edits. |
| `revision_output_manifests` | One manifest per revision, with separate aggregate manifest schema, root SHA-256 and captured source document ID/sequence/content hash. Composite foreign keys require both revision and source document to belong to the same project. |
| `revision_output_snapshots` | Frozen representations keyed by revision and output kind: DOCUMENT, REQUIREMENTS, CEM, PDM, SCHEMATIC, BOM, CAD, VALIDATION or INPUTS_AND_PINS. Each has its own integer snapshot envelope schema and SHA-256. Objects and arrays are supported (including list-shaped BOM output). |

The relational document identity, schema and sequence must match document JSON.
The base revision must belong to the same project. Document sequence is separate
from the existing project lock, recovery version and immutable revision number;
this migration neither resets nor advances any existing clock. Writers must use
the project/document fences and ensure JSON base pointers agree with storage.
Project `lock_version` remains authoritative, including when returning document
metadata after project-only changes.

The new output tables deliberately coexist with the existing CEM/PDM snapshot
tables and `project_revisions.model_manifest`/`content_sha256`. No old digest is
reinterpreted as a complete bundle root. A missing output manifest means that
complete-output storage has not been supplied; migration does not backfill
historical schematic, BOM, CAD or validation values or assert completeness.

The output manifest schema is independent of the working aggregate and integer
snapshot envelope schemas. SQL enforces nonempty schema labels, positive snapshot
versions, JSON container shapes, lowercase SHA-256 syntax, unique storage keys and
ownership. It does not establish digest correctness, supported contract versions,
resolved engineering references or engineering validity. Future repository and
publication boundaries must validate those, store immutable referenced values,
hash canonical content and publish atomically. The engineering content digest
excludes independent clocks/current/base pointers as specified by the approved
document semantics. Updating a working document must retain old referenced values.

Assets continue to use existing managed content-addressed storage and artifact
metadata; these tables add no filesystem paths or asset cleanup behavior.
Runtime immutable-row guards and read-only integrity audits are described in
[revision integrity](REVISION_INTEGRITY.md).

## Complete publication bundles

P1-T04 adds `app/persistence/revision_outputs.py`. Generation, restoration and
project import/duplication prepare detached output values, SHA-256 digests,
projection transforms/bounds and managed files before opening the publication
transaction. Import validates and prepares its entire history before creating the
new project; a failed import still publishes nothing. Failed database publication
may leave unreferenced content-addressed files, as before; no cleanup deletes
shared or historical files.

The independent output manifest has schema `1.0.0`. It contains the revision and
project identities, captured source document ID/sequence/content hash, all nine
snapshot references and original artifact IDs with storage metadata, byte hashes,
sizes, generators and PDM source digest. The existing revision model manifest
anchors its hash in `output_manifest_sha256`. The existing revision digest keeps
its original formula over CEM/PDM hashes and the model manifest; old revisions
and their hashes are untouched.

| Output kind | Frozen representation |
| --- | --- |
| DOCUMENT | Captured source working document, resolved source snapshots and content hash. This is provenance; publication does not install generated outputs into the working document. |
| REQUIREMENTS | Validated requirement set used for this publication, including defaults and resolution state. |
| CEM / PDM | Exact generated model values; their hashes match the existing snapshot tables. |
| SCHEMATIC / BOM / CAD | Exact current engine output containers, including the list-shaped BOM and primitive CAD descriptor. No implicit conversion to a new schematic presentation contract occurs. |
| VALIDATION | Published physical violation list and saved validation policy. Any violation, including a warning, blocks preparation. Prototype route check statuses remain in PDM; an empty violation list is not certification. |
| INPUTS_AND_PINS | Actual answers/configuration and complete model manifest pins before adding the output manifest hash, avoiding a digest cycle. Includes engine, generators, selected catalog/product/model/rule versions and validation policy version. |

The writer locks and checks project `lock_version`, then checks the captured
source document identity, sequence and content hash under a document row lock.
It inserts all outputs, projections, artifact metadata and the current revision
pointer in the caller's single transaction. It performs no engine calls, hashing,
asset I/O or geometry calculations. Source document content and sequence are not
changed by this publication path. The existing generation endpoint's combined
compute/publish behavior remains until the later lifecycle separation tasks.

`verify_outputs` checks the manifest root, exact required output set, each stored
snapshot schema/hash, original artifact metadata and actual file size/hash. It
runs outside write transactions and ignores additional asynchronous exports not
part of the original publication. Historical reads use the verified stored
representations through `services/revision_reader.py` without calling installed
generators. Packages currently retain their
existing version-1 format; complete package transport is a subsequent task.

## Historical reads and legacy conversion

Revision/design GET responses preserve raw saved CEM/PDM containers, rather than
applying defaults from installed model classes. Complete revisions read frozen
schematic, BOM, CAD and validation containers and expose the verified output
manifest and its SHA-256. Original publication artifacts are verified against
their stored size/hash. Changed installed generators cannot alter these reads.
Schematic, CAD and FreeCAD-script GETs accept an optional `revision_id`; the script
comes from the saved artifact even when inputs have since changed.

`is_non_current`, `is_input_stale` and `is_version_incompatible` are independent.
The first compares the current revision pointer, the second compares saved
requirement/configuration inputs, and the third compares installed engine/CAD
generator pins. `is_stale` retains their aggregate for existing clients. Version
incompatibility does not prevent reading supported frozen output envelopes.
Unsupported envelopes or corrupt/missing anchored bundles fail explicitly.

A legacy revision without an output manifest retains its original CEM/PDM,
revision digest and any saved artifacts. Its `output_status` is `MISSING_OUTPUTS`,
with `missing_outputs` listing unavailable snapshot kinds; schematic, CAD and BOM
are null. Dedicated output GETs return `REVISION_OUTPUT_MISSING` when unavailable.
They never synthesize historical bytes. Missing data from an anchored complete
bundle is an integrity error, never silently reclassified as legacy.

An explicit `POST /api/projects/{id}/revisions/{revision_id}/compatibility-conversion`
with `expected_version` creates a new complete revision from legacy CEM/PDM using
installed generators. It records `compatibility_converted_from_revision_id`, uses
the existing publication fences and strict validation policy, and leaves the
source snapshots, artifacts and digest intact. Ordinary restore rejects missing
outputs and directs the caller to conversion. This compatibility operation does
not claim that new generated representations were historical output.

## Restore and legacy overlay proposals

Restore publishes one new revision with `restored_from_revision_id`; its parent
is the head immediately before restoration. Frozen CEM, PDM, schematic, BOM, CAD
and validation values are copied without calling installed generators. Only the
original publication artifacts are reused, with new metadata identities referring
to the same verified content-addressed bytes. Historical rows and hashes remain
unchanged. The project lock and captured working document fences still apply.
Restore does not apply workspace overlays to engineering geometry. General
operation application and working-state rebase remain separate lifecycle work.

`POST /api/projects/{id}/compatibility-proposal` accepts `expected_version`,
`revision_id`, `source` (`workspace`, `recovery` or `supplied`), optional raw
`overlay` for supplied browser data, and `base` evidence. It is a read-only
proposal operation: it never saves a draft, applies operations, reroutes or
publishes. The response preserves the selected raw overlay plus original server
workspace/recovery, current lock/recovery clocks, itemized blockers and proposed
absolute `MoveComponent` before/after positions. Explicit acceptance and future
operation application are required before recomputation/publication.

Base evidence must exactly match `revision_id`, `revision_sha256`, `cem_sha256`,
`pdm_sha256`, the saved `manifest` (including geometry/generator/policy pins), and
`coordinate_frame: enclosure-mm`. The proposal returns the selected revision's
evidence for explicit selection/review; it never infers the base from the current
head or treats a recovery revision ID alone as sufficient evidence. Missing or
mismatched evidence produces `BLOCKED`, preserves the originals and asks the user
to select/review the original base. Recovery also requires its saved
`baseRevisionId` to match the selected revision; supplied target evidence cannot
override a conflicting checkpoint base. A matching base permits `REVIEW_REQUIRED`
proposals only when all items are supported. Unknown/ambiguous component IDs,
nonfinite/malformed transforms, nonzero rotations, legacy schematic data and
unknown fields remain itemized blockers; no snapping, remapping or partial
application occurs. Exact model hashes fence dimensions, terminal identities and
geometry along with stable CEM/PDM IDs. A proposed move does not establish physical
validity; placement, routes, physical validation, BOM and CAD require recomputation
after a future accepted operation batch.

`tests/test_revision_outputs.py` exercises individual representation/artifact
corruption, project/document conflicts, physical warning rejection, failure after
every publication DML statement and successful retry. It checks generate/restore/
import preparation occurs before database writes. These tests use the existing
disposable PostgreSQL fixture; they never migrate a development database.

Mappings and the frozen baseline manifest are generated with the existing
`backend/tools/build_schema_models.py` isolated-database tool. The baseline
manifest must still describe `0001_baseline`, so successful regeneration should
leave its bytes unchanged. Mapping reflection covers Alembic head, including all
four new tables. Never replace the baseline manifest with a head signature.

Verification is in `backend/tests/test_design_document_storage.py`: fresh runtime
initialization versus an upgrade from `0004_projects`, byte comparisons of all
pre-existing row representations, baseline adoption compatibility, Alembic
mapping comparison, document fixture resolution, output digest round-trips,
version/shape/ownership/uniqueness checks and retained parent rows. Tests allocate
only disposable `panel_integration_test_<uuid>` databases and verify their removal.
