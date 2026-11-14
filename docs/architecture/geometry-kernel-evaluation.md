# Bounded native geometry evaluation

P0-T05 · cad_kernel_engineer · 2026-11-13 · investigation complete; human acceptance pending.

## Result and scope

Recommend **an out-of-process, pinned headless FreeCAD adapter**, consuming the
existing shared primitive contract, subject to correcting the failed native
reference case before adoption. Retain
the current GLB preview path. This is a bounded spike, not a production worker
implementation, kernel adoption approval or supported-platform declaration.

**Attempt 02 executed native export/reopen; `native_cad` FAILS.** The pinned
FreeCAD runtime exported STEP and a fresh process reopened 42 valid solids in
mm, but the rotated mounted part is displaced by −30 mm X / −10 mm Y relative
to PDM. Maximum bound error is 30 mm against the unchanged, human-approved
0.05 mm reference-test tolerance. P0-T05-NATIVE-001 now blocks later native
implementation on this demonstrated exporter transform defect and a passing
rerun, rather than an absent runtime. See the
[attempt-02 report](../../planning/task_reports/P0-T05/attempt-02.md) and
[retained native review](../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/review.json).
No production geometry, lifecycle state or tolerance was changed; no later task
was executed. Local evaluation authorization does not approve distribution.

**Attempt 03 completes the evidence investigation and blocker registration.**
The current P0-T05 contract requires `document_review`; a failing native experiment
is a research outcome. The retained native result remains **FAIL**, and new native
execution in attempt 03 is **NOT_RUN** because the existing evidence is sufficient.
P5-T00 must pass before subsequent native implementation proceeds. Completing
this investigation qualifies neither native geometry nor distribution nor an
engineering release. Task acceptance and all human approvals remain human-owned.

### Evidence review through attempt 03

| Evidence | Reviewed outcome / status |
| --- | --- |
| [Attempt 01](../../planning/task_reports/P0-T05/attempt-01.md) and frozen [observation](../../backend/tests/fixtures/cad_reference/observation.json) | Native **NOT_RUN**: no discovered runtime at that time. Script/GLB inspection was non-native. Preserved unchanged. |
| [Attempt 02](../../planning/task_reports/P0-T05/attempt-02.md), [run-01](../../planning/task_reports/P0-T05/evidence-attempt-02/run-01/failure.json), [run-02](../../planning/task_reports/P0-T05/evidence-attempt-02/run-02/failure.json), [run-03](../../planning/task_reports/P0-T05/evidence-attempt-02/run-03/failure.json) | Preserve initialization SIGSEGV and missing-report failures, including stderr and controller/process records. Later successful serialization does not erase these failures. |
| [Run-04 review](../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/review.json), [STEP](../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/panel_model.step) and [failure](../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/failure.json) | Native **FAIL**: export/reopen process exits 0 and 42 valid solids, but mounted bounds fail by 30 mm against 0.05 mm. Two failed bounds checks remain failed. |
| [Attempt 03](../../planning/task_reports/P0-T05/attempt-03.md) and [review evidence](../../planning/task_reports/P0-T05/evidence-attempt-03/document-review.json) | Read-only rehash/comparison of prior reports, raw evidence, source pins, archive, selected runtime files and notice inventory; independent mounted-bound derivation; downstream-owner and document checks. No native process launched and no new native PASS. |

The current read-only [lifecycle](../../planning/development_lifecycle.json)
assigns correction/qualification to P5-T00. Its attempt-01 source hash in
`observation.json` is historical: that lifecycle was already changed before
attempt 03. The other eleven frozen source/input pins still match. Preserve the
old observation and reports, including their earlier PARTIALLY_COMPLETED
assessments; the new investigation contract does not retroactively qualify their
native result. The [preservation manifest](../../planning/task_reports/P0-T05/evidence-attempt-03/preservation-manifest.json)
records the workspace as received, including existing unrelated changes.

## Implementation evidence

