# P0-T05 bounded CAD reference

This is a **synthetic geometry coupon**, not a feasible generated DB, a catalog
part, an electrical reference or an approved enclosure construction. No database,
catalog import, CP-SAT placement, DuctRouter run or revision publication occurs.
The P0-T03 full-board fixtures remain separate and unchanged.

`reference.json` defines one 300 × 400 × 150 mm enclosure, its backplate, one
plate-mounted 20 × 40 × 30 mm box rotated 90° about z, one vertical duct and
one hand-defined duct route. The source terminal is independently transformed
from component-local coordinates. The destination is an explicitly synthetic
`PANEL_ROOT:EARTH_STUD` anchor, **not** a verified cabinet termination. Wire
geometry is built through the existing `build_wire_geometry`; original routing
status and unresolved electrical checks remain intact. A geometry `PASS` only
permits the existing CAD exporter to consume that sampled centerline.

The 42 separate, unfused solids are seven enclosure sheets/returns, one
backplate, 32 duct pieces (base, 30 fingers, cover), one mounted box and one
wire sweep. `ENVELOPE` is not a solid. Independent expectations include overall,
backplate, rotated-device and wire bounds, terminal endpoints, bend radius and
the ideal arc length `50 + 100 - 2*6 + pi*6/2`. The current sampled centerline
is shorter by about 0.00673 mm. Its native export remains a sweep along sampled
edges; this fixture does not turn it into an exact analytic circular elbow.

## Local checks

From `backend/`, with the existing backend interpreter:

```sh
.venv/bin/python -m tests.fixtures.cad_reference.spike inspect
.venv/bin/python -m pytest tests/test_cad_reference.py -q
```

Inspection compiles the current emitted FreeCAD script without executing it,
generates actual GLB bytes and checks independent bounds, offsets, endpoints,
IDs and metre conversion. `observation.json` records attempt 01's environment,
hashes and one diagnostic time/memory sample. These are **non-native** results;
they do not measure FreeCAD, STEP, startup time or native peak memory. The
inspection helper and its RSS interpretation target Linux only.

## Native experiment, attempt-02 qualification failure

The pinned target and its upstream archive SHA-256 are in `reference.json`.
Attempt 02 downloaded and verified that official archive before extraction into
`/home/jacobGM/.local/share/panelflow-tools/freecad-1.0.2/`. Its verified dispatch
is `squashfs-root/AppRun freecadcmd`: FreeCAD 1.0.2 R39319, embedded Python
3.11.13, OCCT 7.8.1, Qt 5.15.15. Runtime provenance and library hashes are retained
in the evidence linked below. Backend/orchestrator environments were not altered.
The reference's original absent-runtime/approval status fields and observation
remain historical attempt-01 evidence; the reference numbers/hash are unchanged.

This opt-in command runs from `backend/`. Choose a **new** evidence directory for
each run; an existing directory is rejected, including a failed run's directory.
This host required normal execution escalation for FreeCAD initialization:

```sh
.venv/bin/python -m tests.fixtures.cad_reference.spike native --freecad-command /home/jacobGM/.local/share/panelflow-tools/freecad-1.0.2/squashfs-root/AppRun --launcher-arg freecadcmd --evidence-dir ../planning/task_reports/P0-T05/evidence-attempt-02/run-05
```

The path is the inspected local archive launcher; `run-05` is an unexecuted
example directory (actual retained execution is `run-04`). The helper runs
the actual current script in one process, then opens only its STEP file
through `Part.read` in a second process. It requires FreeCAD 1.0.2 / Python 3.11,
42 valid solids, explicit STEP millimetre units, unchanged file hash, independent
assembly/device/wire bounds, and matched per-solid bounds/volumes after reopen.
It records FreeCAD/OCCT/Python versions, STEP size/hash, operation and process
wall times, and Linux per-process peak RSS. Reopen independence means a fresh
process reading serialized STEP; it is **not** a second vendor's kernel.

Each child gets a scratch cwd/profile, no shell and a 60-second timeout with
process-group termination. This is a trusted local experiment, **not** a network,
filesystem, memory or untrusted-script sandbox. It inherits the invoking process
environment except Python/venv/display variables, which are removed from the
child environment before AppRun selects its own runtime. Sandbox initialization
SIGSEGV was observed and retained in run-01; outside the sandbox the CLI ran.
No deliberate native crash/OOM/timeout injection was executed. Production
resource limits, sanitized environment, supervision and publication are later
implementation responsibilities, not delivered here.

The helper retains STEP, source script, reference copy, sidecar, raw reports,
process commands/times/exit codes and stdout/stderr, including failures. It prints
a JSON result only when its checks pass; exit zero alone from FreeCAD is not
sufficient because FreeCADCmd can swallow script exceptions. Missing reports
fail the controller. FreeCADCmd uses a module name other than `__main__`; the
worker's explicit environment guard executes once and handles built-in FreeCAD
modules without a `__file__` attribute. It does not publish
assets or write revision/artifact rows. The existing sequential FreeCAD names
are mapped to source primitive IDs in a printed sidecar; STEP round-trip identity
preservation is **unverified**, and geometric matching cannot establish it.

