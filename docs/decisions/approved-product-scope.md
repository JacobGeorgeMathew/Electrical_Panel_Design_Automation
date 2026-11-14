# D01 — Product scope, document semantics and deployment boundary

P0-T06 · architecture_lead · prepared 2026-11-14.

**Status: APPROVED — JacobGM, product owner and human technical lead, 2026-11-14.**
JacobGM explicitly approved choices A–H and confirmed both human roles in the
conversation recorded below. This approves the bounded product direction and
document semantics; it does not authorize executing later tasks, exposing a
service, redistributing a kernel or claiming engineering qualification. Lifecycle
task acceptance remains owned by the normal human decision process.

## Decision sheet

All rows were selected as proposed in explicit user replies on 2026-11-14;
JacobGM subsequently confirmed the product-owner and human technical-lead roles.
Silence, prerequisite acceptance and agent-authored text are not approval. Later
amendments must identify the affected row and replacement.

| ID | Recommended choice | Human decision |
| --- | --- | --- |
| A — Release scope | DB-only, document-centric prototype MVP through P3; P4–P7 remain the recommended later release, P8 deferred. Unqualified native STEP is excluded from the MVP. | User approved A–D as proposed |
| B — Document UX | Separate Save, explicit Recompute and explicit Publish; retain recover/discard and immutable Restore; approve the proposed semantics below and the linked P0-T04 ADR. | User approved A–D as proposed |
| C — Legacy strategy | Preserve originals; show missing outputs; require reviewed compatibility/overlay proposals and new revisions. No regeneration on ordinary open after rollout. | User approved A–D as proposed |
| D — Architecture | Retain modular monolith, PostgreSQL and managed assets, React/Zustand/Three.js and existing editors; add custom typed operations and an isolated geometry worker. | User approved A–D as proposed |
| E — Deployment | Local desktop, one local user/session boundary, loopback backend and local PostgreSQL provisioned separately. Hosted multi-user exposure deferred. | User approved E–G as proposed |
| F — Platforms | Initial pilot support target: Linux x86_64 on the measured Arch host; Windows x86_64, macOS and ARM deferred. No installer or OS is yet release-qualified by this decision. | User approved E–G as proposed |
| G — Size and performance | Adopt the two reference workloads and proposed hardware/measurement budgets below; larger workloads require separate evidence and approval. | User approved E–G as proposed |
| H — Kernel and distribution | Conditional pinned headless FreeCAD subprocess path; defer kernel redistribution now. Keep P5-T00 qualification and P7-T03 distribution approval mandatory. | User approved H; redistribution deferred |

Alternative E: hosted multi-user deployment requires a separately scoped and
approved identity/authorization backlog **before hosted exposure**, with a named
owner, approval evidence and release-blocking acceptance checks. Local-session
protection does not cover it. Alternative F: identify the exact OS/version and
CPU architecture to add, with packaging, WebGL, database and native-worker checks
and effort reviewed before promising support. Alternative H: requesting kernel
redistribution now also requires the distribution/license owner's explicit review
of the exact artifact and approach; product approval alone cannot clear it.

## Evidence and present implementation

Reviewed [architecture assessment](../../ARCHITECTURE_ASSESSMENT.md),
[project lifecycle](../PROJECT_LIFECYCLE.md),
[P0-T04 ADR](../architecture/document-operation-adr.md),
[P0-T03 baseline](../verification/performance-baseline.md) and
[P0-T05 evaluation](../architecture/geometry-kernel-evaluation.md).
The prerequisite reports are [P0-T03](../../planning/task_reports/P0-T03/attempt-01.md),
[P0-T04](../../planning/task_reports/P0-T04/attempt-01.md) and
[P0-T05 attempt 03](../../planning/task_reports/P0-T05/attempt-03.md), which retains
the earlier negative native findings. Prerequisite verification is not D01 approval.

