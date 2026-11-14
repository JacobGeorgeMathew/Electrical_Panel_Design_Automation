# Current workflow and contract inventory

P0-T01 · source review dated 2026-11-12 · PanelFlow prototype DB designer.

## Scope and evidence

This is an inventory of the implementation at commit
`6e85b6b2918aaee2587e2c473584d076486d636e` on branch `phase_1`, not an approved
replacement contract or ADR. The reviewed worktree initially had no changes.
[The lifecycle](../../planning/development_lifecycle.json) was read only. Its E02
and E03 findings are confirmed below; its future document/operation APIs are not
present-day behavior. This task does not grant human acceptance or engineering
approval, change Save semantics, or implement a later lifecycle task.

Status labels throughout mean:

- **Implemented:** a concrete source path implements the stated bounded behavior.
- **Partial:** a path exists, with a specific missing guarantee or limitation.
- **Unverified:** runtime, platform, engineering or operational evidence was not
  obtained in this document review. Source inspection is not a passing test run.

FastAPI, PostgreSQL and the React/Zustand workspace form a modular monolith. DB is
the implemented engineering archetype. Calculations, catalog dimensions and
thermal/fill limits remain prototype assumptions; generated previews and scripts
do not establish manufacturing or standards compliance.

### Source index

References below use stable source symbols; links are relative to this document.

| Key | Source and relevant symbols |
| --- | --- |
| S1 | [ProjectService](../../backend/app/services/project_service.py): `create`, `update`, `_inputs`, `generate`, `load_revision`, `restore`, `propagate`, `queue_artifact`, `_artifact_worker`, `generate_files`; `ENGINE_VERSION` |
| S2 | [ProjectLifecycle](../../backend/app/services/project_lifecycle.py): `opened`, `recovery`, `delete`, `export`, `duplicate`, `import_project`, `_import` |
| S3 | [DesignOrchestrator](../../backend/app/services/orchestrator.py): `generate_design`, `_physical_design` |
| S4 | [ProjectRepository](../../backend/app/persistence/repositories.py): `row`, `get`, `create`, `check_version`, `touch`, `save_requirements`, `answer_values`, `revisions`; `CatalogRepository.asset_dto` |
| S5 | [Revision publisher](../../backend/app/persistence/revisions.py): `write_revision`, `transform` |
| S6 | [API request/response contracts](../../backend/app/models/api.py): `ProjectCreate`, `ProjectUpdate`, `RecoverySave`, `RevisionCreate`, `ExpectedVersion`, `ChangeInput`, `CadJobInput`, `ProjectImport`, `DesignPackage` |
| S7 | [Project routes](../../backend/app/api/routes_projects.py), [design routes](../../backend/app/api/routes_design.py), [CAD routes](../../backend/app/api/routes_cad.py), [asset routes](../../backend/app/api/routes_assets.py) |
| S8 | [Project store](../../frontend/src/stores/projectStore.ts): `projectFields`, `designFields`, `openProject`, `saveCurrentProject`, `recoverChanges`, `runDesignPipeline`, `restoreSavedRevision`, `validateCurrentPlacement`, `recoveryDocument` |
| S9 | [HTTP client](../../frontend/src/api/client.ts): `request`, `generateDesign`, `validatePlacement`, `saveRecovery`, project/revision/artifact wrappers |
| S10 | [Recovery hook](../../frontend/src/hooks/useProjectRecovery.ts): `useProjectRecovery`; [browser checkpoints](../../frontend/src/stores/projectRecovery.ts): `readRecovery`, `writeRecovery`, `clearRecovery` |
| S11 | [CEM](../../backend/app/models/cem.py): `CanonicalEngineeringModel`, `CEMState`, `ComponentRef`, `ConnectionRef`, `NetRef`; [PDM](../../backend/app/models/pdm.py): `PhysicalDesignModel`, `PhysicalComponent`, `WireRoute`, `DesignValidationPolicy` |
| S12 | [Draft rerouting](../../backend/app/services/physical_routing.py): `reroute_placement`; [duct routing](../../backend/app/algorithms/duct_routing.py): `DuctRouter`; [diff reporting](../../backend/app/services/change_propagation.py): `ChangePropagationEngine.compute_diff` |
| S13 | [Asset storage](../../backend/app/persistence/assets.py): `AssetStore`, `canonical_json`, `content_hash`, `primitive_glb`; [application lifecycle](../../backend/app/main.py): `create_app`, `lifespan` |
| S14 | [Workspace commands](../../frontend/src/components/workspace/useWorkspaceCommands.ts): `useWorkspaceCommands`; [history/recovery UI](../../frontend/src/components/projects/ProjectPersistenceBar.tsx): `ProjectPersistenceBar`; [dashboard](../../frontend/src/pages/ProjectDashboard.tsx): `ProjectDashboard` |
| S15 | [Schematic editor](../../frontend/src/components/schematic/SchematicViewer.tsx): `SchematicCanvas`; [BOM UI](../../frontend/src/components/bom/BOMTable.tsx): `BOMTable`; [workspace preferences](../../frontend/src/stores/workspaceStore.ts): `useWorkspaceStore` |
| S16 | [Generated mappings](../../backend/app/persistence/models.py): `projects`, `project_revisions`, `cem_snapshots`, `pdm_snapshots`, `generated_artifacts`; [0004 migration](../../backend/migrations/versions/0004_projects.py) |