Human approved the unchanged reference-test bounds tolerance 0.05 mm, sampled
length tolerance 0.02 mm and
round-trip volume relative tolerance 1e-6 (absolute floor 1e-6 mm³). Counts and
IDs are exact, all solids must be valid. Approval is for this synthetic test
only, not manufacturing tolerances or a weakened physical policy. Named STEP
identity is still unverified. External licensing/distribution review remains
pending; local evaluation permission does not authorize shipment.

Attempt 02 exported/reopened 42 valid solids, mm units, AP214 STEP and unchanged
per-solid bounds/volumes. **The native profile FAILS**: mounted bounds are
`[40,100,15,80,120,45]`, expected `[70,110,15,110,130,45]`, maximum error 30 mm
against 0.05 mm. The emitted script retains the centring translation when
replacing Placement.Rotation, so it rotates around the wrong pivot. The native
wire/backplate/assembly checks pass. Neither tolerances nor production geometry
were changed to conceal this discrepancy.

Raw [STEP](../../../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/panel_model.step),
[export](../../../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/export.json),
[reopen](../../../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/reopen.json)
and [review/provenance](../../../../planning/task_reports/P0-T05/evidence-attempt-02/run-04/review.json)
are persistent local evidence in the ignored planning directory. They must be
preserved with the report for human review; they are not managed application assets.
`review_native.py` rechecks raw files without loading FreeCAD and writes a new
exclusive `review.json` (exit 1 for the demonstrated reference failure):

```sh
.venv/bin/python -m tests.fixtures.cad_reference.review_native --evidence-dir /absolute/path/to/new-retained-run --runtime-dir /home/jacobGM/.local/share/panelflow-tools/freecad-1.0.2
```

That review command already ran for `run-04`; rerunning it against that directory
refuses to overwrite the retained review.

## Attempt-03 review and mandatory qualification handoff

The evidence investigation is complete under the current P0-T05 contract, pending
human task acceptance. Attempt 03 reviews retained evidence without launching
FreeCAD or changing this fixture, expectations, tolerances or prior results.
Its new native execution status is **NOT_RUN**; the retained attempt-02 native
result remains **FAIL**, with 30 mm mounted-bound error against 0.05 mm.
P5-T00 must pass before subsequent native implementation proceeds. Completing
P0-T05 qualifies the investigation only; native geometry, distribution and an
engineering release remain unqualified.

| Open issue | Mandatory downstream task / owner | Handoff |
| --- | --- | --- |
| P0-T05-NATIVE-001 | **P5-T00**, `cad_kernel_engineer` | Correct box/cylinder pivot mapping; zero/nonzero rotation regressions, generator/version compatibility review, pinned export and fresh-process reopen. Preserve expected mounted bounds `[70,110,15,110,130,45]`, all approved tolerances and prior failed artifacts. Close only on passing native evidence. |
| P0-T05-IDENTITY-001 | **P5-T05 / P5-T06**, `cad_kernel_engineer` | Qualify persistent source IDs across GLB picking, PDM and named STEP instances, including conductor/route references and revision lineage. Existing sidecar/geometric matching is insufficient. |
| P0-T05-ISOLATION-001 | **P5-T02**, `cad_kernel_engineer` | Qualify production resource limits, crash/timeout/cancellation, fenced retries, sanitized errors, API survival and preservation of the prior revision. |
| P0-T05-DISTRIBUTION-001 | **P7-T03**, `security_release_engineer`; human distribution/platform approval | Complete dependency/license review, approved-platform install/signing and sidecar/worker lifecycle checks. Local runtime permission does not permit redistribution. |

See the full closure criteria in the
[evaluation register](../../../../docs/architecture/geometry-kernel-evaluation.md#decision-and-unresolved-prerequisites).
These owners/tasks are verified against the read-only
[lifecycle](../../../../planning/development_lifecycle.json); none is executed here.
The reference's historical `BLOCKED_NATIVE_RUNTIME_ABSENT` and proposed-tolerance
status strings remain unchanged. Attempt 02 records the later runtime observation
and human tolerance approval; attempt 03 grants no new approval. The lifecycle's
old source pin is also historical after pre-existing lifecycle reconciliation;
the other eleven pins match current sources.

The [preservation manifest](../../../../planning/task_reports/P0-T05/evidence-attempt-03/preservation-manifest.json)
and [document review](../../../../planning/task_reports/P0-T05/evidence-attempt-03/document-review.json)
record hashes and static checks. All prior reports, run-01 through run-04 failures,
STEP, raw/process reports, logs and rotation probe are preserved. No native rerun
is needed to register the demonstrated defect. Any later native run requires
local runtime permission and a new exclusive evidence directory.

See the [evaluation](../../../../docs/architecture/geometry-kernel-evaluation.md)
and [attempt-03 report](../../../../planning/task_reports/P0-T05/attempt-03.md).
The [attempt-02 report](../../../../planning/task_reports/P0-T05/attempt-02.md) and
the [earlier report](../../../../planning/task_reports/P0-T05/attempt-01.md) remain unchanged.