| Source checked | Current implementation and decision consequence |
| --- | --- |
| [ProjectService](../../backend/app/services/project_service.py), `validate`, `update`, `generate`, `load_revision`, `restore` | DB-only runtime. Save writes requirements/configuration/workspace without a revision. Generate computes and publishes together. Reads verify saved CEM/PDM hashes but reconstruct schematic/CAD/BOM with installed generators. Restore uses that reader. Generator-free complete historical reads and separate Recompute/Publish are future work. |
| [Project store](../../frontend/src/stores/projectStore.ts), `openProject`, `saveCurrentProject`, `runDesignPipeline` | Saves overlays; generation replaces them with generated state. Opening saved transforms may invoke a preview reroute. Draft placement and schematic changes are not authoritative published CEM/PDM edits. |
| [Revision writer](../../backend/app/persistence/revisions.py), [orchestrator](../../backend/app/services/orchestrator.py) | Short transactional publication and stable logical references exist. Placement → DuctRouter → validation is enforced; any physical violation fails generation. Complete frozen output bundles remain proposed. |
| [Dependencies](../../backend/app/api/dependencies.py), [settings](../../backend/app/persistence/config.py) | HTTP runtime requires PostgreSQL; there is no JSON runtime fallback. Assets use managed storage outside the source tree. PostgreSQL configuration is separate from the desktop binary. |
| [Desktop entry](../../backend/desktop_main.py), [Tauri wrapper](../../frontend/src-tauri/src/lib.rs), [configuration](../../frontend/src-tauri/tauri.conf.json) | Release wrapper launches `panel-backend` on loopback port 8731 and manages its lifetime; development starts the backend separately. `targets: all` is not cross-platform qualification. Only the backend sidecar is declared, with no kernel bundle. |
| [Application](../../backend/app/main.py), [API dependencies](../../backend/app/api/dependencies.py) | CORS allowlist and database/service wiring exist; no authenticated per-user/project authorization boundary is established here. Current CAD queue uses one in-process thread, not the recommended isolated native worker. |
| [CAD engine](../../backend/app/services/cad_engine.py), [CAD routes](../../backend/app/api/routes_cad.py) | Backend produces descriptors, GLB and Python script text; it does not execute a qualified native STEP service. A script ending in STEP export is not a verified STEP deliverable. |

## Approved product and model boundary

The first release delivers a bounded prototype DB document workflow: create/open,
requirements and enclosure input, constrained manual physical/schematic editing,
explicit recomputation, Save/reopen/recovery, immutable publication/history and
exports matching the chosen saved revision. Existing GLB and script outputs keep
their preview/unqualified labels. MVP completion requires the applicable P1–P3
verification; D01 is scope approval only. P4 engineering methods, P5 exact CAD,
P6 structured AI and P7 hardening remain separately gated later scope.

CEM owns electrical intent, components, terminals, connections and nets. PDM owns
physical arrangement, enclosure-mm geometry, structures and routes. Schematic
presentation cannot change connectivity without a permitted CEM operation. CAD
and BOM derive from the authoritative models. Preserve stable component,
terminal, net, connection and route IDs, mounting-plate transforms, immutable
catalog/model pins and saved `validation_policy` across every projection.

Use a working document as the transaction boundary, with independent display and
recovery state. Preserve project `lock_version`/`expected_version`, independent
recovery version and future document sequence/hash fences. Custom allowlisted
typed operations validate references, units, hard constraints and preconditions;
manual tools, algorithms and later accepted AI proposals share this boundary.
Use atomic batches, idempotent receipts and explicit conflict resolution. Failed
or stale work retains local edits, recovery and the prior published revision.

Keep one backend codebase and PostgreSQL database with explicit service/stage
interfaces. Retain existing editors and improve their authority and contracts.
Isolate native computation in a separate supervised process with bounded inputs,
resources, cancellation and output verification; do not load a kernel ABI into
the API process. Close read transactions before computation; publish through the
existing short writer and content-addressed asset store. These are architecture
directions, not claims that the proposed operation service or worker exists.

