# Atomic operation batch persistence

P2-T02 adds migration `0006_operations` and the internal
`OperationBatchRepository(database).commit(project_key, request, idempotency_key)`
boundary. `request` is the existing `OperationPreviewRequest`. There is no new HTTP
apply endpoint or frontend mutation flow. The preview API remains read-only.

## Transaction boundary

The repository loads a verified working document and closes the read session.
It evaluates the allowlisted members in order on detached candidates, validates
identities, finite values, snapshot hashes and references, and retains intermediate
model states. These are structurally validated drafts: requirement rules, physical
constraints, routing and validation remain unresolved as reported by the existing
registry. The writer adds no engineering PASS claim and invokes no optimization,
routing, CAD generation, revision publication or asset writes.

One short write transaction locks the active project, checks for an existing retry
receipt, then rechecks project lock version, document ID, sequence, base revision
and content hash. It writes the batch, referenced intermediate snapshots, ordered
operation members and the document/version update together. A constraint failure
at any member rolls everything back, including the receipt and counters. A
concurrent edit invalidates preparation; the writer never rebases automatically.
Database constraint errors become a sanitized `OPERATION_STORAGE_CONFLICT`.

Every member receives a monotonically increasing project-scoped operation
`sequence`, including no-ops. Member identity is unique per project; `batch_index`
preserves request order. Each member stores its complete normalized payload,
SHA-256, origin, and before/after snapshot references. Composite foreign keys
enforce document ownership and retained snapshot resolution. A state-changing
batch increments document sequence and project lock version once; an entirely
unchanged batch records a receipt without advancing either counter. Mixed or
reversing edits still record their ordered transitions and advance once.

The document provenance records the last state-changing member. Existing revision
head, immutable revisions, assets, display/workspace and independent recovery
state remain intact. Unaccepted `PROPOSED` operations are rejected: this storage
boundary cannot supply human acceptance. Authoritative physical and engineering
operation rules and any explicit acceptance workflow require their own tasks.

## Retry identity and result

The opaque idempotency key is 1–200 characters, without surrounding whitespace or
control characters. Its uniqueness scope is the project's database UUID, including
requests made through a project-code alias. Different projects may use the same
key. Batch UUID and member UUID reuse within a project is rejected by constraints.

The batch hash covers the complete Pydantic-normalized request, including defaults,
schema, base fences, batch ID, ordered member IDs, provenance and parameters.
Key order and omitted defaults do not change canonical content. A retry must
retain that content; changed content returns `IDEMPOTENCY_CONFLICT`, including
after the original document version is obsolete.

The append-only batch stores the complete JSON result and its digest, including
the committed resolved `DocumentView`, version counters, operation sequence range,
required unresolved checks and before/after content hashes. Retry checks occur
before candidate evaluation and again under the project lock; an additional read
handles a concurrent commit between the initial project and document reads. Replay
verifies stored payload/result digests and returns the original result verbatim,
even after subsequent edits or repository restart. It does not reload current
state as the prior result. Concurrent identical retries share one receipt; distinct
same-base batches produce one state-changing winner and a conflict.

## Migration and verification

`0006_operations` creates two tables without rewriting pre-existing rows. Runtime
readiness requires that head. Generated mappings come from
`tools.build_schema_models`, which uses its own disposable schema-build database;
the frozen baseline manifest is unchanged. Application publication guards make
both tables append-only. Deployment roles still need the existing independent
database authorization controls described in
[revision integrity](../database/REVISION_INTEGRITY.md).

`backend/tests/test_operation_persistence.py` covers validation failure, a late
database member failure, retained intermediate hashes, exact retries after later
edits, key conflicts, competing transactions, no-ops, migration from `0005`,
ownership and immutable history. PostgreSQL cases use only fixture-owned
`panel_integration_test_<uuid>` databases. Actual command outcomes are recorded
in the [task attempt report](../../planning/task_reports/P2-T02/attempt-01.md).
