# ADR: document, operation and compatibility contracts

P0-T04 · proposed contract · source review 2026-11-13.

## Status, authority and scope

**Proposed for human review; not approved or implemented.** This ADR prepares the
document/operation decision for P0-T06 (D01). Task acceptance does not itself grant
that decision. Current Save, autosave, generation and Restore behavior remains in
force until approval and an explicit compatibility rollout. No new endpoint,
database schema, migration or supported engineering capability is introduced here.

The scope is the existing prototype Distribution Board (DB) modular monolith:
FastAPI, PostgreSQL, React/TypeScript/Zustand, Three.js and Tauri. CEM owns electrical
intent; PDM owns physical arrangement. Calculations, catalog geometry and
thermal/fill limits are prototype assumptions. Publication and validation do not
establish manufacturing or standards certification. Detailed electrical semantics
and applicability are reserved for P0-T07/P0-T08; this ADR cannot approve them.

## Implementation evidence and gap

The [current contract inventory](current-contracts.md) and
[project lifecycle](../PROJECT_LIFECYCLE.md) provide context. The following source
was rechecked; source takes precedence over older architecture/status prose.

| Source | Current behavior and design consequence |
| --- | --- |
| [CEM](../../backend/app/models/cem.py), [requirements](../../backend/app/models/requirements.py) | `CanonicalEngineeringModel` contains requirements, electrical identities, components, nets and connections. Requirement states/source must survive round trips. CEM `revision="1.0.0"` is not the database revision number or a document sequence. |
| [PDM](../../backend/app/models/pdm.py) | `PhysicalComponent.cem_component_id`, `WireRoute.conductor_id`, net/terminal references, enclosure coordinates and `validation_policy` are shared contracts. Some numeric fields reject nonfinite values, but comprehensive finite/reference validation is not enforced by these models alone. |
| [API models](../../backend/app/models/api.py), [TypeScript API](../../frontend/src/types/api.ts), [CEM types](../../frontend/src/types/cem.ts), [PDM types](../../frontend/src/types/pdm.ts) | `ProjectUpdate`, `WorkspaceDocument`, `RecoveryDocument`, `DesignPackage` exist; no working aggregate or operation envelope exists. Broad dictionaries/`any` and differing optional/null fields do not prove schema parity or reference integrity. |
| [ProjectService](../../backend/app/services/project_service.py): `update`, `generate`, `load_revision`, `restore` | Full Save validates inputs/configuration and saves overlays; it creates no revision. Generation computes and publishes together. Reads verify CEM/PDM/manifest hashes, then reconstruct schematic, CAD descriptors and BOM with installed generators (E02). Restore republishes a loaded revision and currently inherits this reconstruction. |
| [Revision writer](../../backend/app/persistence/revisions.py): `write_revision` | Short transaction publishes snapshots/projections/pins/artifact metadata, advances current pointer and project version, and clears workspace/recovery. Only CEM/PDM and the existing manifest enter the revision content hash; a complete frozen output bundle is not yet present. |
| [Project store](../../frontend/src/stores/projectStore.ts): `saveCurrentProject`, `openProject`, `runDesignPipeline`, `recoverChanges` | Save retains edits after conflicts/late responses. Generation replaces overlay drafts. Open loads saved transforms and can call `validateCurrentPlacement`, which requests a nonpersisting reroute through the client. Ordinary open is therefore not currently a pure frozen-output read. |
| [Lifecycle service](../../backend/app/services/project_lifecycle.py), [recovery hook](../../frontend/src/hooks/useProjectRecovery.ts), [display store](../../frontend/src/stores/workspaceStore.ts) | Recovery has independent versions; package v1 contains CEM/PDM history but rebuilds assets on import. Dock preferences persist separately; saved workspace overlays lack their own saved base revision/hash. |
| [Orchestrator](../../backend/app/services/orchestrator.py), [physical routing](../../backend/app/services/physical_routing.py), [assets](../../backend/app/persistence/assets.py) | Placement → DuctRouter → validation is enforced; physical violations, including warnings, fail generation. Nonzero device rotation is unsupported by draft routing. Canonical JSON rejects NaN; assets use verified SHA-256 storage. |

