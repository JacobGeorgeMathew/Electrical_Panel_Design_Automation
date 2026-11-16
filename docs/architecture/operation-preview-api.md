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

The immutable registry permits these draft operations (P2-T03/P2-T04 extend the original preview contract):

| Type | Target and parameters | Affected model | Newly dirty stages | Required unresolved checks |
| --- | --- | --- | --- | --- |
| `MoveComponent` | Matching PDM/CEM component IDs; finite `position_mm` x/y/z | `pdm` | routes, physical_validation, cad | physical_constraints, routing, physical_validation |
| `RotateComponent` | Matching PDM/CEM component IDs; finite absolute Z `rotation_deg`; only zero supported | `pdm` | routes, physical_validation, cad (no-op adds none) | physical_constraints, routing, physical_validation (no-op adds none) |
| `UpdateRequirement` | Existing requirement ID; scalar or null `value` | requirements | all stages | requirement_rules |
| `ChangeComponentRating` | Existing `cem_component_id`; exact `catalog_id`, `component_version_id`, `current_rating` | cem | calculations, selection, connectivity, schematic, placement, routes, physical_validation, bom, cad | requirement_rules, physical_constraints, routing, physical_validation |
| `ResizeEnclosure` | Current `enclosure_id`; exact replacement `catalog_id`, `component_version_id`, `width`, `height`, `depth` in mm | pdm | placement, routes, physical_validation, bom, cad | physical_constraints, routing, physical_validation |

Optional `affected_models` defaults to the registry declaration; a supplied value
must match exactly. Unknown fields, operations, arbitrary snapshots, rotation fields on moves,
nonfinite coordinates and duplicate operation IDs fail request validation.
Any nonzero rotation in the layout blocks physical edits. `RotateComponent`
rejects every nonzero requested angle, including full turns and tiny angles,
without normalization. Zero on a zero-rotation layout is a validated no-op;
resetting an imported rotated layout is unsupported until P4-T10 supplies shared
oriented geometry and terminal/obstacle transforms.

Movement translates absolute physical terminal coordinates along with the
component, preserving identities and
mounting-plate offsets. Routes and other derived values are retained as dirty;
the candidate is not a rerouted or physically validated design. Coordinates are
absolute enclosure millimetres, so mounting offsets are not added a second time.
Dimensions, clearance policy and mounting-plate extents come from the saved server
PDM; the request cannot override them. The physical handler checks positive finite
dimensions and uses `ValidationEngine` on a detached placement-only copy to enforce
backplate and enclosure bounds, cabinet depth, overlaps, saved-policy clearances,
duct/device collisions and prototype thermal density. Any returned violation rejects the edit,
including a no-op on an invalid placement. This does not add mounting/oriented-solid
checks reserved for P4 or establish route validity. Obsolete routes are excluded
only from this placement check and retained unchanged in the dirty draft. Thermal
and validation metadata are not refreshed by Apply. Explicit Recompute must resolve
the dirty outputs and outstanding checks before publication; no routing, CAD,
optimization or publication runs during preview, batch commit or Save. Separate
Recompute/Publish service implementation remains outside P2-T04.

Requirement edits retain ID, label and unit, replace the value and set state
to PROPOSED, source to USER for manual edits (otherwise the operation origin),
and message to null. Other requirements retain their provenance. Before snapshots
and immutable operation members retain previous values and sources. Unknown keys,
invalid types/options/ranges and inapplicable fields fail against the server's
pinned questionnaire and available DB choices. A partial draft can retain other
missing requirements; this field check does not claim whole-design validity.
Changes clear prior requirement validation claims. Structured values, insertion
and unit changes are unsupported. An equal value is a no-op.

Catalog substitutions use exact published component versions loaded by the server,
never client-supplied records or JSON runtime fallback. Ratings must match the
requested catalog rating exactly and preserve category, poles, mounting and terminal
IDs without reducing breaking capacity. Catalog-owned component fields change;
logical component ID and quantity remain. Physical and schematic projections are
retained as dirty. Enclosure dimensions must match the selected published enclosure;
only its identity, dimensions, IP rating and plate offsets change. Zones, placement
and routes remain stale pending explicit recomputation. Catalog version IDs are
retained in operation payloads/history; generated base pins remain unchanged.
No published catalog/version records are created or modified.

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
unsupported rotation, missing terminal geometry and known physical constraint failures return structured
422 design errors. Malformed requests return FastAPI's 422 validation details.
Missing, corrupt or uninitialized documents use the existing document error path.
Physical failures use `OPERATION_PHYSICAL_CONSTRAINT` with operation ID and
structured violations. Even a successful response makes no whole-design PASS claim.
The internal batch repository reuses these handlers and fences its durable transaction.

Backend contracts live in `app/models/operations.py`; frontend interfaces and the
shared JSON request fixture live in `frontend/src/types/operations.ts` and
`frontend/src/types/fixtures/operation-preview-v1.json`. The backend validates the
fixture with Pydantic; Vitest compares a TypeScript-checked request to that fixture.
