# Aggregate validation contract

P3-T09 adds `aggregate-validation/1` in
[validation.py](../../backend/app/models/validation.py) and the pure
[report service](../../backend/app/services/validation_report.py).
It implements the aggregation boundary documented by the
[academic electrical semantics decision](../decisions/approved-electrical-semantics.md).
Qualified applicability, engineering methods and reference values remain unapproved.

`GET /api/projects/{project_id}/validation` retains `violations`, database `results`
and heat-density fields and adds a typed `aggregate`. This is a current software
interpretation of the hash-verified saved CEM/PDM and saved wire subchecks. It is
not a replacement for the historical validation rows. Reading does not generate,
reroute, modify snapshots, publish a revision or grant engineering release.
There is no request field for supplying applicability approval.

Each check identifies its object and kind, rule ID/version, domain, severity,
requiredness, applicability, rationale, status, freshness and evidence. Numeric
evidence is finite and carries an explicit unit. Groups retain object, rule/version,
severity and applicability; check IDs link each group back to its evidence.
The TypeScript contract and shared fixture live under `frontend/src/types/`.

The general `aggregate_validation` function requires a caller-owned expected rule
inventory. Missing observations, changed rule versions, changed requiredness or
scope cannot become PASS. Unknown result IDs and duplicate identities are rejected.
Old failed observations remain failures; stale passes cannot establish eligibility.
Required FAIL dominates UNRESOLVED; otherwise applicable passes and justified
exclusions yield PASS, and all justified exclusions yield NOT_APPLICABLE. An empty
inventory is UNRESOLVED. Optional failures remain visible without becoming required
failures. Severity never substitutes for requiredness. NOT_APPLICABLE requires a
nonblank recorded rationale, matching applicability and current evidence. The trusted
inventory/review owner must substantiate exclusions; text alone supplies no approval.

The snapshot adapter keeps all C01–C09 engineering families UNRESOLVED with unknown
applicability, including expected scope not enumerable from today's models. It adds
requirement states, calculation/constraint/compliance observations, bounded CEM/PDM
reference checks, all physical violations, the prototype thermal-density screen,
geometry previews and required route subchecks. Missing bend, segregation, dimensions
and virtual earth-anchor evaluations remain UNRESOLVED. A `catalog` string or
positive bend radius does not resolve the broader conductor/engineering family.
Raw unknown statuses and unjustified N/A cannot become PASS; conflicting route
observations become FAIL. Unknown applicability and stale evidence remain blocking.

Version provenance is bounded: saved physical rules use the supplied published rule
version where available, otherwise the saved PDM policy version. Legacy wire checks
use their saved explicit rule version or geometry backend version. Newly derived
structural checks use `prototype-validation/1`; the unresolved C01–C09 inventory uses
`academic-db-inventory/1`. These adapter versions do not invent published catalog
rules or reviewed methods. The response identifies the evaluated saved revision.

The report separates these outcomes:

- `geometric_feasible`: current required prototype physical/envelope checks pass.
- `physical_generation_eligible`: physical evaluation is recorded, all required
  prototype checks pass and the physical violation count is exactly zero.
- `prototype_preview_available`: both conditions above hold.
- `engineering_release_eligible`: preview conditions hold, the required engineering
  aggregate is PASS or justified NOT_APPLICABLE, and a trusted policy review
  reference exists. The runtime snapshot adapter never supplies that reference.

These flags are derived again during model validation. They are eligibility data,
not a certification or signed release. Synthetic policy-review strings in unit
tests exercise the positive branch only; they are not human approvals. The existing
generator and detached physical stages still reject every physical violation,
including warnings, before CAD generation. No thresholds or engineering methods
were relaxed. No CEM/PDM, database, artifact or generator-version change is needed:
saved generation payloads remain unchanged and this additional read projection has
its own explicit schema version. Publication/recompute guards and UI presentation
are outside this task; no new engineering release operation is introduced.
