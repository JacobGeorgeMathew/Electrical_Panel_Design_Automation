# Publication integrity and deployment permissions

PanelFlow stores prototype Distribution Board engineering publications as immutable
history. Saving a working document changes working state; Publish, restore,
compatibility conversion and package import insert new revisions. Project deletion
sets `projects.deleted_at` and retains revisions and shared content. These controls
do not establish manufacturing or standards compliance.

## Application write boundary

`Database` installs `publication_guards.py` on its SQLAlchemy engine. Typed
UPDATE/DELETE statements against immutable mapped tables fail with HTTP 409
`IMMUTABLE_PUBLICATION`, before mutation. PostgreSQL INSERT ON CONFLICT DO UPDATE
is rejected on every mapped table; insert-only conflict handling remains supported.
Catalog import/constraint seeding insert versions and never update published ones.

The immutable set is derived from mapped metadata, excluding only the five
explicit mutable tables below. It covers revision headers, both legacy model
snapshots, complete-output manifests/snapshots, referenced working snapshots,
catalog/model/rule/questionnaire versions and their child definitions, all
electrical/physical projections, validation, dependencies and provenance. Catalog
identity rows also remain append-only through this runtime boundary.

| Mutable table | Permitted application changes |
| --- | --- |
| `projects` | Working metadata, clocks, pointers, workspace/recovery and tombstones; physical DELETE is rejected. |
| `design_documents` | Version-fenced working aggregate updates; DELETE is rejected. Referenced snapshots remain append-only. |
| `project_requirements` | Updates/deletes only when `project_revision_id IS NULL`; published requirements are retained. |
| `requirement_sources` | Updates/deletes only for draft requirements; published provenance is retained. |
| `generated_artifacts` | Only a matching PENDING job may update storage metadata, completion/error and status fields. READY/FAILED rows and job identity/source/generator fields cannot be updated; DELETE is rejected. |

Matched mutable rows are locked before checking publication state, serializing
concurrent job completions. Startup marks only PENDING jobs failed. Worker failure
handling also fences on PENDING, so it cannot downgrade a completed export.
Project/document/recovery optimistic clocks and short publication transactions
continue to apply. Guards do not perform asset I/O or engineering computation.

These are accidental-mutation guards on supported application SQLAlchemy paths,
not a SQL parser or database authorization layer. Raw text/driver SQL, separate
administrative engines, database owners and filesystem administrators are outside
this boundary. No HTTP endpoint accepts arbitrary SQL. Do not expose owner
credentials to the application or treat the guard as protection from a compromised
database administrator. No schema, migrations or generated mappings changed.

## Deployment roles

Provision roles outside application startup, under the deployment owner's review.
This task does not provision users, grant privileges or alter a live database.
The current process shares its connection pool with its local export worker;
separate worker credentials require a separately reviewed deployment change.

- The migration/import owner owns schema objects and runs reviewed Alembic/import/
  seed commands. It is separate from application and audit logins. Keep published
  versions append-only during import, even with owner privileges.
- The application login must be NOSUPERUSER, NOCREATEDB, NOCREATEROLE, NOREPLICATION,
  not an object owner, and not a member of an owner/admin role. Grant CONNECT to
  its application database, USAGE on its schema and SELECT on required tables.
  Revoke schema CREATE and database CREATE/TEMP where unnecessary. Remove PUBLIC
  grants and inherited privileges that defeat these restrictions.
- Grant INSERT only on the revision/publication/projection/provenance and working
  tables needed by `write_revision`, `DocumentRepository` and `ProjectRepository`.
  Catalog/version/definition tables are SELECT-only for runtime. Grant no UPDATE,
  DELETE, TRUNCATE, REFERENCES or TRIGGER privileges on immutable tables; grant no
  TRUNCATE anywhere. Do not use blanket `ALL PRIVILEGES` or blanket default grants.
- Grant UPDATE on `projects` and `design_documents`; project deletion is an UPDATE,
  so no project DELETE grant is needed. Existing draft replacement needs DELETE on
  `project_requirements` and `requirement_sources`. Its draft-only restriction is
  enforced by the application row guard, not by table-level PostgreSQL grants.
- The existing in-process export worker needs UPDATE only on
  `generated_artifacts(storage_backend, storage_key, sha256, byte_size,
  generation_status, completed_at, error)`. Grant no artifact DELETE. Column grants
  alone do **not** enforce PENDING-only updates; the application guard does that.
  A shared deployment requiring enforcement against direct SQL needs separately
  reviewed database row policies/triggers or a restricted completion function.
  Do not claim those are installed by this task.
- An audit login needs SELECT plus read-only asset-directory access, no INSERT,
  UPDATE, DELETE, TRUNCATE or schema ownership. Run audits without export workers.
  Review effective grants, role memberships and default privileges after upgrades;
  explicitly grant new tables only after reviewing their lifecycle responsibility.