The [architecture assessment](../../ARCHITECTURE_ASSESSMENT.md) recommends the
aggregate/operation boundary. This ADR refines that recommendation without claiming
that the missing guarantees already exist.

## Proposed ownership, IDs and clocks

| Entity | Authority and identity | Version/fence |
| --- | --- | --- |
| Project | Stable database UUID; existing project code remains an alias. Tombstone retains history. One active working document per project initially. | Existing `lock_version` L; require `expected_version` for project-affecting writes. |
| Working document | Mutable, durable engineering aggregate with a stable `document_id`, project/panel IDs, requirements, configuration, CEM/PDM and schematic references, pins, provenance and derived-output status. References resolve to immutable, hashed snapshot values. | `document_sequence` S starts at 0 and increases once per accepted state-changing batch, Save or Recompute installation. It never resets on open, Publish or Restore. |
| Immutable revision | New UUID, project-scoped monotonically increasing `revision_no` N, parent UUID, complete output manifest, source document sequence/hash and provenance. Existing revisions are never edited. | Publish/Restore allocate N+1 under the project lock. Parent is the head immediately before publication, not necessarily the restored source. |
| Display state | Separate local/profile preference document keyed by project/document and optional viewed revision. Selection, visibility, camera, explode, docks, grid and active tool are presentation. | Optional display version is independent of S/L/N; display edits do not invalidate engineering. |
| Recovery | Unfinished local edits/checkpoint of a document and display references, never a revision or automatic operation acceptance. | Retain independent `recovery_version` R and base L/S/revision/hash; server checkpoint write requires expected L/R. |
| Operation/proposal | UUID `operation_id`; atomic batch UUID; stable proposal/job IDs where applicable. Server receipt preserves origin and accepted before/after references. | `base_sequence`, expected L, base revision and target hashes are preconditions, not wall-clock timestamps. |

S versions engineering content, not head-pointer metadata. A document content hash
covers requirements/configuration, model references, pins and engineering provenance;
it excludes L/S, current/base revision pointers, display state and recovery. Publish
may update those pointers under L without changing engineering content or S.

All new entity UUIDs are opaque; logical engineering IDs remain opaque strings
scoped to the project/document lineage. Preserve existing component IDs such as
`QF001`, PDM IDs such as `PDM-QF001`, and terminal/net/connection/route IDs. Never
derive identity from array index, display name, position or current sorting. New
insertions need a persistent allocator; deleted IDs are retained in history and
not reused. Existing selector sequence labels alone do not supply this guarantee.
Relational projection UUIDs can differ per revision; logical stable keys cannot.

Validate uniqueness within each identity namespace and every reference: PDM
component → CEM component; connection → existing endpoint component/terminal and
net; net membership → the same canonical connection; route `conductor_id` → CEM
connection; route endpoints/net → that connection; wire geometry → route; duct
route IDs → routes. Explicit enclosure interfaces such as `PANEL_ROOT` require a
declared terminal registry, not a missing-reference exemption. Schematic symbols,
pins and wire presentation reference electrical IDs; graphical crossings alone
never change connectivity. CAD/BOM selections map back to these IDs.

PDM positions and dimensions use finite enclosure millimetres; rotation uses finite
degrees about the existing Z axis. Retain mounting-plate offsets explicitly;
never apply them twice or substitute camera/world coordinates. GLB metre conversion
stays at the adapter boundary. Length/area/current/voltage/power units are explicit
(`mm`, `mm2`, `A`, `V`, `W`, `kW`); unit conversion cannot be inferred from magnitude.
Dimensions and conductor areas must be positive; permitted zero values and numeric
ranges come from the field schema and pinned policy. Validate nested dictionaries
as well as typed fields. Reject NaN and ±Infinity before hashing or committing.