Out of scope: other panel archetypes, manufacturing or standards certification,
general-purpose CAD/sketch solving, a rewrite, default microservices, real-time
collaborative merging, proprietary model training and unrestricted AI mutation.
Detailed electrical semantics, methods and data rights retain their qualified
human review gates; an empty physical violation list does not establish them.

## Approved Save, Recompute, Publish and Restore UX

| Action | Intended user-visible semantics after approved implementation |
| --- | --- |
| Open | Read complete stored outputs and intact original bytes; report missing/incompatible/corrupt data explicitly. No generation, rerouting, automatic conversion or publication. Updating last-opened metadata is allowed. |
| Save | Persist structurally valid working edits through the operation boundary. Keep obsolete outputs marked dirty. No calculation, placement, rerouting, CAD work or revision creation. Already applied durable operations need no second write. Unfinished invalid input remains in recovery. |
| Recompute | Explicitly Save local edits first, then compute affected stages from pinned persisted input. Preserve manual decisions; replacement placement requires a reviewed proposal. Install only a valid result matching the captured sequence/version/hashes. No published revision or head change. |
| Publish | Explicitly snapshot the already computed complete compatible bundle. Block dirty outputs, any physical violation including warnings, and unresolved applicable required checks. No hidden recomputation. New immutable revision/head, with version fences and atomic publication. |
| Restore | Resolve unsaved edits/recovery explicitly. Copy a verified compatible complete source into a new revision and working state; record source and parent. Preserve historical bytes and original validation provenance; never invent a new check result. |
| Recover / Discard | Keep independent checkpoints and explicit choices. Incompatible-base overlays remain available for comparison/conversion; do not silently apply them. Autosave neither computes nor publishes. |

Keep unsaved edits, dirty stages, input-stale outputs, non-current history, version
drift, incompatibility and missing/corrupt outputs distinct. Selecting an old
revision does not make it stale internally. Display selection, visibility and
camera changes remain separate from engineering edits; schematic placement is
document presentation, while physical movement changes PDM.

P0-T04 defines proposed document sequence S, project lock L and recovery R:
changed Save/Apply and successful Recompute installation advance S/L once;
Publish advances L and revision/head without changing S; Restore advances S/L
and creates a new revision. Fenced recovery clearing must not erase a newer
checkpoint. Current Save/generation endpoints retain their existing semantics
until a versioned rollout; do not simply relabel Generate as Recompute.

## Approved legacy migration strategy

Preserve original snapshots, hashes, manifests, assets, workspace overlays and
recovery. Use additive schema migrations and versioned readers/contracts; never
rewrite published history or frozen baseline/seed data. Complete new publications
freeze CEM/PDM, schematic, BOM, CAD descriptors, validation, pins and artifact
metadata. Legacy missing outputs remain explicitly missing on ordinary reads.

Offer an explicit compatibility proposal showing source revision/hash, adapters,
new producer pins, missing outputs and consequences. Saved overlays currently
lack a proven base revision: require evidence or explicit base selection before
mapping transforms to typed PDM operations. Unknown IDs, unsupported rotations,
ambiguous connectivity or invalid values produce visible blocked entries.
Accepted proposals install atomically into working state; Recompute and Publish
then create new output provenance and revisions. Cancellation/failure preserves
originals. Never label regenerated outputs as original historical bytes.

Coordinate old/new API clients, import/export, duplicate, Restore, CAD jobs and
all `load_revision` consumers. Preserve old Save semantics or reject unsupported
mode explicitly; do not reinterpret overlay JSON as engineering. Packages allocate
new identities with verified rebinding and remain project exchange, not database
or catalog backups. Keep shared/historical assets; migration grants no deletion.

## Approved deployment and platform boundary

Default: local Tauri desktop, loopback FastAPI sidecar, separately provisioned
local PostgreSQL and managed local assets. Initial setup documents must make the
database prerequisite and migrations explicit; no SQLite/JSON fallback or bundled
PostgreSQL installer is approved by this proposal. Backup requires coherent
database plus referenced assets/catalogs. No deployment is performed by D01.

