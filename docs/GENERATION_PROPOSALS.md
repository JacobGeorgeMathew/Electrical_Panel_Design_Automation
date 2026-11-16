# Automatic generation proposals

The working-document adapter wraps the existing deterministic DB pipeline. It
uses saved working requirements and enclosure configuration, closes database read
sessions before optimization and returns a proposed aggregate delta. It never
publishes a revision or writes generated artifact files.

1. `POST /api/projects/{id}/design/generation-proposal` accepts a requirements
   override dictionary. A `REVIEW_REQUIRED` response contains `batch` and
   `preview`: changes, before/after hashes and a detached resolved candidate.
   A `CONFLICT` response contains target/reason entries and no applicable batch.
2. Review the candidate and conflicts. Preview does not imply acceptance.
3. Explicitly accept by posting the returned batch to
   `/api/projects/{id}/design/generation-proposal/accept` with `Idempotency-Key`.
   The server uses the exact retained candidate and checks the reviewed digest
   and request. Clients cannot supply output snapshots. An ordinary operation
   commit rejects the proposed batch.
4. Acceptance writes one working-document operation batch. Shared document ID,
   sequence, project lock, revision-base and per-model snapshot preconditions apply.
   The writer rechecks the base under the project row lock. Failures roll back all
   snapshots/history/state writes. Exact idempotent retries return the saved receipt.
5. Undo/redo uses the existing operation history endpoints. Acceptance changes no
   published revision; publication and artifact export remain separate workflows.

Review candidates are bounded process-local state: at most 32 per database,
retained for 15 minutes. Expiry, eviction or server restart requires a new preview;
accepted receipts remain durable and replayable. Retaining exact candidates avoids
rerunning a solver whose wall-clock cutoff can select a different feasible result.

Matching CEM component/terminal/net/conductor identities come from the bounded DB
pipeline. Matching PDM component and schematic symbol/pin/wire IDs are retained;
document/project/panel ownership is rebound to the working document. No fuzzy
identity match or general panel archetype inference is performed.

`WorkingDocument.generation_intent` retains `manual_models` and CEM IDs in
`locked_placements`. The optional field is omitted when absent to preserve old
canonical hashes. Changed manual engineering operations record protected models;
physical moves also record placement locks. Ordinary Save preserves this metadata.
Generation returns a conflict if a protected model changes, or a locked component
is removed, moved, resized or assigned another rail/zone. Protection is conservative:
an edited model can block generation even when only derived fields differ. Undo
can restore the previous intent; this adapter provides no force-overwrite switch.
Older/imported engineering snapshots without intent metadata are conservatively
protected against replacement as well.

The legacy immediate-publication generation endpoints remain compatible for
projects with an untouched, input-only working document. Once a document has been
edited or contains CEM/intent metadata, they fail with
`GENERATION_PROPOSAL_REQUIRED`; they cannot overwrite authoritative working edits.
The new API helpers are available to document consumers; the legacy workspace UI
is not converted into a proposal-review UI by this backend task.

The pipeline retains its zero-physical-violation requirement, including warnings.
The adapter does not establish manufacturing or standards compliance, or verify
native FreeCAD/STEP execution. CAD artifacts remain dirty until separate output
preparation/publication.