## Working document and display examples

The named JSON fixtures below are illustrative proposal payloads unless marked
**current**. UUIDs and 64-character digests are synthetic, not existing database
rows or verified content hashes. Snapshot references require server resolution,
ownership, digest and schema checks; their presence alone is not validation proof.
No proposed payload should be sent to today's endpoints.

Each working snapshot reference carries its schema and hash. Requirements retain
their existing state/source/message; input drafts that cannot satisfy engineering
schemas belong in recovery. An editable aggregate can be structurally valid while
downstream outputs are dirty or checks are unresolved. Server-owned catalog
dimensions, pins and validation policy cannot be overwritten by client snapshots.

<!-- fixture: working-document -->
```json
{
  "schema_version": "1.0.0",
  "document_id": "11111111-1111-4111-8111-111111111111",
  "project_id": "22222222-2222-4222-8222-222222222222",
  "panel_id": "PNL-DB-1",
  "archetype": "DB",
  "document_sequence": 25,
  "lock_version": 9,
  "base_revision_id": "33333333-3333-4333-8333-333333333333",
  "requirements": [{"id": "supply_voltage", "label": "Supply voltage", "value": 415, "unit": "V", "state": "CONFIRMED", "source": "USER", "message": null}],
  "configuration": {},
  "models": {
    "cem": {"schema_version": 1, "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
    "pdm": {"schema_version": 1, "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
    "schematic": {"schema_version": 1, "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}
  },
  "pins": {"engine_version": "db-pipeline-4", "generator": {"name": "panelstudio-primitives", "version": "3"}, "catalog_manifest_sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd", "validation_policy_version": "strict-v1"},
  "dirty_stages": ["routes", "physical_validation", "cad"],
  "validation": {"status": "UNRESOLVED", "evaluated_sequence": null, "report_sha256": null, "physical_violation_count": null},
  "provenance": {"last_operation_id": "44444444-4444-4444-8444-444444444444", "origin": "MANUAL"}
}
```

The catalog manifest hash resolves the exact archetype, questionnaire, rule set,
rules, electrical templates, components/products, hardware, enclosure and CAD model
versions already pinned by `ProjectService.generate`. It is not permission to
select “latest”. A missing pin is explicit incompatibility, not a fallback lookup.
`base_revision_id=null` is valid before first publication; null model references
are valid for a new input-only document and prohibit Publish until computed.

<!-- fixture: display-state -->
```json
{
  "schema_version": "1.0.0",
  "document_id": "11111111-1111-4111-8111-111111111111",
  "viewed_revision_id": "33333333-3333-4333-8333-333333333333",
  "selected_ids": ["QF001"],
  "hidden_ids": [],
  "camera_pose": "isometric",
  "exploded": false,
  "grid_mm": 5,
  "docks": {"browser_open": true, "inspector_open": true}
}
```

Stale display references may be marked unavailable or cleared with an explanation;
they must never create engineering objects. Physical moves and schematic symbol
positions are document changes, not display preferences. Electrical connection
edits require CEM operations; presentation cannot become connectivity authority.

## Proposed operation envelope and receipt

Manual tools, automatic algorithms, imports and future AI proposals share one
allowlisted operation boundary. `origin` is one of `MANUAL`, `AUTOMATIC`, `IMPORT`,
`RESTORE`, `COMPATIBILITY`, `AI_PROPOSAL`. It records provenance, not privileges;
server identity/authorization is authoritative. AI proposals remain untrusted and
need explicit user acceptance. Preview resolves base data and validates a candidate
without mutating the working document, head, recovery or operation log.

