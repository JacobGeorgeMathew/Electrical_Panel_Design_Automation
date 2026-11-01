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
selection is the existing project store selection; PDM component IDs normalize to CEM
component IDs and physical route IDs normalize to conductor IDs. No CEM/PDM instances,
connectivity, sizing or catalog specifications are recreated by the shell.

Properties support the existing physical transform draft and schematic net-label draft.
Catalog specifications and mechanical hardware are inspected read-only. Components
opens the existing library; electrical device insertion continues through Requirements
and the existing automatic generator. This task does not add a backend manual-instance
insertion API. Measure reports the center-to-center distance and axis deltas of two
selected physical components, using the current transform draft in millimetres.

Camera controls include fit, zoom, isometric/front/top/right 3D views, and the existing
native/full-window fullscreen fallback. Three.js uses live canvas dimensions and
updates the orbit target during fitting. React Flow observes its container and refits
after panel resizing. The 2D SVG uses a responsive viewBox and zoom controls. Panel
resizing does not remount the canvas. Camera requests are consumed once rather than
replayed when changing document views.

Keyboard shortcuts: Ctrl/Command+S saves, Ctrl/Command+Z undoes placement,
Ctrl/Command+Shift+Z redoes placement, V selects, M moves, F fits, Shift+F maximizes.
Text fields retain native undo. Menus support arrows and Escape; dialogs trap focus.

The console shows backend validation, errors, current engineering values, and actual
generation/export state. Generation is indeterminate because the existing synchronous
API does not publish stage progress. No synthetic percentages or engineering results
are displayed. Exports continue to use the saved revision and existing API endpoints.

Frontend tests cover shell navigation, selection normalization, inspector synchronization,
measurements, dividers, responsive collapse, save shortcuts, generation state, camera
zoom/aspect/orientation, non-replayed fullscreen, and schematic ResizeObserver cleanup.
The existing viewer, project lifecycle, and API tests remain in place.
