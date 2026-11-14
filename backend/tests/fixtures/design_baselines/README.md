# Deterministic prototype DB references

P0-T03 captures two feasible Distribution Boards and four real failure cases.
These are explicit direct-engine fixtures, not an HTTP runtime fallback or
qualified engineering reference designs. See the
[performance procedure](../../../../docs/verification/performance-baseline.md).

## Evidence boundaries

- `cases.json` supplies all questionnaire values, fixed project identities,
  board sizes, independently calculated expectations and synthetic failure
  geometry. Observed enclosure choices and error messages are labeled as such.
- `db-12.observed.json` and `db-16.observed.json` capture current output: CEM/PDM
  state, component/catalog/terminal lists, net IDs, every connection's endpoints,
  every route's conductor/net/terminal/duct references, and counts. Full output
  is reconstructed by running the pinned engine; it is not stored as a large
  opaque snapshot. SHA-256 covers the entire package and each projection, as
  well as actual GLB and FreeCAD-script bytes, so omitted geometry is still
  protected by exact regression comparison.
- `pins.json` records engine/generator versions, actual Python and geometry
  library versions, complete default solver configuration and raw SHA-256 for
  catalogs, questionnaire, requirements and implementation/model sources. JSON
  fixture catalogs have file hashes instead of fabricated SQL version UUIDs.
  API-generated revisions retain their actual SQL manifest pins in integration
  checks; they are not silently substituted for these fixture-adapter inputs.
- `test_design_baselines.py` checks references, terminal coordinate arithmetic,
  mounting-plate containment, device gaps, duct occupancy and trunk containment,
  schematic/CAD/BOM identity, arithmetic and real failure behavior separately
  from the observed-output hashes. It also compares a second fresh solve and
  asserts zero physical violations, including warnings.

The hand calculation of apparent power is 179.70 kVA. Prototype load factors
give 225 A. The unrounded prototype busbar multiplier gives 312.5 A; the engine
currently reports 312 A due to rounding and selects a catalog busbar above
312.5 A. This observation does not approve rounding an engineering minimum down.
No application behavior was changed for this capture.

An empty physical violation list does **not** resolve missing ampacity,
manufacturer bend-radius or wire-segregation evidence. The tests explicitly
retain current `UNRESOLVED` wire-geometry checks. No manufacturing, thermal-model
applicability, standards, manufacturer data or native CAD certification is given.

## Exact comparisons and deliberate updates

Run from `backend/` using the existing backend virtual environment:

```sh
.venv/bin/python -m pytest tests/test_design_baselines.py -q
.venv/bin/python -m tests.design_baseline_support package db-12
.venv/bin/python -m tests.design_baseline_support capture
```

The package command prints a full generated package. The capture command prints
a proposed **Add File** patch for review; it never applies or overwrites a
baseline. For an intentional update, review the source/pin changes, compare old
and new semantics/artifact hashes, then explicitly edit the existing files with
`apply_patch`. A passing snapshot update alone is not an independent reference
review. Human task acceptance remains separate.

Canonical JSON sorts dictionary keys and uses UTF-8, finite JSON numbers and
compact separators via the existing `canonical_json`. List order, IDs,
coordinates, floats, warnings and unresolved statuses are retained. There are
currently **no nondeterministic timestamps** in direct-engine output, so the
normalization list is empty. No timestamp-like field-name wildcard, UUID
replacement, sorting of arrays, coordinate rounding or elapsed-time filtering
is allowed. New nondeterminism must fail visibly before any narrow timestamp
exception is reviewed. Raw GLB and script bytes receive no normalization.

## Failure cases

| Case | Independent infeasibility | Expected observed behavior |
| --- | --- | --- |
| `placement-too-wide` | 200 mm device > 80 mm usable rail width | CP-SAT placement API returns `INFEASIBLE`, no parts |
| `undersized-fixed-enclosure` | Catalog heat / 0.45 W/L > fixed enclosure's 240 L | `NO_FEASIBLE_ENCLOSURE`, original inputs unchanged |
| `disconnected-ducts` | Left/right duct footprints separated by 140 mm | `RoutePlanningError` retains connection `C` / net `N` |
| `blocked-duct-bridge` | Full-height wall divides otherwise connected ducts | Same structured routing failure; no free-air fallback |

These failures use real solver/router inputs, not injected success/failure
returns. No final PDM, published revision or artifact is expected from them.
Existing PostgreSQL rollback tests independently cover publication atomicity.