<!-- fixture: operation-envelope -->
```json
{
  "schema_version": "1.0.0",
  "batch_id": "55555555-5555-4555-8555-555555555555",
  "document_id": "11111111-1111-4111-8111-111111111111",
  "project_id": "22222222-2222-4222-8222-222222222222",
  "base_sequence": 24,
  "expected_version": 8,
  "base_revision_id": "33333333-3333-4333-8333-333333333333",
  "idempotency_key": "manual-move-55555555-5555-4555-8555-555555555555",
  "mode": "APPLY",
  "operations": [{
    "operation_id": "44444444-4444-4444-8444-444444444444",
    "type": "MoveComponent",
    "origin": {"kind": "MANUAL", "actor_id": "local-user", "proposal_id": null, "job_id": null},
    "preconditions": {"cem_component_id": "QF001", "pdm_component_id": "PDM-QF001", "before_position_mm": {"x": 100, "y": 200, "z": 30}, "before_rotation_deg": 0, "validation_policy_version": "strict-v1"},
    "affected_models": ["PDM"],
    "invalidates": ["routes", "physical_validation", "cad"],
    "payload": {"position_mm": {"x": 110, "y": 200, "z": 30}}
  }]
}
```

`MoveComponent` changes only that component's physical position; it does not change
terminal IDs, connectivity, catalog dimensions or electrical ratings. It checks
known hard constraints against server geometry/policy and leaves dependent outputs
dirty; Apply does not reroute. Unsupported rotation fails explicitly; it cannot be
smuggled into this payload. The server registry determines affected models and
invalidation, and rejects mismatched client declarations. Requirement edits
invalidate downstream electrical/physical outputs; schematic presentation edits
invalidate only presentation and its outputs; connectivity edits affect CEM and
all dependent projections. Exact supported operation kinds remain bounded by the
later registry and approved engineering scope, not arbitrary JSON Patch.

All operations in a batch share the captured base; ordered operations run on a
candidate copy, with each operation's target preconditions evaluated against the
state at its execution point. Duplicate operation IDs, unknown fields/types,
missing references, nonfinite values and failed preconditions reject the entire
batch. Return structured errors with operation ID and field/reference, not SQL,
credentials or internal paths. No partial application or silent rebase is allowed.

<!-- fixture: operation-result -->
```json
{
  "batch_id": "55555555-5555-4555-8555-555555555555",
  "status": "APPLIED",
  "base_sequence": 24,
  "document_sequence": 25,
  "lock_version": 9,
  "before_content_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "after_content_sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
  "operation_ids": ["44444444-4444-4444-8444-444444444444"],
  "dirty_stages": ["routes", "physical_validation", "cad"],
  "validation": {"status": "UNRESOLVED", "evaluated_sequence": null, "physical_violation_count": null},
  "revision_id": null
}
```

`APPLIED` means the structurally valid working edit committed, not engineering
PASS. Validation statuses are `PASS`, `FAIL`, `UNRESOLVED`, `NOT_APPLICABLE`;
NOT_APPLICABLE requires a recorded applicability reason/rule. Required applicable
UNRESOLVED cannot aggregate to PASS. Reports bind the exact model/input hashes,
sequence, policy/rule versions and engine. A changed dependency invalidates that
evidence. Detailed required-check aggregation awaits P0-T07/P0-T08; until then no
engineering-release eligibility is inferred from the legacy empty violation list.

For Apply, load immutable base values and close read transactions; validate/compute
outside transactions. In one short transaction recheck L/S/head/target hashes,
commit document plus operation receipts, then increment S and L once. Failure
retains the previous document, head and checkpoints. A 409 version conflict retains
local edits/proposals; resolution is explicit reload/compare/repreview. Responses
must be fenced by project/document/request and submitted sequence so late results
cannot clear newer local changes. Display-only changes never increment L/S.