## Contract ownership and identity

| State/model | Current authority and persistence | Status / source |
| --- | --- | --- |
| Project inputs | Current requirements derive from non-revision `project_requirements` plus answer provenance; fall back to current revision requirements when drafts are absent. `projects.configuration` holds enclosure selection/parameters. | Implemented: S4 `get`, `save_requirements`. These are mutable inputs, not an editable CEM/PDM aggregate. |
| CEM | Electrical components, terminals, graph, nets, connections and calculations; saved in `cem_snapshots`. | Implemented for bounded DB generation: S3, S5, S11. No current HTTP command publishes manual electrical connectivity edits. |
| PDM | Enclosure, mounting plate, components, structures, routes, policy and validation; saved in `pdm_snapshots`. | Implemented for generated arrangements: S3, S5, S11. Coordinates are enclosure millimetres with plate offsets; projection frame is lower-left-front, right-handed (S5). GLB converts millimetres to metres (S13). |
| Workspace overlay | `projects.workspace = {editorTransforms, schematicData}`. Transforms use CEM component IDs; schematic presentation may contain draft graph edits. | Partial: S6, S8, S15. Save persists these JSON overlays, not CEM/PDM mutations. Workspace has no saved base revision/hash. |
| Display state | Selection normalizes PDM component IDs to CEM IDs and route IDs to conductor IDs. Visibility, explode, tool, snap, grid and undo stacks live in the store. Dock dimensions/visibility persist separately under `panelstudio-workspace-v1`. | Implemented: S8 `selectObject`, S15. Hidden-component IDs and most display state are absent from Save/recovery payloads. |
| Local PDM | `pdmBaseline` is the loaded revision; `pdm` can become an edited/rerouted preview. `cadData` remains the loaded CAD descriptor. | Partial: S8 `updateEditorTransform`, `validateCurrentPlacement`. A successful draft preview is not a saved engineering revision or export source. |
| Derived outputs | Schematic data, CAD descriptors and `assembly_bom` are generated from CEM/PDM on every revision read. Stored artifact bytes have separate hashes/metadata. | Partial: S1 `load_revision`; E02 below. The frontend BOM UI separately derives its table from current store CEM/PDM (S15), rather than consuming `DesignPackage.bom`. |
| Recovery | Browser localStorage and `projects.recovery` store unfinished inputs/overlays and a base revision. | Implemented checkpoint paths, partial compatibility checks: S2, S8, S10. Recovery does not change saved inputs or revisions. |

Logical links are explicit: `PhysicalComponent.cem_component_id → ComponentRef.id`,
`WireRoute.conductor_id → ConnectionRef.id`, route/net and terminal endpoint IDs
cross CEM/PDM, and routes are named `ROUTE-<connection id>` (S11, S12).
`write_revision` creates fresh relational UUIDs for each revision's projections
while retaining logical `stable_key` values. `PANEL_ROOT` is an enclosure terminal
interface in projections, not a purchased BOM component (S5).

Identity support is **partial** for arbitrary editing: the selector uses sequence
labels such as `QF001`/`X001`, and netlist connection IDs depend on net/index
construction ([ComponentSelector.select_components](../../backend/app/services/component_selector.py),
[NetlistEngine.generate_netlist](../../backend/app/services/netlist_engine.py)).
No persistent identity allocator for arbitrary insert/delete/reorder operations
is established here. Import rebinds exact project/panel/PDM strings recursively;
it does not allocate new logical component IDs (S2 `_import`).

## Versions, preconditions and freshness

Let **L** be `projects.lock_version`, **R** be `projects.recovery_version`, and
**N** be a project's maximum `project_revisions.revision_no` (zero without history).
All counter increments below describe successful commits, not failed attempts.

