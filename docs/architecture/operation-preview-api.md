# Operation preview API

P2-T01 introduces `POST /api/v1/projects/{project_id}/document/operations/preview`.
It loads the server's verified working document through `DocumentService.load`,
closes that read transaction, and evaluates the request on a detached copy.
There is no apply endpoint, receipt, Save, recomputation, publication or approval.
Existing Save and legacy editing flows retain their semantics.

## Request boundary

`OperationPreviewRequest` requires batch UUID, document ID, `base_sequence`,
`expected_version`, explicit nullable `base_revision_id` and 1–100 operations.
All four base fences must match. Each operation requires a unique operation UUID,
origin, typed target and parameters, and a snapshot SHA-256 precondition evaluated
at that operation's execution point. Repeated edits to the same model must use the
previous candidate snapshot hash. No silent rebase or partial result is returned.
An opaque logical target ID must be nonempty, without surrounding whitespace or
control characters; unknown targets are rejected separately from malformed IDs.

The immutable registry currently permits two preview operations:

| Type | Target and parameters | Affected model | Newly dirty stages | Required unresolved checks |
| --- | --- | --- | --- | --- |
| `MoveComponent` | Matching PDM/CEM component IDs; finite `position_mm` x/y/z | `pdm` | routes, physical_validation, cad | physical_constraints, routing, physical_validation |
| `UpdateRequirement` | Existing requirement ID; scalar or null `value` | requirements | all stages | requirement_rules |

Optional `affected_models` defaults to the registry declaration; a supplied value
must match exactly. Unknown fields, operations, arbitrary snapshots, rotations,
nonfinite coordinates and duplicate operation IDs fail request validation.
Movement of an already rotated component is rejected. Movement translates absolute
physical terminal coordinates along with the component, preserving identities and
mounting-plate offsets. Routes and other derived values are retained as dirty;
the candidate is not a rerouted or physically validated design.

Requirement previews retain ID, label and unit, replace the value and set state
to PROPOSED, source to USER and message to null. They clear prior requirement
validation claims. This boundary accepts scalar draft values; questionnaire rules,
numeric ranges, applicability and downstream engineering remain unresolved.
Structured requirement values, insertion and unit changes are unsupported.

Origin records the caller's provenance claim, not authorization. AI or other
proposal origins require `proposal_id` and `proposal_status: PROPOSED`. Preview
accepts only NOT_PROPOSED or PROPOSED status and never records human acceptance.

## Response and errors

The response has `status: PREVIEW`, `persisted: false`, unchanged base sequence,
before/after content hashes, typed per-operation changes with target IDs and
snapshot hashes, required checks, dirty stages and a resolved candidate. Changed
fields are explicit; before values are available in the loaded base and after
values in the candidate. Content hashes use the existing document hash convention;
snapshot hashes use fully defaulted canonical model JSON. Pins, sequence, lock,
revision pointers and provenance remain unchanged. No timestamps or random IDs
are generated, so identical pinned inputs and requests produce identical results.
No-ops produce no change or newly required check, retaining existing dirty stages.

Base conflicts and snapshot precondition mismatches return structured 409
`DOCUMENT_CONFLICT` / `OPERATION_PRECONDITION`. Unknown or mismatched target IDs,
unsupported existing rotation and missing terminal geometry return structured
422 design errors. Malformed requests return FastAPI's 422 validation details.
Missing, corrupt or uninitialized documents use the existing document error path.
Even a successful response makes no engineering PASS claim. A future apply service
must revalidate, enforce constraints and fence its own durable transaction.

Backend contracts live in `app/models/operations.py`; frontend interfaces and the
shared JSON request fixture live in `frontend/src/types/operations.ts` and
`frontend/src/types/fixtures/operation-preview-v1.json`. The backend validates the
fixture with Pydantic; Vitest compares a TypeScript-checked request to that fixture.