Persist a unique `(project_id, idempotency_key)` with canonical request digest,
batch/operation IDs and original receipt in the same transaction. Lookup an
existing key before rejecting an old base: same key and same request digest returns
the original result even after sequence advancement; same key with different
content is 409 `IDEMPOTENCY_CONFLICT`. Simultaneous duplicates yield one commit.
Reusing an operation ID in a different batch/key is rejected. Retain receipts for
the document lineage, including tombstones. A retry after a lost response must not
repeat generation, publication or version increments. Failed validation/conflict
does not consume a success receipt; a rebased request needs new IDs/key. Preview
creates no durable receipt or version increment. Apply always revalidates preview
preconditions. Save, Recompute installation, Publish, Restore and explicit conversion
use equivalent request identity/idempotency fences; these are future guarantees,
absent from today's APIs.

## Save, Recompute, Publish, Restore and state transitions

| Action | Proposed preconditions and effects |
| --- | --- |
| Open/view/export saved state | Read stored snapshots/outputs and report compatibility/completeness. No engine, routing, CAD, Save, operation acceptance or publication. Existing last-opened metadata may still be updated without advancing engineering versions. A new empty project remains empty. |
| Save | Validate structural/reference/unit/schema integrity and bounded input rules, persist explicit local changes to the working aggregate under expected L/S/R. Local engineering changes pass through the allowlisted operation boundary; Save cannot bypass it by replacing arbitrary snapshots. A changed Save advances S/L once and clears only the checkpoint covered by expected R; an unchanged Save returns the current receipt without new engineering versions. Dirty stages stay dirty. No computation, rerouting or revision. Already server-applied operations need no second Save; acknowledge their persisted sequence. Unfinished invalid input remains recoverable outside the engineering aggregate. |
| Explicit Recompute | First Save any local changes; capture persisted S/L/input/model hashes/pins, compute declared dirty stages outside transactions and preserve authoritative manual decisions. Placement precedes DuctRouter and strict physical validation. Replacement placement that would discard manual work needs a separately reviewed proposal. On successful fence recheck, atomically install one result at S+1/L+1 and persist its validation evidence. No N/head change. Failed checks or stale results install nothing; keep dirty state and prior outputs labelled by their old hashes/sequence. |
| Publish | Require explicit user action, expected L/S/head/R, a complete compatible bundle, no dirty stages, and current validation evidence. Require zero physical violations including warnings and no unresolved applicable required checks. Snapshot the already recomputed state; no hidden computation. Allocate N+1/new UUID, advance L, head and document base reference atomically; S stays fixed because document content is unchanged. Clear only fenced recovery. Failure preserves previous head and document. |
| Restore | Require expected L/S/head/R and explicit save/discard resolution for local edits/recovery. Verify source bundle/hashes and schema compatibility; publish a new revision copied from that source, with `restored_from_revision_id` and pre-restore head as parent. Advance N/L and working S once, rebase working document to restored state, reset dependent editor baselines and clear fenced recovery. No recomputation, historical overwrite or invented engineering PASS. Incomplete/incompatible sources require explicit conversion first. |

Recompute's frozen input result may run asynchronously later; cancellation/stale
completion cannot install it. Stage scheduling, jobs and endpoint design belong to
later tasks. Publication snapshots include the exact working content and do not
read “latest” catalog rows. Existing artifact downloads remain bound to their
revision. Working preview downloads, if later exposed, must be labelled with
document sequence/hash and cannot masquerade as a published export.

Recompute reports retain their captured input sequence and bind evaluated output
hashes to the installed sequence (26 in the manifest example). Restore retains the
original report and its original evaluated sequence; a restoration receipt binds
that evidence to the identical restored input/model hashes at the new S. It must
not relabel the original report as a newly executed check. If applicability or pins
are incompatible, conversion/revalidation is required before restoring as valid.

These states are independent, not one overloaded `is_stale` flag:

| State | Meaning and example | Allowed resolution |
| --- | --- | --- |
| Unsaved/dirty local edits | Client differs from persisted S; recovery alone does not Save. | Save or explicit recover/discard; retain after conflicts. |
| Dirty stages | Dependencies changed since an output was computed; can be durably saved with no unsaved edits. Example: saved move with obsolete routes. | Explicit Recompute; Publish blocked. |
| Input-stale revision | Frozen revision input hash differs from current working requirements/configuration/engineering inputs. | View/export frozen revision with label; recompute and publish explicitly for current inputs. |
| Non-current revision | Viewed UUID differs from project head; its own complete outputs may be internally consistent. | View/export or explicit Restore; never regenerate merely because it is old. |
| Version drift | Installed engine/generator differs from pinned producer. | Read compatible frozen outputs; explicit conversion for editing/recomputation if producer unavailable. Drift alone does not corrupt a snapshot or prove its engineering validity. |
| Incompatible schema/pins | No approved reader/adapter or required immutable version is unavailable. | Read supported portions or preserve opaque originals; block affected edits/compute/publication. |
| Missing/corrupt output | Snapshot/artifact absent or failed integrity verification. | Report separately from dirty/non-current; preserve evidence and use explicit conversion or recovery. Never pass empty output as success. |

An unchanged historical revision does not become current when opened. A clean Save
does not make stale output fresh. Engine version drift is neither document sequence
nor evidence of changed bytes. `validation.status`, integrity, completeness and
prototype applicability are separately reported.

## Frozen revision bundle and compatibility

A new-format published bundle includes requirements/configuration, CEM, PDM,
typed schematic presentation, BOM, CAD descriptors, full validation report, pins,
operation/provenance references and artifact hashes/sizes/producer versions.
Schema versions are separate for aggregate, CEM, PDM, schematic, output manifest,
operation envelope and package. Saved `validation_policy` is authoritative for both
backend and frontend analysis. Do not fill missing historical policy with today's
defaults and claim that it was the policy originally used.

<!-- fixture: revision-manifest -->
```json
{
  "schema_version": "1.0.0",
  "revision_id": "66666666-6666-4666-8666-666666666666",
  "revision_no": 4,
  "parent_revision_id": "33333333-3333-4333-8333-333333333333",
  "source_document_id": "11111111-1111-4111-8111-111111111111",
  "source_document_sequence": 26,
  "restored_from_revision_id": null,
  "completeness": "COMPLETE",
  "outputs": {
    "cem": {"schema_version": 1, "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
    "pdm": {"schema_version": 1, "sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"},
    "schematic": {"schema_version": 1, "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"},
    "bom": {"schema_version": 1, "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
    "cad": {"schema_version": 1, "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
    "validation": {"schema_version": 1, "sha256": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"},
    "inputs_and_pins": {"schema_version": 1, "sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"}
  },
  "artifacts": [],
  "publication_profile": "prototype-db",
  "validation": {"status": "PASS", "evaluated_sequence": 26, "physical_violation_count": 0}
}
```

This manifest shape omits the external root digest to avoid self-reference. Hash
each stored canonical JSON output using the existing canonicalization (sorted
keys, compact UTF-8, nonfinite numbers rejected), hash artifact bytes separately,
then hash the canonical manifest including their digests, identities, schema
versions, pins and provenance. Store/verify the root separately. Synthetic repeated
digests above illustrate shape only. `artifacts=[]` represents no requested optional
file formats; required formats declared by the publication profile must be READY
and verified or Publish fails. COMPLETE concerns declared output availability,
not native FreeCAD/STEP execution or certification. Post-publication export jobs
may append artifact records bound to the root/model hash; they never rewrite the
frozen manifest. Requested native outputs require their own verified producer.