Read root AGENTS.md and searched for nested AGENTS/override files; none applied.
Read the lifecycle task, CAD specialist responsibilities and verification profile,
P0-T03 evidence, [current contracts](current-contracts.md),
[operation proposal](document-operation-adr.md) and
[assembly documentation](../PANEL_ASSEMBLY.md), then checked source:

| Source | Actual contract / limitation |
| --- | --- |
| [cad_engine.py](../../backend/app/services/cad_engine.py) | Generates BOX/CYLINDER/TUBE descriptors and nonrendered ENVELOPEs. Routes require geometry status PASS for script export. Script creates FreeCAD `Part::Feature` objects and calls `Part.export(..., 'panel_model.step')`; backend does not run it. Object names `PanelPart_<primitive index>` omit CEM/PDM/route identity. No STEP schema/unit preferences, worker pin, reopen, resource accounting or timeout are supplied. |
| [panel_geometry.py](../../backend/app/services/panel_geometry.py) | Enclosure is separate thin panels/returns, not a solid block or fused watertight enclosure. Backplate and duct/rail/accessory geometry are shared with previews. Part positions are transformed from local lower-corner coordinates about the component's XY centre. |
| [PDM](../../backend/app/models/pdm.py), [wire geometry](../../backend/app/services/wire_geometry.py) | Coordinates and diameters are mm. Saved polyline is authoritative; geometry centerline samples circular fillets. CAD pipe follows that sampled polygon with `makePipeShell(..., True, False, 2)`. A shape check cannot resolve ampacity, segregation or missing manufacturer data. |
| [assets.py](../../backend/app/persistence/assets.py) | GLB triangle tubes, metre positions/translations, original axes and primitive extras. `conductor_id` is omitted from GLB extras although present on CAD TUBE; route/net IDs survive. GLB is not BREP/STEP. |
| [project service](../../backend/app/services/project_service.py), [main.py](../../backend/app/main.py), [CAD routes](../../backend/app/api/routes_cad.py) | Revision artifacts are GLB/PY, with content hashes and generator pins. Current queued work is an in-process one-thread executor, not a native subprocess; startup fails all PENDING artifacts. A native crash in this process would have no process boundary. Read transactions close before the normal geometry/file-generation path; final publication is short and transactional. |
| [panel-backend.spec](../../backend/panel-backend.spec), [Tauri config](../../frontend/src-tauri/tauri.conf.json), [requirements](../../backend/requirements.txt) | PyInstaller declares empty explicit binaries/data and no kernel-specific hook. Requirements contain no FreeCAD/pythonocc/OCP. Tauri packages only `binaries/panel-backend`, targets `all`; that does not establish kernel bundling or cross-platform operation. |

The older assembly prose describes cylindrical wire segments and migration
`0002_app`; current script uses a pipe shell and repository head is
`0004_projects`. Those historical claims are not used as evidence for native CAD.
No production source, dependency, schema, generator version or lifecycle file was
changed. Existing published geometry/artifact hashes remain untouched.

## Three adapter paths on the same coupon

The [reference directory](../../backend/tests/fixtures/cad_reference/README.md)
contains one synthetic enclosure/backplate, one mounted box and one routed wire
through a duct. It deliberately avoids claiming a generated feasible DB. P0-T03
already supplies full-board identity/physical reference fixtures; this coupon
isolates coordinate, serialization and kernel questions.