| Counter / token | Initial value and transition | Consumers / limitations |
| --- | --- | --- |
| `lock_version` / frontend `lockVersion` | DB default 1. `touch` sets locked row's L+1 for metadata edits, Save, deletion and publication. | `expected_version` compares under `SELECT … FOR UPDATE`; mismatch is 409 `REVISION_CONFLICT` (S4). Open/recovery/artifact jobs do not increment L. |
| `recovery_version` / `recoveryVersion` | DB default 0. Recovery put/clear increments R; full Save and publication clear recovery and increment R. | Recovery requires both expected L and R. Full Save checks `expected_recovery_version` only when supplied; metadata-only PATCH does not increment R. Delete clears recovery without incrementing R (S1, S2, S5). |
| `revision_no`, revision UUID, `parent_revision_id` | Publisher allocates UUID and N+1 under project lock; parent is current head. | Generate, restore and each imported revision use S5. Save does not increment N. Restore parent is the pre-restore current head, with source separately in manifest. |
| Manifest `saved_lock_version` | L+1 recorded at publication. | Historical provenance, not current concurrency token. `DesignPackage.lock_version` always reports the project's current L, including historical reads (S1, S5). |
| Recovery `base_version`, `document.baseRevisionId`, `saved_at` | Checkpoint captures L, revision UUID/null, timestamp. | UI warns on base L mismatch; overlay application checks only base revision equality. Checkpoints are chosen by lexicographically latest timestamp, not a causal/version merge (S8, S10, S14). |
| Frontend `editSequence` | Starts/resets at zero on create/open; increments on input/config/schematic/transform changes and transform undo/redo/reset/recovery. | Save clears dirty state only if response matches captured sequence. It is local, not persisted or a backend precondition. Visibility changes do not increment it (S8). |
| `projectRequest`, `routingRequest` | Module-local increasing request counters; open also aborts a controller. | Fence late project and routing responses. Reroute additionally compares project, revision and transform object identity. No server sequence/idempotency fence (S8). |
| Local UI sequences | Camera command sequence increases; schematic `draftSequence` is local. | Presentation events only; neither is a project/revision version (S15). |
| CEM `revision` | Model default string `1.0.0`; generator does not increment it. | Distinct from database `revision_no`; PDM has no corresponding document counter (S11). |
| Revision/CEM/PDM `schema_version` | Writer currently stores integer 1 for each. | `load_revision` parses with installed Pydantic models; no schema-version dispatch/conversion is implemented (S1, S5). |
| Package/browser format versions | Package `panelstudio-project`, literal version 1; local key `panelstudio:recovery:v1:<id>`; workspace key `panelstudio-workspace-v1`. | Transport/storage format markers, not concurrency counters. Recovery payload has no independent schema field (S2, S6, S10, S15). |
| Catalog `version_no` and pinned UUIDs | Published archetype, questionnaire, rule set/rules, electrical templates, component/product, enclosure/hardware and CAD model versions. | `_inputs` materializes current eligible catalog/rules; manifest and projections pin consumed versions. Questionnaire/archetype versions are not project counters (S1, S4, S5). |
| Engine/generator/policy versions | Current `ENGINE_VERSION='db-pipeline-4'`; manifest GLB generator `panelstudio-primitives` version `3`; script artifact version is engine string; policy default `strict-v1`. | Queue checks exact engine/generator compatibility. Historical read marks engine mismatch stale but still invokes installed generators. Policy values are carried in PDM (S1, S11). |
| Migration/API versions | Inspected migration head `0004_projects`; FastAPI metadata version `1.1.0`. | Deployment/schema markers, not document locks (S13, S16). Installed database readiness was not exercised. |

Hashes are integrity/freshness evidence, not counters: `content_hash` is SHA-256
of sorted compact canonical JSON. Snapshot hashes cover each CEM/PDM; revision
`content_sha256` covers `{cem: cem_hash, pdm: pdm_hash, manifest}`. Package revision
`sha256` instead covers the full `{cem, pdm, manifest}` payload. Artifact SHA-256
covers bytes. Manifest `input_sha256` covers raw submitted requirements and
configuration (S1, S2, S5, S13).

`load_revision.is_stale` is true if engine differs, requested revision is not
current, or current persisted inputs/configuration hash differs from the manifest.
It conflates historical/non-current with outdated inputs; it does not compare
workspace edits, newer catalog releases, or a separate schematic/BOM generator
version. Frontend `designStale` also becomes true on local requirement/config edits
and recovery. Overlay edits mark `hasUnsavedChanges` but do not themselves mark
`designStale`; Save leaves that flag as it was (S1, S8). Thus a saved overlay can
coexist with a non-stale generated revision whose exports exclude that overlay.

## Request and state transitions

All project-relative paths below use `P=/api/projects/{project_id}`. The client
base includes `/api`; routes delegate to PostgreSQL services, not legacy JSON
runtime adapters (S1, S7, S9).

### Create and open

1. Dashboard `createNewProject` sends `POST /api/projects` with name, DB archetype,
   optional version/description/location and `requirements:{}`. S1 `create`
   resolves a template, inserts project and default/validated requirements with
   answer provenance, and sets last-opened time in one transaction. Initial
   revision is null; no generation or artifacts exist. Frontend clears prior
   CEM/PDM/overlays and loads project defaults plus refreshed project list.