| Compatibility case | Proposed rule |
| --- | --- |
| Exact supported schema and intact complete bundle | Return stored values/bytes without generators. Check integrity before parsing or adaptation. |
| Additive minor aggregate/envelope change | Optional fields need documented defaults that do not alter engineering meaning. Writer negotiates capabilities; unknown operation fields/types fail. An older reader may present supported fields read-only and retain opaque bytes; it must not round-trip-drop unknown fields. |
| Breaking major, unit/identity meaning change, or unsupported nested schema | Fail affected edit/write with structured compatibility details and supported versions. Preserve originals and expose compatible outputs read-only. No best-effort coercion or default-current policy. |
| Supported old schema with deterministic adapter | Adapt in memory for presentation without changing stored bytes/hashes. Record adapter identity and distinguish adapted representation from original. Persist only through explicit conversion to a new working document/revision. |
| Installed engine/generator unavailable or newer | Frozen complete outputs remain readable/exportable if their schemas are supported. Recompute needs exact available pins or an explicit reviewed repinning/conversion proposal. |
| Hash failure | Mark integrity FAIL and block use of the affected representation. Preserve original evidence; never repair with a generator during read. |

Current integer snapshot `schema_version=1`, CEM `revision`, engine version,
generator version, project package literal `version=1` and proposed aggregate
SemVer are independent namespaces. A future compatibility registry must map each
explicitly; this ADR does not reinterpret an old integer as a new aggregate.
Schema adapters, Pydantic/OpenAPI models and TypeScript types/fixtures must be
updated together. Format/schema compatibility does not establish electrical
applicability. Import/duplication allocate new project/revision identities with an
explicit mapping of scoped references, retain source provenance and verify source
digests before rebinding; recompute destination digests for new immutable records.
Project packages remain distinct from database/catalog backups.

## Legacy missing outputs and overlay migration

Opening a legacy revision verifies and serves the original CEM/PDM and any intact
stored assets. It reports absent schematic/BOM/CAD/validation snapshots explicitly.
It never silently reconstructs them, reroutes saved overlays, upgrades schemas,
rewrites hashes or creates a revision. Missing originals cannot be certified as
byte-identical by regenerating them with a matching version label.

<!-- fixture: legacy-status -->
```json
{
  "revision_id": "33333333-3333-4333-8333-333333333333",
  "compatibility": "LEGACY_PARTIAL",
  "integrity": "PASS_FOR_PRESENT_OUTPUTS",
  "missing_outputs": ["schematic", "bom", "cad", "validation"],
  "validation_status": "UNRESOLVED",
  "can_read_original_models": true,
  "can_publish_unchanged": false,
  "conversion_required": true
}
```

Explicit **Create compatibility proposal** copies supported originals into a new
candidate, identifies missing outputs, adapters and proposed pins, and shows a
diff with producer changes. It does not mutate source or head. On user acceptance,
install the candidate under L/S/R fences with COMPATIBILITY provenance, then
explicitly Recompute missing/invalidated outputs and Publish a new revision. New
outputs are labelled generated during conversion with source revision ID/hash,
adapter/engine/generator versions and unavailable historical evidence. They are
never backfilled into the source manifest. Cancellation/failure leaves originals,
workspace/checkpoints, head and shared assets intact.

Legacy overlay conversion follows the same proposal process:

1. Preserve raw `workspace`, browser/server recovery, source revision/pin/hash
   evidence and the conversion mapping. Do not delete or overwrite it on open.
2. Establish the overlay base. Recovery `baseRevisionId` is useful but insufficient
   without matching IDs, versions/geometry and coordinate frame. Saved workspace
   has no base field today; do not infer a proven base from the current head.
   Missing/ambiguous base requires explicit user selection and review; retain the
   overlay as recoverable legacy data if no safe base can be established.
3. Match CEM/PDM/terminal IDs and pinned geometry/policy. Convert absolute enclosure
   mm transforms into proposed MoveComponent/allowed RotateComponent operations
   with captured before values. Unknown IDs, changed dimensions, unsupported
   nonzero rotations or nonfinite positions produce itemized blocked entries,
   never silent deletion, snapping, remapping or changed constraints.
4. Convert known schematic symbol/pin/wire presentation with stable references.
   Graphical edges/junctions that imply connectivity changes remain unresolved
   proposals requiring approved CEM operations and engineering checks. Unsupported
   legacy fields stay in the preserved source, not an invented valid schematic.