Recommend Linux x86_64 as the initial pilot target because this is the measured
host. Windows x86_64, macOS Intel/Apple Silicon, Linux ARM, mobile and remote
browser hosting remain deferred unless explicitly selected. OS-specific clean
installation, upgrade, database readiness, WebGL and sidecar lifecycle still
require evidence; native-worker testing applies only when native scope is enabled.
D06/P7-T02 must finalize exact supported distribution/OS versions and packaging
responsibility. Source portability and Tauri target declarations confer no support.

Local session/origin protection and trusted-session actor attribution remain
implementation/release obligations, not existing security guarantees inferred
from CORS or loopback. **Hosted multi-user exposure is blocked until a separate
identity/authorization backlog is explicitly approved and its release checks
pass.** That backlog must cover authentication/session lifecycle, project and
artifact permissions, cross-project isolation, server-derived actors, audit and
deployment threat review. It must name its approving humans and implementation
owner. D01 local scope and later local-session work cannot satisfy that condition.

## Approved reference limits and initial performance targets

Use the exact [baseline cases](../../backend/tests/fixtures/design_baselines/cases.json)
as initial workloads, not an inferred validated range of electrical inputs:

| Reference | Feeders | Components | Conductors/routes | Enclosure W × H × D mm |
| --- | ---: | ---: | ---: | --- |
| `db-12` standard | 12 | 29 | 44 | 800 × 1200 × 300 |
| `db-16` upper reference | 16 | 37 | 56 | 1000 × 1200 × 300 |

Each uses three rails, six ducts and ten accessories, 415 V, three phases, 50 Hz,
250 A incomer, IP54, 20% spare and neutral enabled. These are fixture inputs,
not independently approved ratings or certified applicability. The 56-route
case reaches the present router's discrete lane count. Recommend no initial size
claim beyond the upper reference counts; topology/capacity checks still govern
every design, including smaller ones. No runtime size guard is added here.
Other inputs/topologies, larger designs and actual hardware require separate
engineering review, fixtures and performance evidence before support expansion.

Reference hardware is the measured i3-1115G4 (2 cores/4 threads), approximately
8 GB RAM, Intel UHD G4, local PostgreSQL, Linux x86_64; exact environment is in
the baseline. This is a measurement configuration, not an established minimum
specification. It had swap available; memory peaks and GPU frame pacing were
not measured. Reuse exact fixtures/pins, record versions and host load, and run
measurements sequentially. Approved initial acceptance protocol (implementation pending):

| Metric | Approved initial target and interval | Repetition and limitations |
| --- | --- | --- |
| Drag feedback | p95 ≤ 33 ms, pointer-event receipt to the next frame callback after installing the corresponding visual preview; no synchronous server recompute on pointer movement. | Production build in a visible interactive desktop viewport, both boards, fixed viewport recorded. Five 30-second drag sessions per board, ≥200 total samples per board, no dropped slow samples. Frame callbacks approximate feedback opportunity, not GPU/display completion; record frame gaps separately. |
| Cached document open | p95 < 2,000 ms, explicit open command to saved document plus initial 2D/3D view ready for interaction; include API, parsing, model installation and render preparation. | Per board: one separately retained warm-up, then ≥30 sequential opens/re-mounts, warm process/assets and no Recompute. Record cold startup/assets separately. |
| Job acknowledgement | p95 < 500 ms, explicit submit to durable job receipt returned to the UI; exclude job execution from acknowledgement but report it separately. | Per board: one retained warm-up, then ≥30 submissions, one at a time under fixed queue conditions; verify durable job IDs. Current in-process queue does not establish the future durability guarantee. |

Use nearest-rank p95 (`ceil(0.95 × n)`), retain raw ordered samples, report
median/p95/max and failures per board/platform. Errors/timeouts fail the scenario,
not disappear from samples. Keep process/kernel/asset cold-start, network and
provider costs visible in separate measurements. D06 must confirm the final
release matrix/protocol; changed scope or thresholds require explicit review.

