# Distribution Board and 3D Editor Test Sheet

**Project:** Electrical Panel Design Automation  
**Test date:** __________  **Tester:** __________  **Build/commit:** __________

## Test objective

Verify that a DB design can be generated and inspected, the schematic and 2D editors support their draft interactions, and the 3D editor supports assembly inspection. This is a software demonstration test. It does not certify an electrical design or establish standards compliance.

## Preconditions

1. Start the backend from `backend/` with `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8731`.
2. Start the frontend from `frontend/` with `npm run dev -- --host 127.0.0.1`.
3. Open `http://127.0.0.1:3000/` and generate the default DB design.
4. Confirm the default design reports 29 components and 44 routes.

## Manual acceptance cases

| ID | Test | Steps | Expected result | Result / evidence |
|---|---|---|---|---|
| UI-01 | 2D drawing fit | Open **2D Layout** at a normal desktop size, then resize the browser shorter and taller. | The complete enclosure boundary remains visible, including its top and bottom. The drawing keeps its aspect ratio and fits the available canvas. Toolbar controls remain visible. | __________ |
| SC-01 | Schematic navigation and selection | Open **Schematic**, zoom and pan, drag a symbol, then select a symbol and a wire. | React Flow supports selection, dragging, zoom, and pan. The inspector shows the selected object's stable ID, terminal/net details, and wire electrical class. | __________ |
| SC-02 | Connect terminals and edit wire properties | Drag a connection between two valid terminal handles. Select the new wire, enter a label, and select a wire class. | A labeled draft edge appears, properties update in the inspector, and domain checks flag missing terminals or net labels. The banner identifies the graph as a draft; the CEM/netlist remains unchanged. | __________ |
| SC-03 | Fan-out junction | Inspect a net with three or more terminal endpoints. Add a draft junction and connect two draft wires to it. | Generated fan-out nets display a junction. A junction connected to multiple net IDs produces a rule error. | __________ |
| L2-01 | Drag, snap, and select footprint | Open **2D Layout**, drag one footprint, and toggle snapping/grid size. | The selected footprint follows the pointer in PDM millimetres, snaps to the displayed grid, and the inspector shows its current position. | __________ |
| L2-02 | Rotate, align, and edit properties | Select a footprint; use **Rotate 90°**, **Center X**, and the numeric position fields. | The footprint orientation and position update in the SVG preview; each committed edit requests PDM validation. | __________ |
| L2-03 | Apply placement and inspect warnings | Move a footprint outside the plate or over another, then select **Apply & Validate**. | The frontend PDM receives the edited position/orientation and the backend PDM validator returns structured boundary/overlap/clearance violations. This endpoint validates but does not persist or regenerate routes/BOM/CAD. | __________ |
| ED-01 | Select a component | Open **3D Panel**, select a component in the tree, then click a different component in the viewport. | Selection follows the last action; the selected part highlights and its ID, category, and dimensions appear in the properties inspector. | __________ |
| ED-02 | Move with gizmo | Select a component, choose **Move**, and drag one gizmo axis. | The component moves in the 3D view. With snap enabled, translation aligns to the displayed millimetre grid. | __________ |
| ED-03 | Numeric position | Enter a new X/Y/Z position for the selected component and leave the field. | The component moves to the entered position. With snap enabled, values snap to the selected grid increment. | __________ |
| ED-04 | Rotate | Choose **Rotate** and rotate a selected component, then edit Rotation Z numerically. | The component rotates around its center. With snap enabled, gizmo rotation snaps to 15° increments. | __________ |
| ED-05 | Visibility | Hide a component from the tree, then show it again from the tree or inspector. | The component disappears from and returns to the 3D view; it remains available in the component tree. | __________ |
| ED-06 | Undo and redo | Make a numeric or gizmo transform, use **Undo**, then **Redo**. | Undo restores the prior transform; redo restores the edited transform. | __________ |
| ED-07 | Placement warnings | Move a component over another component, then move it beyond the enclosure boundary. | The inspector reports an overlap or boundary warning and the viewport displays a warning count. | __________ |
| ED-08 | Draft status | Change a component transform and inspect the banner. Then choose **Reset**. | 3D changes remain local viewing drafts; reset restores the generated 3D positions and clears undo history. | __________ |
| ED-09 | FreeCAD export boundary | With a local draft edit present, open **BOM & Traceability** and request the FreeCAD script. | The script is still generated from the backend-validated PDM, not the local 3D draft; this limitation is disclosed in the 3D editor. | __________ |

## Automated checks

Run these commands from the indicated directories:

```powershell
cd backend
python -m pytest
```

```powershell
cd frontend
npm test
npm run build
```

Automated coverage includes DB requirement validation and generation, route identity and obstacle avoidance, impossible-route errors, physical bounds/collision/terminal checks, PDM placement API validation, CAD/PDM identity, React Flow graph mapping/rules, responsive SVG sizing, 2D PDM placement submission, camera reframing, editor geometry warnings, and transform undo/redo.

## Test summary

**Passed:** ______  **Failed:** ______  **Blocked:** ______

**Notes / screenshots:**

______________________________________________________________________________

______________________________________________________________________________
