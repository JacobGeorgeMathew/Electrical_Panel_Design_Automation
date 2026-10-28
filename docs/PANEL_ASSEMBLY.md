# Enclosure assembly and duct routing

The current engine is `db-pipeline-3` with migration `0003_constraints`: it enforces the declared DIN clearance for terminals and selects enclosures that also pass the thermal-density limit. [Upgrade instructions and strict-policy seeds](CONSTRAINT_POLICY_UPDATE.md) replace the earlier warning-tolerant generation behavior described in historical verification notes below. Primitive geometry generator 2 and the existing hardware definitions are retained.

The generation engine now builds a cabinet assembly as well as electrical placements. All physical coordinates remain enclosure millimetres. A saved PDM includes `accessories`, `construction`, real `ducts`, detailed local component `geometry`, and each wire's duct references/trunk indices.

## Install/update catalog data

With PostgreSQL configuration set privately in the backend terminal, run from `backend/`:

```powershell
.\venv\Scripts\python.exe -m app.persistence.manage initialize
.\venv\Scripts\python.exe -m app.persistence.manage import-legacy
```

For an existing initialized/imported database, the targeted additive update is:

```powershell
.\venv\Scripts\python.exe -m app.persistence.manage import-panel-hardware
```

Linux uses the same modules with the activated environment's `python`. No extra database tables are needed: existing versioned component, CAD, accessory, mounting-structure, route and revision tables store these records. The schema revision remains `0002_app`.

The import adds the versioned generic parts in `backend/app/data/panel_hardware.json`: enclosure shell, door, hinges, handle, gasket, gland plate, 40×60 slotted duct with cover, top-hat rail, terminal end stops, insulating end plate and three isolated outgoing terminals. Accessory relationships link the enclosure catalog entries to these parts. Imported hardware source changes require a new version; existing published rows are not rewritten.

New detailed CAD model versions and GLB assets are added for existing components/enclosures. Electrical component version 1 and earlier CAD assets remain available. The catalog repository orders CAD versions newest first. These assets are generated generic geometry, not manufacturer CAD or certified construction data.

## Generate and inspect

Restart the backend after updating code/catalog. Open a DB project and choose **Generate Design** to publish a new revision. An old revision's snapshot and artifacts are preserved; it does not acquire ducts just because the application was upgraded. Old revisions can still be read, but export regeneration requires a matching generator version.

In the 3D tab:

- **Close door / Open door** rotates the door, handle, gasket and moving hinge geometry around the hinge side.
- **Fit duct covers / Remove duct covers** shows or removes the lids so the wires can be inspected.
- **Hide cabinet body / Show cabinet body** exposes the interior without removing electrical parts.
- Select a duct in the tree or viewport to see dimensions, estimated fill and wire count.
- The component tree contains cabinet hardware as well as electrical components. The BOM includes hardware, duct cut lengths and DIN rail cut lengths.
- **View saved GLB** shows the saved closed-cabinet artifact; return to the assembly editor to operate the door/covers.

## Placement and routing

`PanelAssemblyEngine.layout_config` reserves left/right gutters and horizontal trough bands. CP-SAT excludes those bands from plate-device placement. Terminal assemblies occupy a contiguous rail strip with space for end stops. Device z offsets now derive from the mounting plate, and rail geometry uses an actual top-hat section.

`DuctRouter` constructs a connected occupancy grid from the physical trough footprints. Terminal leads use obstacle-checked paths to the nearest reachable trough. Trunks use JPS/A* constrained to the trough network, with visibility smoothing only inside that network. Disconnected or obstructed troughs fail generation; there is no free-air trunk fallback. Terminal endpoints remain exact catalog points. A few depth lanes make coincident bundles visible; this is not a full wire-packing solver.

Each route records `duct_ids`, `duct_entry_index`, `duct_exit_index` and an estimated insulated `wire_diameter_mm`. Duct records carry estimated conductor area, route IDs, fill percentage and the catalog fill limit. The validator independently checks trunk containment, declared volumes, duct/device collision, bounds and estimated cross-sectional fill. Only local terminal leads may leave the trough network. Overfill is a critical failure. The configured 40% fill limit and wire diameters are generic assumptions, not ampacity or standards calculations.

Three-pole outgoing branches use a three-terminal assembly and separate per-phase, per-breaker-side nets. Other existing limitations in load-based selection, neutral/PE branch design and electrical protection calculations remain.

## Persistence and output

The revision manifest pins hardware component versions and `db-pipeline-2` / primitive generator 2. Ducts are `WIRE_DUCT` mounting structures; other hardware uses `OTHER` with typed category/material/catalog references in parameters. Revision-component FKs retain the catalog versions. Routes save their duct metadata alongside waypoints. Snapshot publication remains atomic; file writes precede the DB transaction as before.

The same backend geometry drives the editor's static assembly, saved GLB and FreeCAD script. The enclosure consists of separate thin rear/side/top/bottom panels, not a filled solid box. Component meshes include cases, toggles, terminals, screws and copper pieces; ducts have slotted fingers and separate lids. GLB wires are triangle tube meshes. The FreeCAD script creates the same boxes/cylinders and cylindrical wire segments. Native FreeCAD/STEP execution still requires FreeCAD and is not part of the backend worker.

## Verification

From `backend/`, run `PANEL_RUN_POSTGRES_TESTS=1 python -m pytest` (PowerShell: set `$env:PANEL_RUN_POSTGRES_TESTS='1'` first). Integration tests create their own disposable database and asset directory. From `frontend/`, run `npm test` and `npm run build`.

`tests/test_panel_assembly.py` covers real duct reservation/containment, overfill, disconnected network failure, isolated terminals, shell/hardware geometry, GLB triangle wires, generated script syntax and saved hardware projections. Frontend tests cover the door/cover controls and duct inspector. These checks do not exercise a native CAD kernel or prove manufacturing compliance.

### Checked in the development workspace on 2026-10-28

- Backend: 35 tests passed, including the isolated PostgreSQL suite. A Starlette/AnyIO deprecation warning remains.
- Frontend: 24 tests passed; TypeScript and Vite production build passed. Vite still reports the existing large-bundle warning.
- The local database was backed up and its archive listing checked before the additive import. Eleven catalog items and 29 detailed previews were imported without replacing the original JSON fixtures or existing published records.
- A separate project named **Enclosed DB with duct routing** (`PROJ_DB_CABINET_DEMO_001`) was generated for inspection. It has 29 electrical components, six duct sections, ten enclosure accessories and 44 duct-linked routes. Existing projects were not regenerated automatically.
- Windows computer/browser inspection tools could not initialize (`failed to write kernel assets`, OS error 3). Live WebGL appearance was not visually verified in this session; the frontend controls, geometry/export checks and build were verified separately.
