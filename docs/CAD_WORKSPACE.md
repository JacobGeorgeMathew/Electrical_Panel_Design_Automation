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

`OperationPreview` shows retained errors/proposals and dirty stages. Save preserves
the working document without rerouting or publishing; transient physical previews
and legacy schematic overlays cannot override its saved geometry on reopen. Explicit
recovery still retains unfinished edits. Manual operation drafts require subsequent
Recompute support before Publish; the automatic input pipeline cannot silently
replace them. Recompute implementation is outside these workspace tool bindings.

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