P0-T03 observed five-sample generate maxima of 3,524.497/4,325.508 ms, backend
saved-open maxima of 260.631/249.540 ms and headless SVG mount maxima of 26/24 ms
for `db-12`/`db-16`. Those are historical measurements with different intervals,
not passes for the targets above. There is no new generation-time, cold-start,
native, memory, concurrent-user or larger-board performance promise.

## Conditional kernel recommendation and independent gates

P0-T05 recommends a pinned headless FreeCAD adapter in a separate process,
retaining GLB previews. Its observed runtime was FreeCAD 1.0.2 / OCCT 7.8.1 in
the Linux x86_64 Python 3.11 AppImage; backend Python remains separate. This is a
conditional direction for later qualification, not adoption or redistribution.

Retained native evidence is **FAIL**: export and fresh-process STEP reopen each
returned 42 valid solids, but mounted-part bounds differ by up to **30 mm** from
PDM against the unchanged **0.05 mm** reference tolerance. Stable STEP occurrence
identity and production isolation also remain unqualified. A valid solid or
successful export process cannot override wrong placement. **Unqualified native
STEP is explicitly excluded from the MVP**, including any promise of exact
native output from the existing Python script. Script/GLB remain preview aids.

| Gate | Requirement retained regardless of D01 approval |
| --- | --- |
| P5-T00 / P0-T05-NATIVE-001 | Correct pivot/centring defect, review version compatibility and pass the unchanged pinned native export/fresh-process reopen reference before subsequent native implementation. Preserve the failed evidence. |
| P5-T02 | Qualify isolated worker resource bounds, timeout/crash/cancellation handling and publication fencing. |
| P5-T05 / P5-T06 | Qualify stable semantic occurrence/route identity, geometry units/transforms and revision-bound STEP evidence. |
| P7-T03 / P0-T05-DISTRIBUTION-001 | Obtain human distribution/license review of the exact runtime/dependencies and complete approved-platform packaging checks. Local evaluation permission, a subprocess boundary or product scope approval does not grant redistribution. |

**Kernel redistribution now: DEFERRED by explicit user selection H.**
Deferral retains both P5-T00 native qualification and P7-T03 distribution approval.
Even an explicit request to include redistribution does not clear either gate;
the license owner must separately record the exact approved artifacts, approach,
conditions and evidence. D01 cannot waive engineering or distribution failures.

## Human decision record

| Authority / record | Status |
| --- | --- |
| Product owner — JacobGM | APPROVED A–H as proposed, 2026-11-14; explicit conversation replies below |
| Human technical lead — JacobGM | APPROVED, 2026-11-14; “JacobGM also approves as human technical lead” |
| License owner, only if redistribution is selected now | NOT REQUESTED under recommended deferral; no clearance granted |
| Separate hosted identity/authorization backlog approval | NONE — hosted exposure remains blocked |
| Final D01 disposition | APPROVED for the stated bounded scope; no additional conditions supplied beyond the recorded exclusions and gates |

Conversation evidence, received 2026-11-14 (reviewed by 06:50:25 UTC for the
three choices; names supplied afterward):

- A–D: “Approve A–D as proposed; I will name the approvers”.
- E–G: “Approve E–G as proposed”.
- H: “Approve H; defer redistribution”.
- Initial names reply: “JacobGM , Nithin , Swarag .” No roles were inferred.
- Role clarification: “Product owner: JacobGM ; technical lead: Chatgpt ;”.
  ChatGPT was explained to be a technical adviser unable to grant human approval.
- Final human role confirmation: “JacobGM also approves as human technical lead”.
  This resolves the required second human role. Nithin and Swarag are not assigned
  approval roles by this record.

Final role confirmation was received by the recorded review time
2026-11-14 06:54:12 UTC. This is the agent's receipt/review time, not a separately
authenticated signature timestamp.

These are actual user replies, not an agent signature. The architecture_lead
prepared and recorded the decision; JacobGM supplied the human approvals. The
normal human decision process owns lifecycle acceptance/state; no lifecycle,
execution state, journal or history is modified by this record.