2. `openProject` refuses unsaved local changes unless explicit discard is passed.
   It increments request token, aborts the previous design request and sends
   `POST P/open`. S2 `opened` writes only `last_opened_at` and returns `ProjectView`.
3. Frontend then fetches `GET P/revisions` and, when head exists, `GET P/design`
   concurrently. `designFields` installs CEM/PDM and baseline, descriptor data,
   artifacts, head identifiers, current L and stale flag; it clears transform
   history. Saved workspace transforms/schematic override loaded display data.
   Nonempty saved transforms trigger draft rerouting. Latest browser/server
   checkpoint becomes `pendingRecovery`; it is offered, not auto-applied.
4. Empty projects avoid the design request (direct design GET returns 404).
   Open does not optimize or publish, but its design GET invokes current output
   generators (E02). Open/project/revision reads span independent transactions,
   so another tab can change state between responses; the client request token
   prevents cross-navigation results, not this server consistency race.

### Edit, Save and close

1. Requirement/config edits update local values, dirty/stale flags and sequence.
   Physical edits store CEM-keyed transforms and immediately clear local routes;
   `validateCurrentPlacement` merges transforms onto baseline and calls
   `POST P/design/reroute-placement` (despite client name `validatePlacement`).
   Returned PDM/violations affect preview only. Schematic editing calls
   `setSchematicDraft` with symbols/wires; draft connection IDs are
   `DRAFT-CONN-<uuid>`/`NET-DRAFT-<uuid>` (S8, S9, S15).
2. `saveCurrentProject` captures L, R and sequence and sends `PATCH P` with
   `{expected_version, expected_recovery_version, requirements, configuration,
   workspace:{editorTransforms,schematicData}}`. S1 `update` locks/checks versions,
   merges saved/submitted requirements, validates requirements/configuration,
   replaces current requirement/source rows, writes workspace/configuration,
   clears recovery and increments L/R. It does not call the orchestrator,
   reroute, change the head or persist the preview PDM.
3. Successful Save updates saved input baselines/L/R and project list entry.
   It clears browser recovery and dirty state only if no newer sequence exists.
   Errors retain local edits. Save is blocked while saving/generating or recovery
   is pending. Even a workspace-only backend PATCH revalidates inputs and rewrites
   requirement provenance. Metadata-only PATCH follows a separate smaller path.
4. `saveAndClose` saves dirty state first and closes only when dirty is false.
   `closeProject` refuses busy/dirty state, invalidates pending requests and clears
   loaded design. Close has no API mutation. `discardLocalEdits` clears server
   recovery using both versions, clears browser checkpoint, then reopens saved
   state; failure retains local edits (S8).

### Recovery and discard

1. `useProjectRecovery` subscribes to store changes. Dirty state immediately writes
   localStorage `{base_version:L,saved_at,document}` with inputs, workspace and
   `baseRevisionId`. It debounces server autosave for 1500 ms; it suppresses
   writes while recovery awaits a decision and server sends while busy. Fingerprint
   is `[projectId,editSequence,lockVersion]` (S10).
2. `autosave` sends `PUT P/recovery` with expected L/R and document. S2 validates
   shape and 4 MiB canonical size but accepts unfinished engineering values. It
   writes recovery and R+1 only; dirty remains true. It neither saves requirements
   nor increments L/N. Errors are shown in autosave status; online events enable
   retry. No durable background retry queue is established.
3. `recoverChanges` makes no request. It applies inputs/configuration locally;
   overlays apply only when checkpoint base revision equals loaded revision.
   It sets dirty/stale, clears pending decision and increments sequence. An old
   base L is warned about but is not itself a recovery rejection. This action
   does not immediately reroute recovered transforms; explicit placement
   validation can refresh preview. Checkpoint selection uses timestamps whose
   clocks may differ, not an L/R-based merge (S8, S10, S14).
4. `discardRecovery` puts null using expected L/R, then removes browser checkpoint
   and pending state and adopts returned R. Recover/discard do not publish.
   Saving inputs or publishing later clears server recovery; successful
   generation/restore also clears local recovery through the frontend (S8).

### Generate and propagate

1. `runDesignPipeline` sends `POST P/revisions` with local requirements, current
   configuration and expected L; it refuses missing project/busy/pending recovery.
   This is synchronous generation (90-second client timeout), not a durable job.
   Legacy `POST P/design/generate` accepts overrides and optional expected L query;
   it uses saved configuration (S7, S9).
2. S1 `_inputs` materializes project/catalog/template/rules/model/hardware data and
   closes read transaction before engineering. `generate` checks supplied L,
   validates merged inputs/configuration and calls S3 with memory adapters and
   `persist_requirements=False`.