5. Show all accepted/blocked items and impact; require explicit user acceptance.
   Apply an accepted valid batch atomically to working state under fresh fences;
   leave routes/CAD/validation dirty. Partial selection requires a new visible
   proposal, not partial batch success. Recompute and Publish remain separate.

Retain existing Recover/Discard UX and independent R. A different base must never
apply overlay geometry automatically. Legacy originals stay available until an
explicit archive/discard choice after successful conversion; migration does not
authorize asset deletion or historical mutation.

## Current Save compatibility and decision required

Until D01 approval and implementation rollout, **retain today's Save**. The
following is a current `ProjectUpdate` example, not the proposed aggregate Save.

<!-- fixture: current-save -->
```json
{
  "expected_version": 8,
  "expected_recovery_version": 2,
  "requirements": {"supply_voltage": 415},
  "configuration": {},
  "workspace": {
    "editorTransforms": {"QF001": {"x": 110, "y": 200, "z": 30, "rotation_deg": 0}},
    "schematicData": null
  }
}
```

<!-- fixture: current-recovery -->
```json
{
  "expected_version": 8,
  "expected_recovery_version": 2,
  "document": {
    "requirements": {"supply_voltage": 415},
    "configuration": {},
    "workspace": {"editorTransforms": {}, "schematicData": null},
    "baseRevisionId": "33333333-3333-4333-8333-333333333333"
  }
}
```

Current full Save advances L/R, clears recovery, retains the engineering revision
and does not make transforms authoritative. Current requirement validation may
reject unfinished inputs; recovery is the checkpoint path. Metadata-only PATCH
has separate effects. Existing frontend edit-sequence/request guards retain newer
local edits. Existing generation still recomputes and publishes together and clears
overlays; this ADR does not rename it Recompute or change current counters.

Recommended rollout after approval: add versioned aggregate/operation contracts
and additive storage; preserve old records/endpoints; introduce complete output
publication and generator-free readers; expose capability/schema negotiation;
offer explicit legacy proposals; move UI tools to operations and separate actions.
Route old Save to its old semantics, or return a clear unsupported-mode response
when a document cannot be represented safely; never silently reinterpret its
workspace as engineering. Coordinate all read/export/restore/import/duplicate/job
consumers of `load_revision`, and replace open-triggered preview rerouting with an
explicit action. Do not create a second competing working-state writer.

D01 review should accept/revise Save versus Apply persistence, S/L/R transitions,
separate Recompute/Publish UX, frozen outputs, legacy conversion and bounded
operation scope. Record the human decision through the existing lifecycle process;
this ADR and its author supply no signature or approval. Alternatives considered:
retain overlay-only authority (manual export mismatch persists), make Save
regenerate (breaks current recovery/Save expectations), or mutate revisions in
place (destroys immutable history). The proposed aggregate preserves those
boundaries at the cost of explicit compatibility states and more version fences.

## Verification and future implementation obligations

This is a design document. The [attempt report](../../planning/task_reports/P0-T04/attempt-01.md)
records actual commands and results. Documentation fixture checks can establish
payload syntax, current Pydantic/OpenAPI acceptance, TypeScript shape consistency
and proposal invariants; they cannot establish unimplemented runtime behavior.
Synthetic references/hashes do not prove database resolution, physical validity
or historical byte fidelity.

Required later regression scenarios: Save/open call no generators/router and create
no revision; raising generator sentinels cannot affect complete historical reads;
legacy open preserves hashes and reports missing outputs; conversion preserves
originals even on failure; two writers from one base yield one success/conflict;
same-key retries after lost response yield one receipt/revision; same-key changed content
conflicts; stale Recompute installs nothing; Publish rejects dirty/missing/warning
and unresolved required checks; Restore creates one new revision with unchanged
source bytes; fixtures reject orphan IDs, nonfinite nested units and unsupported
schemas; frontend preserves local edits on conflicts/late responses. PostgreSQL,
browser, native CAD and engineering review remain separate verification evidence.
