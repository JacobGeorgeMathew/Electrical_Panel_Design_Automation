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
Publication services and immutable-row access guards belong to their separately
scheduled tasks. This migration provides storage, not those application behaviors.

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