3. S3 transitions CEM through `REQUIREMENTS_VALIDATED → ENGINEERING_CALCULATED →
   COMPONENTS_SELECTED → NETLIST_VALIDATED → SCHEMATIC_GENERATED → FINAL_VALIDATED`.
   It calculates/selects, builds graph/netlist/schematic, considers feasible
   enclosures, runs CP-SAT placement, assembly ducts, **DuctRouter**, physical
   validation and wire geometry, then CAD descriptors/BOM. Additional enum states
   exist but are not assigned here. Disconnected/blocked duct routing fails;
   there is no free-air fallback in this flow. Any physical violations, including
   warnings, reject generation. This does not prove unresolved engineering
   subchecks or prototype assumptions are approved.
4. S1 pins catalog/model/version provenance and input hash, writes GLB/script
   bytes through `generate_files`, then opens a short publication transaction.
   S5 rechecks captured L, writes the publication records below and advances
   head/L/R. `generate` calls `load_revision` after commit to return `DesignPackage`.
5. Frontend fetches project/history and replaces state using `projectFields` and
   `designFields`, discarding prior overlays/undo state and clearing browser
   recovery. Failures before commit preserve the prior revision; assets already
   written may be orphaned. A response/load failure or timeout **after** commit
   can leave a successfully published revision despite a client error. No
   idempotency key or timeout cancellation of server computation exists (S1, S9).
6. `applyChangePropagation` sends `POST P/design/propagate-change`. It blocks other
   unsaved requirement/config edits but does not submit overlay edits. S1 loads
   old design, verifies field and performs full generation, then computes a diff.
   The returned diff modal opens **after publication**; it is not an approval
   preview. `DEPENDENCY_DAG` is reporting metadata, not a stage scheduler (S12).

### Restore

`restoreSavedRevision` refuses dirty/busy/pending-recovery state and posts expected
L to `P/revisions/{revision_id}/restore`. S1 first `load_revision`s the source
(including E02 generators), retrieves historical answer provenance and READY
artifact references, validates answers against the source archetype template and
restores manifest configuration. S5 publishes copied CEM/PDM as a fresh N+1
revision with `restored_from_revision_id`, current-head parent and new hash/L/R.
It reuses artifact storage keys, clears saved workspace/recovery and leaves source
snapshots unchanged. This does not rerun placement/routing. It does parse current
models and validate requirements; source engine pins stay historical, so restoring
an old-engine revision can still yield `is_stale=true`. Frontend fetches project
and history, installs the result and clears local recovery (S1, S5, S8).

### Export and preview refresh

Workspace/dashboard package export sends `GET P/export` and downloads the response
as JSON using a browser Blob. It exports saved server state, without Save or
changes to L/R/N. FreeCAD script export sends `GET P/cad/freecad-script` and
downloads returned script text; GLB export follows a READY artifact's
`GET /api/artifacts/{id}/content` URL. Neither exports the edited preview PDM.

`refreshCadPreview` rejects dirty/stale state, sets `cadJobStatus=PENDING`, posts
`{expected_version:L,file_format:'GLB'}` to `P/cad-generation`, and polls
`GET P/cad-generation/{job_id}` at 500 ms intervals, up to 60 attempts. READY
inserts/replaces that artifact in the store and sets READY; failure/poll timeout
sets FAILED with a message. Late results are fenced by project request token.
Backend queue/worker records and restart behavior are in the mutation inventory;
this refresh leaves project/revision counters and CEM/PDM unchanged (S1, S8, S9).

Client `request` normalizes structured errors and cancellation/timeout messages.
Backend `DesignError` is 422; `PersistenceError` uses its status/code, version
conflicts are 409, and database exceptions return sanitized 409/503. A timeout is
not proof a write failed; reopen reconciles server state (S9, S13).

## Mutation inventory

The following covers project, draft-computation and artifact lifecycle mutation
surfaces. Catalog routes are reads; database setup/import administration is
outside this workflow. **Q** means S4 `save_requirements`: replace non-revision
`project_requirements`/`requirement_sources`, create a submitted
`questionnaire_sessions` record when versioned, and supplied `question_answers`.
Historical answer/session records remain. **W** means the publication bundle
listed after the table. No row below edits an existing published CEM/PDM snapshot.