| Question | Existing emitted script | Pinned headless FreeCAD subprocess (recommended) | Direct OCCT alternative |
| --- | --- | --- | --- |
| Shapes | Shared panel boxes/cylinders and sampled-wire pipe shell | Reuse exactly those descriptors and current script initially; explicit validation/export/reopen wrapper | Rebuild boxes/cylinders with `BRepPrimAPI`; transformed shapes with `gp_Trsf`; polygon spine plus `BRepOffsetAPI_MakePipeShell`; check with `BRepCheck_Analyzer` |
| STEP and assemblies | User executes `Part.export`; no native evidence | Explicit mm export; fresh-process `Part.read` for geometric qualification; later identity-aware exporter must retain stable labels/sidecar | `STEPControl_Writer/Reader` for geometry; XDE/`STEPCAFControl` needed for named assembly structure and metadata |
| One enclosure | Separate sheet solids, no face fusion needed | Preserve sheet/part identities; do not fuse incidental contacts | Same separate shapes; own grouping/XDE implementation |
| One mounted part | Intended local-centre rotation is incorrect natively: replacing Placement.Rotation retains the preceding centring translation | Independent bounds check detects −30/−10 mm displacement in this coupon; block adoption pending reviewed correction | Own transform adapter; independently verify pivot and translation |
| One routed wire | PASS sampled centreline → circular profile → solid pipe; rejects null/invalid wire | Same geometry first; measure sweep/reopen and failures; analytic elbow conversion requires a new reviewed generator/version | Same sampled spine possible, but transition settings, tolerances and error mapping require independent implementation |
| Isolation | Script serialization is Python work; manual external execution unspecified | Fresh OS process per job; kill/restart can preserve API process and prior revision if supervisor/publication are implemented correctly | Also needs a subprocess; direct in-process OCCT binding would expose API to native crash |
| Packaging | No native runtime supplied | Large separate runtime plus Qt/OCCT/loader dependencies, pinned independently of backend Python | Smaller surface in principle, **unmeasured**; either C++ executable/toolchain or a Python binding and matching interpreter |
| Evidence through attempt 02 | Actual emitted script executed unchanged | STEP retained and reopened; units/count/validity/roundtrip checks pass, mounted bounds fail; timing/RSS below | Source/API comparison only; no direct OCCT export/reopen or performance result |

The lower implementation distance makes FreeCAD the preferred first adapter.
This is an engineering inference from the existing exporter, not a benchmark
claim. Both native candidates use OCCT; changing wrappers does not guarantee
better sweep robustness. Direct OCCT remains a fallback only if the same coupon
demonstrates an unacceptable FreeCAD packaging or execution constraint.

## Exact inspected qualification environment

