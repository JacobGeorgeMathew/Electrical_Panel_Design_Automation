# Engineering workspace

The project workspace now has a menu bar, shared command toolbar, project browser,
central document tabs, properties inspector, resizable engineering console, and
save/revision status bar. Existing project dashboard and lifecycle APIs are unchanged.

The default browser/inspector widths are 180/224 pixels, leaving about 70–80% of a
normal desktop width to the design area. Drag the dividers or focus them and use
arrow keys. Panels collapse through View or the toolbar. Sizes and visibility are
browser preferences, separate from engineering documents. Below 1100 pixels the
inspector uses an overlay; below 720 pixels both side docks use overlays. Narrowing
the window closes them automatically; they can be reopened through the toolbar.

The existing React Three Fiber, SVG layout, React Flow schematic, BOM and questionnaire
components are integrated, with embedded modes removing duplicated docks. The shared
selection is an opaque engineering ID in `selectionStore`, with a compatibility
facade for existing project-store consumers. PDM component and schematic symbol IDs
normalize to CEM component IDs; physical routes and schematic wires normalize to
conductor IDs, and schematic pins normalize to terminal IDs. No CEM/PDM instances,
connectivity, sizing or catalog specifications are recreated by the shell.

`commandStore` retains an explicit operation or history proposal and its idempotency
key. Preview, commit and undo/redo history requests use the central HTTP client.
Cancellation, changed local inputs and changed document/project context fence late
responses. Rejection retains the proposal and shows the server code and message in
the console. Successful commits advance only the returned working document; saved
published revisions stay immutable. Physical gestures keep a transient preview and
commit one `MoveComponent` on release. Coordinate fields in 2D, 3D and the inspector
use the same enclosure-mm command path and snap preferences. Both viewers install
only the returned PDM. Undo/redo uses server operation history, including after reopen.
Rotation stays disabled until physical/routing support is available. Camera,
visibility, explode and grid preferences emit no engineering operations.

The typed schematic page is a presentation projection with stable symbol/pin IDs.
Symbol release commits `MoveSymbol`; labels and valid shared-pin junction markers
use presentation operations. They do not edit CEM connectivity. Pin gestures open
`ConnectionPreview`, requiring an existing net and explicit conductor dimensions.
Create/replace/delete must preview electrical effects, invalidated routes and removed
nets before Apply. The server checks explicit terminal/supply evidence; labels and
crossings never establish connectivity. Missing evidence remains a rejection.

The catalog supports `AddComponent` with an exact published component version,
explicit zone/rail/enclosure coordinates and unconnected catalog terminals. Apply
requires a successful server preview. The inspector's removal tool previews the
server dependency closure and requires explicit confirmation before `RemoveComponent`.
Catalog specifications and mechanical hardware remain read-only. Measure reports
the center-to-center distance and axis deltas of two
selected physical components, using the current transform draft in millimetres.

The supported operation surface is bounded:

| User action | Shared operation / authority | Current boundary |
| --- | --- | --- |
| 2D drag, 3D gizmo or coordinate/inspector edit | `MoveComponent`, working PDM | One release/field commit per undo group; placement policy checked, routes retained dirty. |
| Symbol drag, label or shared-pin junction marker | `MoveSymbol`, `UpdateSchematicLabel`, `UpdateJunctionPresentation`, schematic page | Presentation only; CEM hashes/connectivity remain unchanged. |
| Pin connection or selected wire replace/delete | `ModifyElectricalConnection`, CEM plus dependent PDM/page changes | Explicit conductor data, preview and Apply required; absent supply/terminal evidence rejects. |
| Catalog insert / inspector remove | `AddComponent` / `RemoveComponent` | Exact catalog version and explicit placement; removal requires confirmation of the exact dependency closure. |
| Undo / redo | Version-fenced server history | Persists across reopen; changed inputs can fence older history. |
| Automatic DB proposal | `ApplyGeneration`, API only | Explicit review/acceptance and one undo group; no workspace proposal-review UI. |
| Requirement/rating/enclosure and page regeneration commands | `UpdateRequirement`, `ChangeComponentRating`, `ResizeEnclosure`, `RegenerateSchematic` in backend registry | Command APIs exist; questionnaire/enclosure forms still save input drafts through the document PUT. These forms are not shared-operation undo tools. |
| Rotate, rail/duct geometry editing, general CAD editing | Unavailable | Nonzero rotation is rejected; mechanical/catalog definitions remain read-only. |

Successful draft operations can leave `requirement_rules`, `physical_constraints`,
`routing` and `physical_validation` checks `UNRESOLVED`. Movement checks saved
backplate/enclosure bounds, depth, collisions, clearances and prototype thermal
density, but does not reroute, refresh thermal metadata or establish mounting,
oriented-solid, bend/earth or complete electrical validity. Existing route geometry
may describe the previous placement. `UNRESOLVED` is not PASS. Automatic generation
still requires zero physical violations, including warnings. These are prototype
DB assumptions, not manufacturing or standards certification.

`OperationPreview` shows retained errors/proposals and dirty stages. Save preserves
the working document without rerouting or publishing; transient physical previews
and legacy schematic overlays cannot override its saved geometry on reopen. Explicit
recovery still retains unfinished edits. Manual operation drafts require subsequent
Recompute support before Publish; the automatic input pipeline cannot silently
replace them. Recompute implementation is outside these workspace tool bindings.
The current labels and actual effects are:

| Label | Actual behavior |
| --- | --- |
| `Save project`, `Save draft`, `Save & close` | Save input drafts/metadata; accepted engineering operations are already durable. No generation, rerouting or publication. Transient mesh previews are not saved as authoritative PDM. |
| `Recompute required before Publish` / `Recompute required: …` | Dirty-output status, with no standalone Recompute action implemented. |
| `Generate & publish revision (legacy)` | Combined generation/publication for untouched input-only documents only. This is an explicitly labeled compatibility action. |
| `Publish unavailable` | Disabled after changed-input Save, CEM or generation intent; explanation identifies pending separate Recompute/Publish. The store and server enforce the same boundary. |
| `Automatic change unavailable` | Questionnaire single-field generation is disabled for working documents; input drafts remain editable and recoverable. |

The server returns `GENERATION_PROPOSAL_REQUIRED` after a document edit or when
CEM/generation intent exists. All Publish entry points use the same eligibility
check, including the toolbar/Design menu, project history, questionnaire and legacy
Header. Disabled actions explain their limitation. The UI does not switch to the new
[generation proposal API](GENERATION_PROPOSALS.md). Accepting a proposal changes
only the working document and leaves CAD dirty. End-to-end publication of edited
documents is therefore unavailable; do not interpret the status text as a working
Recompute/Publish pipeline. Acceptance evidence and outstanding regressions are
recorded in [phase 2 verification](verification/phase-2-acceptance.md).

The mutation audit distinguishes model edits from input/lifecycle/display state:

| Path | Durable write, authority and fences | History and recovery |
| --- | --- | --- |
| Physical gesture or coordinate field | `MoveComponent` batch installs returned working PDM; document ID/sequence, project lock, revision base and PDM hash are checked. | Transient pointer/field preview, one release/blur group; server undo/redo survives reopen. Recovery can retain unfinished preview; Save never promotes it to PDM. |
| Symbol move, wire label, shared-pin junction | Presentation operations install returned schematic; same base fences plus schematic hash. | Local drag only until commit; one group. CEM connectivity stays unchanged; saved page reopens without regeneration. |
| Electrical create/replace/delete | `ModifyElectricalConnection` preview then Apply; CEM plus dependent PDM/page hashes and base fences. | Explicit effect review; rejection retains proposal and idempotency key. History restores exact snapshots. |
| Catalog insertion/removal | `AddComponent` exact version and server preview; `RemoveComponent` dependency-closure confirmation; affected-model hashes and base fences. | One accepted batch/group, server result only. Cancellation/rejection makes no durable model change. |
| Requirement/enclosure local input and submission | Local setters retain drafts; explicit Save sends input-only document PUT with L/S, then metadata PATCH with advanced L. CEM/PDM remain untouched and dirty. | Separate lifecycle Save contract, no operation group. Unfinished input uses browser/server recovery with independent R and explicit Recover/Discard; conflicts retain edits. |
| Automatic generation | Read-only API candidate preview; exact retained candidate acceptance through dedicated endpoint with digest, base fences and idempotency key. | One shared undo group; manual models/placement locks protected. No revision/artifact creation; no proposal-review UI. Legacy combined action is restricted as above. |
| Undo/redo, Save/reopen | Server history uses L/S, revision base and content hash. Save cannot replace engineering snapshots; reopen reads them. | Applied operation groups are durable; version drift conflicts visibly. Save is not an additional geometry history group. |
| Camera, visibility, selection, grid and dock sizes | Workspace/display state only. | No engineering operation required; separate browser preference persistence. |

No supported engineering tool bypass was found in the reviewed physical,
schematic, electrical or catalog bindings. Input Save intentionally has its own
current contract. D01 describes structurally valid Save through operations, whereas
the versioned P1 input API and current forms preserve direct input Save. The literal
P2 all-mutations criterion therefore needs a human scope decision; this audit does
not exempt input submissions by inference or claim full phase acceptance.

Camera controls include fit, zoom, isometric/front/top/right 3D views, and the existing
native/full-window fullscreen fallback. Three.js uses live canvas dimensions and
updates the orbit target during fitting. React Flow observes its container and refits
after panel resizing. The 2D SVG uses a responsive viewBox and zoom controls. Panel
resizing does not remount the canvas. Camera requests are consumed once rather than
replayed when changing document views.

Keyboard shortcuts: Ctrl/Command+S saves, Ctrl/Command+Z undoes the latest operation,
Ctrl/Command+Shift+Z redoes it, V selects, M moves, F fits, Shift+F maximizes.
Text fields retain native undo. Menus support arrows and Escape; dialogs trap focus.

The console shows backend validation, errors, current engineering values, and actual
generation/export state. Generation is indeterminate because the existing synchronous
API does not publish stage progress. No synthetic percentages or engineering results
are displayed. Exports continue to use the saved revision and existing API endpoints.

Frontend tests cover shell navigation, selection normalization, inspector synchronization,
measurements, dividers, responsive collapse, save shortcuts, generation state, camera
zoom/aspect/orientation, non-replayed fullscreen, and schematic ResizeObserver cleanup.
The existing viewer, project lifecycle, and API tests remain in place.