| Request / action | Preconditions | Persisted records and counter changes | Side effects / source / status |
| --- | --- | --- | --- |
| `POST /api/projects` | Valid `ProjectCreate`, supported DB template, unique optional code; no prior version. | New `projects` (L=1,R=0), metadata/open time and Q; no revision. | Defaults validated; rollback on failure. S1 `create`, implemented. |
| `POST P/open` | Existing nondeleted project; no expected version. | Only `projects.last_opened_at`; L/R/N unchanged. | Frontend subsequently loads history/design/overlays. S2 `opened`, S8; implemented. |
| `PATCH P` metadata-only | Required L; optional R checked if supplied; no requirements/config/workspace supplied. | Name/description/location and `updated_at`; L+1, R/N unchanged; recovery preserved. | No engineering work. S1 `update`, S4 `touch`; implemented. Empty PATCH also touches. |
| `PATCH P` inputs/workspace Save | Required L; optional expected R; requirements/config validation. | Q, metadata/config/workspace fields provided, recovery null; L+1,R+1,N unchanged. | No generation or publication; overlay authority partial. S1 `update`. |
| `PUT P/answers` | Required L and answers; no R field on `AnswerSave`. | Same full update path/Q; L+1,R+1, recovery cleared, head/workspace retained. | Optional recovery fence bypassed by this adapter. S7 `save_answers`, S1; implemented. |
| `PUT P/recovery` document or null | Required L and R, document shape/size ≤4 MiB; no engineering validation. | Recovery checkpoint or null; R+1 only; even clearing null increments R. | No Q/W/routing. Browser put/remove is a separate local action with no server precondition. S2 `recovery`, S8/S10; implemented. |
| `POST P/revisions` | Required L; valid inputs/configuration, catalog/rules/assets available and zero physical violations. | Q + W; N+1,L+1,R+1; head moves, workspace/recovery cleared. | Optimization/routing/files precede writer; final fence uses captured L. S1 `generate`, S5; implemented bounded pipeline. |
| `POST P/design/generate` | Optional query L; same engineering checks. | Same Q+W and increments as above. | If omitted, client base is unchecked initially; final writer still fences against L captured by `_inputs`. S7 `generate_design`; partial concurrency contract. |
| `POST P/design/propagate-change` | Optional L; existing current design, known question field. Omission uses captured current L. | Full generation Q+W and increments. | Diff computed after publication; full rerun, overlays replaced. S1 `propagate`, S12; partial preview/incremental semantics. |
| `POST P/revisions/{rid}/restore` | Required L at writer, source belongs to project, hashes and current model/answer parsing succeed. | Q+W using source CEM/PDM and READY files; N+1,L+1,R+1; clears workspace/recovery. | Reuses file bytes; reconstructs outputs on load; no physical rerouting. S1 `restore`; partial historical-output guarantee. |
| `POST P/design/validate-placement` | Body PDM project ID equals path; no L/R/rid check or project lookup. | None; response PDM validation results only. | Current validator, no routing/publication. S7 `validate_placement`; implemented preview. |
| `POST P/design/reroute-placement` | PDM project ID and CEM component-ID set match current saved design; no expected L/R/rid. | None; response says `persisted:false`. | Loads current CEM through E02, clears/reroutes all draft routes; violations clear routes. Rotated devices unsupported. Client fences late results only. S7, S12; partial base binding. |
| `POST P/cad-generation` | Required L; current non-stale revision and exact supported engine/generator; executor available; L checked again transactionally. | New `generated_artifacts` PENDING row pinned to rid/PDM hash; L/R/N unchanged. | Executor submit follows commit; in-process work may be interrupted. S1 `queue_artifact`; partial durability. |
| Artifact worker completion/failure | Captured rid/job; READY update requires still PENDING. | Same artifact row becomes READY with metadata or FAILED with safe error/completion time; L/R/N unchanged. | Files content-addressed; source revision may no longer be head. `_artifact_worker` loads/reconstructs captured revision. S1; implemented local worker, unverified execution here. |
| Backend startup | Database exists and ready. | All PENDING `generated_artifacts` marked FAILED/`INTERRUPTED`; no project counters. | Restart-wide, not leased/resumable jobs. S13 `lifespan`; partial durability/multiprocess assumptions. |
| `DELETE P` | Required L; nondeleted project. | Tombstone `deleted_at`, clear recovery, update timestamp; L+1, R/N unchanged. | Standard project lookups/listings hide it; history/files retained. Global artifact-by-ID routes do not check project tombstone. S2 `delete`, S4 `row`, S7 asset routes; implemented retention, no access-revocation guarantee. |
| `POST P/duplicate` | Required source L, valid new name; package limits/destination catalog checks. | Source unchanged; fresh project plus imported Q/W sequence. | Export source under lock, then import in separate transaction; files rebuilt. S2 `duplicate`; partial portable-copy guarantee. |
| `POST /api/projects/import` | Package v1, ≤32 MiB/200 revisions, integrity/model/project IDs/catalog/physical checks; no existing target version. | New project L=1,R=0; each source revision Q+W adds L/R/N; final Q and `touch` add L+1, workspace/config imported. | New project/revision UUIDs, exact project refs rebound, new provenance/hashes/artifacts; source unaffected. With k revisions final L=k+2,R=k,N=k. S2 `_import`; partial historical byte portability. |