Use the official **FreeCAD 1.0.2 Linux x86_64 conda Python 3.11 AppImage**, not a
floating system package or the backend virtual environment. This historical
version is a concrete spike baseline, not a claim of latest or release suitability.
The [upstream release assets](https://github.com/FreeCAD/FreeCAD/releases/expanded_assets/1.0.2)
list `FreeCAD_1.0.2-conda-Linux-x86_64-py311.AppImage`, approximately 759 MB,
SHA-256 `e00be00ad9fdb12b05c5002bfd1aa2ea8126f2c1d4e2fb603eb7423b72904f61`.
The digest pins the archive's transitive runtime bytes. Attempt 02 downloaded
795,892,216 bytes and verified the official checksum before executing extraction.
The separate user-owned install is
`/home/jacobGM/.local/share/panelflow-tools/freecad-1.0.2/squashfs-root`.
The verified launcher is `AppRun freecadcmd`; `AppRun` dispatches its first
argument to `usr/bin/freecadcmd`. AppRun SHA-256 is
`494eae855763bd526099415b9fa9128c6d2240bf079b9cc4428d2fcfc882d8c1`;
the ELF command SHA-256 is
`7f642d5b0acc4d3dce8259cb5f82c444e6dc9aaa99ca191d543b5dd01e9002d0`.
It ran without FUSE or a display, with `QT_QPA_PLATFORM=offscreen` and no
DISPLAY/WAYLAND_DISPLAY. AppRun sets PYTHONHOME/PATH_TO_FREECAD_LIBDIR to its own
`usr`/`usr/lib`; no LD_LIBRARY_PATH override was needed. ELF RPATH is
`$ORIGIN/../lib`; the host glibc/ELF loader remains a dependency.

First qualification host target is the actual inspected host: Arch Linux
x86_64, kernel `7.2.11-arch1-1`, glibc 2.44, Intel i3-1115G4 (2 cores/4 threads),
7,945,617,408 bytes RAM. Human authorized this workstation for local evaluation;
this is not a clean-install or general supported-OS qualification. Backend controller uses its existing
`backend/.venv/bin/python`, CPython 3.14.8, GCC 16.2.1. Native children must use
the archive's own Python 3.11 ABI. Actual native reports identify FreeCAD
1.0.2 R39319, commit `256fc7eff3379911ab5daf88e10182c509aa8052`, embedded Python
3.11.13 (conda-forge, GCC 13.3.0), OCCT 7.8.1 and Qt 5.15.15. `/proc/self/maps`
confirms bundled libpython3.11, libTKernel 7.8.1, Qt5Core 5.15.15 and
libstdc++.so.6.0.34. `packages.txt` reports libstdcxx/libgcc 15.1.0 and
PySide2 5.15.15. Retained review hashes launcher, interpreter, loaded libraries
and package inventory; these are inspected values, not filename inferences.
Windows/macOS/ARM need distinct qualified artifacts;
no result here applies to them.

For the direct alternative, a concrete source baseline is
[pythonocc-core 7.8.1.1](https://github.com/tpaviot/pythonocc-core/releases/tag/7.8.1.1),
which explicitly requires OCCT 7.8.1, in a separate Python 3.11 worker on the same
Linux x86_64 target. No binary/build digest or compatible package solve has been
verified; it is not an installable lock or qualified alternative. A direct C++
OCCT 7.8.1 executable would remove Python/SWIG but add a toolchain and owned XDE
serialization code. None is linked into FastAPI in this recommendation.

## Units, transforms and stable identity

| Boundary | Required mapping |
| --- | --- |
| PDM → native | Required: right-handed enclosure XYZ, dimensions/coordinates mm, no axis swap. Do not add mounting-plate offset to already placed world coordinates. Centre local primitives, apply quaternion `(x,y,z,w)` about local centre, then world translation. Current script violates the rotation pivot mapping as demonstrated below. CYLINDER axis is +z before rotation. |
| Plate → mounted coupon | Plate origin `(30,30,12)`; 3 mm sheet ends at z=15. Coupon lower corner `(80,100,15)`, size `(20,40,30)`, rotation 90°, centre `(90,120,30)`; bounds `(70,110,15)` → `(110,130,45)`. Its terminal `(10,0,15)` maps to `(110,120,30)`. |
| Wire → native | Consume saved PASS `geometry.centerline` and diameter 3 mm, radius 1.5 mm; do not smooth/refit or reroute in the adapter. Preserve route `ROUTE-CONN-REFERENCE`, conductor/connection `CONN-REFERENCE`, net `NET-REFERENCE`, endpoint component/terminal pairs, duct references and geometry ID. Virtual earth anchor stays UNRESOLVED. |
| PDM → GLB | Divide mm by 1000 once for positions and translations; preserve the same axes/quaternion. Coupon centre becomes `(0.09,0.12,0.03)` m. GLB solids/facets are preview data, not kernel topology. |
| Object identity | Key native occurrence by stable primitive `id`; carry `pdm_component_id`, `cem_component_id`, `assembly_group`, hardware/rail/duct `object_id`, route/net/conductor and source terminal pairs in a manifest. One electrical part may own many primitive/native solids. Never equate solid count with component count. |
| STEP identity | Proposed application-owned assembly root is `panel_id` with enclosure/plate/part/duct/wire occurrences. Use deterministic safe native names plus full original IDs in labels/custom properties and a hash-bound sidecar. Current sequential names and geometric nearest-match cannot establish stable identity on reopen. STEP labels/XDE round-trip is unverified and blocks an identity-complete adapter. |
| Revision/artifact identity | Bind request/result to saved revision ID, PDM SHA-256, catalogue/model pins, generator/adapter version, runtime/archive hash and export options. Retain verified STEP and sidecar in the managed content-addressed asset store through existing publication conventions. Proposed request/result contract only; no endpoint or new artifact enum implemented. |

Topology face/edge indices are not stable engineering identifiers. Selection in
future native output needs a reviewed occurrence mapping, never face enumeration
or STEP entity numbers. CAD cannot alter connectivity, terminals or engineering
placement, and native validity cannot override the saved strict physical policy.

## Reproducible evidence and qualification checks

Actual commands and exits are in the
[attempt-02 report](../../planning/task_reports/P0-T05/attempt-02.md);
[attempt 01](../../planning/task_reports/P0-T05/attempt-01.md) is preserved.
`reference.json` and `observation.json` retain attempt-01 inputs/pins, including
historical status fields. Native execution evidence is from attempt 02. The native
helper now retains artifacts in an exclusive new directory and supports the
upstream AppRun dispatch argument. Five focused tests pass, including failed
child evidence retention and refusal to overwrite a prior run.

Non-native observed output: 41 boxes + 1 tube, 42 rendered/export solids; one
extra ENVELOPE omitted from solid count. Bounds `(0,0,0)` → `(300,400,150)` mm;
plate/device transforms, route endpoints, radius, trunk containment and GLB
metre translation checked independently. The 6 mm ideal quarter-circle
centreline length is 147.424777961 mm; sampled length is 147.418050609 mm.
Actual script is 10,491 bytes, GLB 68,928 bytes; hashes are recorded in the
observation. Compilation is syntax evidence, not STEP evidence.

For qualification, use a fresh scratch cwd and profile, export the actual
repository script, terminate that process, and open only the resulting STEP in
a second process. Assert explicit STEP mm units, exactly 42 valid solids,
independent assembly/part/wire bounds, unchanged STEP hash, and matching
per-solid bounds/volumes. Also inspect named assembly/occurrence identities;
the current helper only produces a source-name sidecar and geometric matching,
so it cannot pass identity qualification. Retain STEP bytes and both process
reports as reviewable evidence. Same-kernel fresh-process reopen is independent
of the PDM/exporter's memory; it is not independent-kernel interoperability.

Human approved these geometric reference-test tolerances in the attempt-02
conversation: bounds 0.05 mm; sampled length 0.02 mm;
round-trip volume relative 1e-6, absolute floor 1e-6 mm³; exact counts/identity;
every solid valid. Approval is for this synthetic test only, not manufacturing
values, distribution or changes to PDM clearance/thermal/fill policy. The frozen
reference's original approval-status string is historical; its numbers and hash
remain unchanged. No tolerance was relaxed after failure.

### Attempt-02 native observations

[STEP](../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/panel_model.step),
[export report](../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/export.json),
[fresh-process reopen report](../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/reopen.json)
and process logs are retained locally under the ignored planning evidence
directory; they are not committed/runtime assets or published revision artifacts.
STEP is 281,382 bytes, SHA-256
`cb534278e53908d3697ae50af508c15cfe21ea8cc8a2796193fb71c725b65c80`, AP214
(`AUTOMOTIVE_DESIGN`), explicit SI milli/metre units. Both native children exit 0;
controller exits 1 because independent mounted-part bounds fail. Reports have
distinct native PIDs 19076/19084. No PDM/BREP is read by reopen mode.

| Check | Export / reopen result |
| --- | --- |
| Units, counts, validity | mm; 42 solids each, all valid; unfused assembly compound valid |
| Assembly bounds | `(0,0,0)` → `(300,400,150)` mm, exact |
| Backplate bounds | `(30,30,12)` → `(270,370,15)` mm, exact |
| Wire bounds | `(110,118.5,28.5)` → `(161.5,220,31.5)` mm, exact |
| Mounted-part bounds | **FAIL:** actual `(40,100,15)` → `(80,120,45)` mm; expected `(70,110,15)` → `(110,130,45)` mm |
| Per-solid export/reopen | Bounds unchanged; maximum volume delta 3.02098e-6 mm³, relative 2.89912e-9, within unchanged limits |
| Stable named assembly IDs | **UNVERIFIED:** Part.read plus geometric matching does not qualify semantic identity; ordinal names/sidecar remain |

The [bundled-runtime rotation probe](../../planning/task_reports/P0-T05/evidence-attempt-02/rotation-probe.json)
reproduces the defect without the application. `shape.translate(-half_dimensions)`
sets Placement.Pos to `(-10,-20,-15)`. Assigning Placement.Rotation to 90°
retains that translation, rotating the original box about its original origin.
Adding `(90,120,30)` produces native centre `(60,110,30)` instead of the intended
`(90,120,30)`. The STEP faithfully preserves this already misplaced solid.
GLB uses centred vertices and passes the non-native reference, so roundtrip
validity/overall bounds alone would miss this native/PDM discrepancy. No exporter
fix or replacement geometry was introduced within this spike.

| Measurement / failure check | Retained attempt-01/02 evidence | Required next evidence |
| --- | --- | --- |
| Script/GLB conversion | One diagnostic in-process sample in observation; imports/startup excluded from interval, process RSS includes imports | Repeated cold/warm samples with retained raw values if performance acceptance is sought |
| Native export/reopen elapsed time and peak RSS | Export: operation 250.945 ms, process 410.769 ms, 116,148 KiB. Reopen: operation 273.047 ms, process 414.301 ms, 100,724 KiB | One sequential diagnostic sample only; operation excludes startup/imports, process includes AppRun/initialization/shutdown; no cold/warm percentile or performance acceptance |
| Native package disk/RAM footprint | Archive 795,892,216 B; extracted regular files 3,077,994,822 B; `du -sk` 3,107,020 KiB; native peaks above | Idle baseline not measured; host page cache, other workloads and CPU frequency uncontrolled; no numerical resource promise |
| Malformed input, invalid sweep, timeout, native crash/OOM | Sandbox startup SIGSEGV observed (run-01), controller survived and retained logs. Escalated CLI initialized. Other injections **UNEXECUTED** | Startup-only observation is not production isolation qualification; no API/DB prior-revision exercise, memory/CPU/output limits or crash/OOM/timeout supervisor verification |
| Desktop/OS distribution | **UNEXECUTED** | Supported-OS install/run/signing, loader dependencies, runtime provenance and license inventory |

## Packaging, licenses and isolation boundary

Package the kernel as a separate, versioned runtime/worker from `panel-backend`,
with an explicit runtime discovery/health check. Do not rely on PyInstaller
auto-discovery of native modules, inject its ABI into backend Python, or assume
Tauri's current single externalBin includes it. Release packaging, code signing,
notices and per-platform loaders remain open. No `.spec`/Tauri change is made.

Upstream [FreeCAD 1.0.2 source headers](https://raw.githubusercontent.com/FreeCAD/FreeCAD/1.0.2/src/App/FreeCADInit.py)
state LGPL version 2 or later; its [LICENSE](https://raw.githubusercontent.com/FreeCAD/FreeCAD/1.0.2/LICENSE)
includes the relevant license texts. OCCT's pinned source provides
[LGPL 2.1](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_8_1/LICENSE_LGPL_21.txt)
and an [additional exception](https://raw.githubusercontent.com/Open-Cascade-SAS/OCCT/V7_8_1/OCCT_LGPL_EXCEPTION.txt).
The direct Python alternative adds the binding's own
[LGPL 3 license](https://raw.githubusercontent.com/tpaviot/pythonocc-core/7.8.1.1/LICENSE).
These source observations are not distribution clearance. The actual AppImage
identifies OCCT 7.8.1. Attempt-02 review retains hashes of 2,011 files whose names
include license/licence/copying/copyright; this is a discovery index, not a
complete license/SBOM audit. `packages.txt` includes FFmpeg 7.1.1 build
`gpl_h127656b_906`, and the archive includes Qt third-party notices and PySide2
LGPLv3/GPL license texts. FreeCAD's own license does not describe every bundled
component. A human
must review that exact runtime, notices/source availability and distribution
approach before shipment; using a subprocess does not itself settle licensing.

Proposed production isolation: trusted adapter code accepts validated finite,
bounded descriptors, no client Python/filesystem paths; child has private scratch,
minimal environment, no DB credentials/network, bounded output/resources and
hard timeout. Supervisor verifies successful exit, version/input hashes, output
units/validity/identity and fresh reopen before staging managed assets. Publish
through a short existing revision-bound transaction; stale/cancelled/failed
results cannot advance the current revision or mutate historical snapshots.
Return structured sanitized errors. A worker process alone is not a sandbox,
and this spike's helper implements none of those production
security/publication guarantees. Durable jobs/leases remain later work.

## Decision and unresolved prerequisites

All issues below remain **OPEN**. Owners and task IDs come from the read-only
[lifecycle](../../planning/development_lifecycle.json); this register assigns no
human authority and marks no downstream task as executed or accepted.

| Issue / present evidence | Mandatory downstream task and owner | Required closure evidence |
| --- | --- | --- |
| **P0-T05-NATIVE-001** — exporter centring/rotation pivot; native **FAIL**, mounted bounds displaced by 30 mm | **P5-T00**, `cad_kernel_engineer`: correct exporter pivot mapping and qualify the native reference; prerequisite of adapter-contract task P5-T01 | Independently derive box/cylinder centre transforms; cover zero/nonzero rotation; review generator/version and historical compatibility; retain pinned native export plus fresh-process STEP reopen passing unchanged expectations and human-approved tolerances. Keep the prior failed STEP/reports. Missing runtime or failing geometry prevents closure. |
| **P0-T05-IDENTITY-001** — ordinal native names, missing GLB `conductor_id`; semantic STEP occurrence identity **UNVERIFIED** | **P5-T05 / P5-T06**, `cad_kernel_engineer`: identity-preserving previews and revision-bound STEP/reopen | Stable primitive/PDM/CEM/connection/route/terminal mapping, explicit mm/metre transform, GLB picking consistent with PDM/STEP instances, named assembly/occurrence roundtrip and revision/runtime/model/hash lineage. Sidecar/geometric matching alone cannot pass semantic identity. |
| **P0-T05-ISOLATION-001** — one diagnostic subprocess failure boundary; production crash/timeout/OOM handling **UNVERIFIED** | **P5-T02**, `cad_kernel_engineer`: isolated native worker, integrated with the lifecycle's job runner | Bounded structured jobs, deadlines/resources/output, cancellation/retry/fencing, missing/crashed/timed-out kernel errors, redacted logs; API survival and no partial publication or damage to the prior revision. Current thread executor and spike helper do not establish these guarantees. |
| **P0-T05-DISTRIBUTION-001** — archive provenance/notice index observed; redistribution and supported-platform operation **UNVERIFIED** | **P7-T03**, `security_release_engineer`: packaging for approved platforms; distribution/platform approval remains human-owned | Full runtime/dependency/license and redistribution review (including Qt/PySide/FFmpeg), approved platform artifacts, clean install/signing, database readiness, sidecar/worker start/stop and no orphan processes. Local evaluation permission and notice hashes do not authorize shipment. |

P5-T00 must pass before subsequent native implementation proceeds; only its
separately authorized correction/qualification work may address the demonstrated
defect. P0 scope approval cannot clear this gate. A later P5-T00 pass will close
the pivot issue only; semantic identity, isolation and distribution retain their
own mandatory gates. None is executed as part of P0-T05.

Recommendation and prerequisite evidence are ready for human review. Neither
this document nor the attempt report changes lifecycle acceptance or authorizes
implementation of a later task.