Use `has_table_privilege`/`has_column_privilege` and `pg_roles`/role-membership
inspection under each deployment login. Attempt UPDATE/DELETE/TRUNCATE against
immutable objects only in a disposable acceptance database and verify denial.
Then verify create/save/publish, pending completion, recovery and project tombstone
flows. The repository tests verify application guards; real deployment role
provisioning and its effective grants remain operator verification.

The present prototype uses a local trusted API and CORS origin allowlisting. It has
no user/session authentication or tenant authorization. CORS is not authentication
and does not stop direct clients. Keep deployment access restricted; a shared
deployment must supply reviewed authentication/authorization before exposing the
API. No new identity or origin policy is introduced by this integrity task.

## Verified reads and schema compatibility

`integrity.py` is shared by historical reads and `audit-revisions`. It checks the
revision/model envelope versions, canonical model hashes, legacy revision digest,
complete-output root anchor, project/revision ownership and relational manifest
envelope. `verify_outputs` additionally verifies:

- Exactly DOCUMENT, REQUIREMENTS, CEM, PDM, SCHEMATIC, BOM, CAD, VALIDATION and
  INPUTS_AND_PINS, with each schema and canonical snapshot hash.
- Captured DOCUMENT through `ResolvedDocument`, including typed references,
  ownership and supported document schema. Source ID, sequence and engineering
  content digest must match the output manifest and relational envelope.
- INPUTS_AND_PINS against the revision model manifest, excluding only its output
  root to avoid a digest cycle. CEM/PDM copies must agree with legacy snapshots.
- Unique original artifact IDs, complete pinned metadata, READY status, revision
  ownership, PDM source digest, supported local format, size and actual file hash.
  Later READY exports and legacy saved files are also verified by the reader/audit,
  while they remain outside the original publication manifest.

| Boundary | Supported version / behavior |
| --- | --- |
| Revision and CEM/PDM snapshot envelopes | Integer `1`; unsupported envelopes fail explicitly. |
| Output manifest and its relational envelope | `1.0.0`; both must agree. |
| Every complete-output snapshot envelope | Integer `1`, excluding booleans. |
| Captured working aggregate and its resolved references | Aggregate `1.0.0`, reference envelope integer `1`; existing typed document validation applies. |
| Raw generated output payloads | Preserve pinned engine containers; do not inject current defaults or reinterpret the untyped generated schematic as the typed document schematic. |
| Missing historical complete-output bundle | Allowed only with no root anchor and no output rows; explicitly `MISSING_OUTPUTS`, never complete. |
| Installed engine/generator differs | Supported frozen envelopes remain readable and are flagged version-incompatible; no implicit regeneration. |

Unsupported/corrupt content returns the redacted 409
`REVISION_OUTPUT_INTEGRITY`; working-document errors use `DOCUMENT_INTEGRITY`.
Asset downloads reject unavailable/corrupt bytes with a redacted 404. SQL,
payloads, credentials and internal paths are not included in these errors.
Hashes detect inconsistency, not malicious rewriting of an entire chain by a
privileged owner; they are not signatures or an external authenticity proof.

## Managed files and read-only audits

Asset keys must be exactly `sha256/aa/bb/<digest>.<supported-format>`, with all
segments agreeing with SHA-256. Reads reject traversal, symlinks, size/hash
mismatches and filesystem failures. Writes flush a temporary file and use atomic
create-if-absent linking; they cannot replace a concurrent or pre-existing shared
file. A corrupt existing file causes failure and is left for investigation.
The local filesystem must support hard links within the asset directory.
Database metadata does not confer permission to overwrite shared content.

From `backend/`, using its existing environment and private database configuration:

```sh
.venv/bin/python -m app.persistence.manage audit-assets
.venv/bin/python -m app.persistence.manage audit-revisions
```

`audit-assets` reports referenced keys, missing/corrupt READY files and unreferenced
files. `audit-revisions` checks all revisions, including tombstoned projects,
reports complete versus legitimate legacy bundles separately, validates working
documents and hashes/envelopes of retained working snapshots. Neither command
updates metadata, regenerates outputs or deletes files. File I/O occurs after
closing revision read transactions. Reports contain counts and
`automatic_deletion: false`; integrity findings produce exit 1. Unreferenced files
and legitimate legacy missing outputs alone do not fail the command. The preserved
illustrative SQL sample revision can be reported invalid; do not suppress it or
rewrite it into valid historical evidence.

Investigate findings against backups, generator pins and retained publication
metadata. Restore exact bytes from a verified backup or publish an explicit new
compatible revision. Do not repair history by replacing its snapshots/digests,
delete shared files, or run migrations/imports as incidental audit steps.
Audits are observational and do not provide a single global point-in-time view
while privileged administrators are concurrently changing data.

Regression evidence lives in `tests/test_revision_integrity.py`, alongside the
existing revision/output/document/package suites. Tamper fixtures use a separate
admin engine restricted to disposable `panel_integration_test_<uuid>` databases;
the runtime guard is never disabled to construct those fixtures.