**W — publication records (S5 `write_revision`):** `project_revisions` (PUBLISHED,
parent/version pins/manifest/hash), `cem_snapshots`, `pdm_snapshots`, revision-bound
copies of requirements and sources, `project_parameter_overrides`,
`revision_components`, `cem_component_instances`, `cem_terminal_instances`,
`cem_nets`, `cem_conductors`, `cem_net_terminals`, `pdm_enclosures`,
`pdm_mounting_structures`, `pdm_component_instances`, `pdm_placements`,
`project_cad_instances`, `pdm_routes`, `pdm_clearance_regions`, `validation_runs`,
`validation_results`, READY `generated_artifacts`, `revision_dependencies` and
`provenance`. It updates the project head/configuration, clears workspace/recovery
and increments L/R atomically with Q. Generated schematic/CAD descriptor/BOM JSON
is **not** in W. There is no separate working-document/operation log or Publish
endpoint in the current implementation.

Normal generation and restore compute/read outside the short writer transaction.
**Import is an exception:** `_import` holds its destination transaction across
per-revision physical validation, CAD descriptor generation and asset writes.
Export holds a source project lock while `load_revision` opens separate read
sessions and computes all historical outputs. Duplicate runs these two paths
sequentially. These are observed transaction boundaries, not a claim that every
lifecycle path meets the short-transaction architectural intent (S1, S2).

## Reads, downloads and E02 impact

### E02: historical reconstruction

S1 `load_revision` verifies CEM/PDM canonical hashes and the manifest-bearing
revision hash, obtains artifact DTOs and deep-copies snapshots within a read
session. After that session closes, it parses installed CEM/PDM models and calls:

- `SchematicEngine.generate_schematic_data(cem_model)`;
- `CADEngine.generate_parametric_geometry(pdm_model)`;
- `assembly_bom(cem_model, pdm_model)`.

It returns stored PDM validation results, not a new physical validation run.
Saved CEM/PDM hashes are thus protected by reads, while **complete historical
output invariance is partial**. Changed generators/current model validation can
change returned output or prevent historical reads even when hashes pass. The
revision hash does not cover the returned reconstructed schematic/CAD/BOM.
Saved GLB/script artifact bytes are independently content-addressed; returning a
live descriptor is not evidence those descriptors match saved artifact bytes.
Even generation's post-commit response uses this reconstruction path (S1).

### Endpoint and export dependencies

| Read/export surface | Current behavior and later-operation integration impact |
| --- | --- |
| `GET /api/projects`, `GET P`, `GET P/answers`, `GET P/requirements`, `GET P/revisions` | Project inputs/metadata/version/projection summaries through S4/S7; no output generation. List excludes tombstones and supports search/recent/pagination. Requirements endpoint returns non-revision rows; answers merges provenance. Later operation contracts must keep current-input and revision views distinct. |
| `GET P/design`, `GET P/revisions/{rid}` | Full E02 path; historical result uses current L and `is_stale` conflates non-current. Current UI history selection chooses a restore target, not a historical read-only editor (S14). |
| `GET P/layout`, `GET P/schematic`, `GET P/cad` | All call full `load_revision` even when returning one projection. E02 generator failure can block layout-only reads. Sources: [layout](../../backend/app/api/routes_layout.py), [schematic](../../backend/app/api/routes_schematic.py), S7 CAD. |
| `GET P/validation` | Calls E02 then reads stored `validation_results` joined through `validation_runs` for current rid; reports saved violations/thermal values, no recompute. Source: [get_validation_report](../../backend/app/api/routes_validation.py). |
| `GET P/cad/freecad-script` | Calls E02, rejects stale with `STALE_DESIGN`, regenerates script from saved PDM with installed `CADEngine`; no expected L, no artifact insertion or project change. It does not run FreeCAD or emit a natively verified STEP file (S7). |
| `GET P/artifacts`, `GET P/cad-generation/{job}` | Metadata/availability reads; project artifact list spans all revisions; job GET checks project ownership. No generation; counter changes occur only in queue/worker/startup. Current design's artifact list comes from E02. |
| `GET /api/artifacts/{id}` and `/content`; catalog `/api/assets/{id}` equivalents | DTO availability and READY/LOCAL/hash/size checks. Content returns immutable-cache headers/ETag and existing bytes. No stale/current-head check and no project lock; historical downloads remain possible by ID. S7 asset routes, S13 storage. |
| `GET P/export` | S2 locks project with no client expected version, limits 200 revisions/32 MiB, calls E02 for every history entry, then serializes saved metadata/requirements/config/workspace and each CEM/PDM/manifest/package hash. Does not include recovery, artifact bytes/metadata, generated schematic/BOM/CAD JSON or source revision IDs as a full history backup. No project counters change; download is browser JSON. |
| `POST /api/projects/import`, `POST P/duplicate` | New identity, model parsing/current physical validation and requirement/template checks. Rebuild GLB/script using installed generators; do not preserve source artifact bytes. Package SHA is checked before rebinding; copied revision manifest/hash differs. References in original manifest may remain historical provenance; this is not a catalog/database backup (S2). |
| `POST P/design/propagate-change`, restore, reroute, CAD job + worker | E02-dependent mutations/computations from the inventory above. A generator/schema change can affect their ability to proceed without any placement change. All are affected consumers for later historical-output/operation contracts. |
| Requirement questions/validation/suggestions | `GET P/requirements/questions`, `POST …/validate`, `POST …/suggestions` read pinned template/catalog and compute responses; no version precondition or persisted mutation. Sources: [requirement routes](../../backend/app/api/routes_requirements.py). |

Workspace exports use saved engineering state (S14). GLB chooses a READY artifact
from the loaded revision and follows its content URL. FreeCAD export calls the
live script endpoint. Both workspace commands disable on dirty/stale state;
the separate BOM script button calls the same endpoint without that client-side
guard and only logs failures (S15). Backend stale checks see persisted inputs,
not unsaved browser edits. Project-package export remains available for saved
state even when local edits exist. None of these actions implicitly saves an
overlay into the published engineering revision.

## Gaps and verification limits

| Status | Finding and source evidence | Boundary for later work |
| --- | --- | --- |
| Partial | E02 reconstructs outputs on every read; schema parsing has no historical adapter; engine check is stale reporting, not full output compatibility (S1/S5). | Preserve original snapshot/artifact bytes. A later complete-output contract needs explicit legacy missing-output/conversion semantics; this inventory authorizes no conversion. |
| Partial | Overlays do not mutate CEM/PDM authority. Saved workspace is not revision-bound; recovered overlays check only base rid, and recovery does not immediately reroute (S6/S8). | Future document/operation contract and overlay migration require the specified human decision, including compatibility behavior. Current Save/recovery semantics remain in place. |
| Partial | Draft reroute has no base revision/version fence; import does physical validation with current code; unsupported rotations return a routing violation (S2/S7/S12). | Preserve strict constraints and identities; do not interpret preview as a validated publication or invent rotation support. |
| Partial | `is_stale` merges multiple causes; optional expected-version and recovery-version paths exist; request cancellation is client-only (S1/S6/S8/S9). | Later operations must account for every adapter, frontend baseline and export/restore consumer listed above. No idempotent operation API exists yet. |
| Partial | In-process CAD worker, restart-wide PENDING failure, asset writes before DB commit and import/export transaction exceptions (S1/S2/S13). | Do not claim durable jobs or transactional file rollback. Missing/corrupt assets are reported, not silently replaced/deleted. |
| Unverified | Database role permissions/triggers enforcing immutability, runtime concurrency interleavings, application tests/builds, actual fixture outputs/performance, platform installers/WebGL and native CAD execution were not exercised. | Source-backed implementation descriptions are not runtime acceptance or electrical/manufacturing certification. |

## Review evidence

Document-review method: inspect route decorators and request models, follow each
handler into S1/S2/S4/S5, cross-check frontend payloads and state installation in
S8–S10/S14/S15, and check E02 consumers, counters, records and side effects against
source. Compare [project lifecycle](../PROJECT_LIFECYCLE.md),
[workspace](../CAD_WORKSPACE.md), [database operations](../database/OPERATIONS.md)
and [architecture assessment](../../ARCHITECTURE_ASSESSMENT.md) with implementation.
Older database prose describes `0003_constraints` and advisory validation without
rerouting; inspected source has `0004_projects`, engine `db-pipeline-4` and an
explicit nonpersisting draft reroute endpoint. Proposed architecture sections
describe future behavior and do not override this inventory.

Existing evidence locations were inspected, **not executed**:

- [Backend project lifecycle tests](../../backend/tests/test_project_lifecycle.py):
  `test_create_empty_save_reopen_after_backend_restart`,
  `test_duplicate_delete_and_package_roundtrip`,
  `test_recovery_is_durable_and_conflicting_tabs_cannot_overwrite`,
  `test_duplicate_and_import_preserve_generated_history`,
  `test_rename_preserves_recovery_and_invalid_packages_are_atomic`.
- [PostgreSQL tests](../../backend/tests/test_postgres.py):
  `test_workflow_reopens_snapshots_projections_and_artifacts`,
  `test_atomic_revision_rollback`, `test_background_cad_status_and_missing_assets`.
  Their presence is not proof of changed-generator historical invariance.
- [Store persistence tests](../../frontend/src/stores/projectStore.persistence.test.ts),
  [draft routing tests](../../frontend/src/stores/projectStore.routing.test.ts) and
  [recovery hook tests](../../frontend/src/hooks/useProjectRecovery.test.tsx) name
  save/conflict/recovery/late-result scenarios; frontend mocks do not establish
  PostgreSQL or native CAD behavior.

The P0-T01 [attempt report](../../planning/task_reports/P0-T01/attempt-01.md)
records actual review commands, exit statuses, unrun verification and the
assessment for human review. No migration, dependency installation, application
test, server, database or native CAD process was run for this documentation task.
