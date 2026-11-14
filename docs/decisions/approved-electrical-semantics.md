# D02 — Bounded DB electrical semantics and required checks

P0-T08 · electrical_engineering_agent · prepared 2026-11-14 · decision packet v2.
Academic-scope amendment explicitly approved by JacobGM; prior attempt preserved.

**Status: ACCEPTED FOR THE ACADEMIC PROTOTYPE — JacobGM, product owner.**
**Qualified electrical engineering approval: DEFERRED; not supplied or claimed.**

The filename is the lifecycle's designated decision-record path, not evidence of
approval. JacobGM initially named themself, then clarified that they are a computer
science student and the project is a final-year computer science project. They
report that Josh, a fourth-year electrical engineering student, reviewed all
documents and approved them on 14 November 2026. That student peer-review
contribution is recorded below; a named
qualified electrical engineer's findings, independent fixtures and explicit
sign-off have not been provided. JacobGM subsequently explicitly approved replacing
the original qualified-review gate with academic prototype acceptance based on
their attestation of Josh's student peer review. The approval record below
identifies the changed authority and preserves the deferred engineering evidence.

## Authority and review baseline

The original P0-T08 task reserved approval to a qualified electrical engineer.
That original gate was not satisfied; attempt 01 remains PARTIALLY_COMPLETED and
unchanged. The original lifecycle is preserved in
[the predecessor snapshot](../../planning/lifecycle_history/2026-11-14.before-p0-t08-academic-scope.json).
The revised P0-T08 gate accepts the documentation for an academic prototype,
with **JacobGM as the product-owner approver**. It uses `document_review`, while
qualified `engineering_review` remains unexecuted and is not relabeled PASS.
No engineering qualification or independent calculation is inferred from product
ownership, task completion, Josh's academic year or software tests.

### Explicit academic-scope approval

The agent asked whether JacobGM explicitly approved revising P0-T08 to academic
prototype acceptance based on their attestation of Josh's student peer review,
with qualified engineering approval deferred. JacobGM replied:

> Yes i approve , because josh is a brilliant and expert in this field . The state
> of P0-T08 should be changed to COMPLETED , so that out team could move to the
> next task .

This is the product owner's explicit electronic conversation decision, recorded
by the agent. It is not a signature attributed to Josh. The product owner's
assessment of Josh's expertise is recorded without asserting professional
qualifications. This decision accepts the E1–E6, C01–C09 and M01–M08 documentation
as the academic prototype's bounded design basis; it does not independently
validate engineering applicability, reference values or a physical panel.

Amend only P0-T08 and D02, reconcile against the fingerprint-verified predecessor,
retain prior accepted tasks and attempt 01, and create attempt 02 under the revised
criteria. The completed report assessment is `COMPLETED`; the orchestrator's
accepted terminal task state is `VERIFIED`, which satisfies dependencies. No
subsequent task is executed by this amendment.

### Academic context and reported student peer review

On 2026-11-14 JacobGM stated that this is their final-year computer science project
and that an electrical engineering student friend reviewed every document and
approved everything. JacobGM subsequently identified the reviewer as **Josh, a
fourth-year electrical engineering student**, and supplied **14 November 2026
(2026-11-14)** as the review date. These details and the reported approval are
provided by JacobGM; they are not a statement or signature supplied by Josh.
A signed statement, specific document versions, row dispositions and independently
worked evidence have not yet been provided. This clarification supersedes any
implication that JacobGM supplied electrical qualifications.

For academic documentation the supported description is: **the project author
reports review and approval by Josh, a fourth-year electrical engineering student,
on 14 November 2026; detailed evidence and Josh's signed statement are pending**.
Retain the student's actual role, name, date and findings without calling the
review professional qualification or certification. Student status alone does
not establish the qualification required by the original D02 wording.

The product owner's explicit amendment accepts this reported student review for
academic documentation. Independent qualified review remains a later obligation
for engineering applicability and release claims. A suitably qualified electrical
faculty member or engineer may later review the packet and student evidence and
sign their own decision. No such review or signature has been supplied here.

Review scope proposed here is the prototype Distribution Board (DB), one explicitly
identified supply, explicit phase mapping and separate L1/L2/L3/N/PE domains.
Applicable supply/earthing arrangements, loads and exposed-part bonding obligations
remain **to be stated by the reviewer**. The proposed boundary excludes PEN,
N–PE bonds, multiple supplies and other panel archetypes. It approves no numerical
reference values, calculation methods, catalog items or manufacturing/standards
certification. This academic D02 acceptance does not satisfy D03/P4-T03 method/data
approval or D04/P4-T16 implementation/release review; they remain separate,
unexecuted qualified gates.

Review these sources together:

- [P0-T07 proposal, including E1–E6](../architecture/electrical-semantics-adr.md).
- [P0-T07 attempt evidence](../../planning/task_reports/P0-T07/attempt-01.md).
- [D01 product/document boundary](approved-product-scope.md),
  [document-operation proposal](../architecture/document-operation-adr.md) and
  [current contract inventory](../architecture/current-contracts.md).
- [CEM](../../backend/app/models/cem.py),
  [functional graph](../../backend/app/models/electrical_graph.py),
  [netlist engine](../../backend/app/services/netlist_engine.py),
  [physical validator](../../backend/app/services/validation_engine.py),
  [wire geometry](../../backend/app/services/wire_geometry.py),
  [orchestrator](../../backend/app/services/orchestrator.py) and
  [draft routing](../../backend/app/services/physical_routing.py).

The inspected branch is `phase_1`, HEAD
`6e85b6b2918aaee2587e2c473584d076486d636e`, with pre-existing uncommitted work.
The following SHA-256 values identify the actual proposal and mandatory inputs,
rather than assuming HEAD includes them:

| Input | SHA-256 |
| --- | --- |
| P0-T07 electrical-semantics ADR | `53e4a444df1c21d905e2228388dfa3f4712de6203f11162bfdd6d76b29e5a45d` |
| `backend/app/models/electrical_graph.py` | `3e7dfb414074b74d3a03a53c69315417ef3941cad5d8f6d281c8fcfb0a8c3ebe` |
| `backend/app/models/cem.py` | `db105ffcafe8cf6ea6a77f4226e1135a16f6235c1c0844c467508d4a9ac8742c` |
| P0-T07 attempt-01 report | `db818c8ca432651eb5eee3d0e8695d27f83407ff3e90d2b40560e4366fb6d37e` |

Source inspection confirms the ADR's main limitations: graph edges are functional
component relationships without mandatory conductor/terminal identity; CEM has
optional conductor data and untyped terminal dictionaries; generated split nets
share busbar terminals; netlist validation checks IDs/references without a phase
compatibility or terminal-capacity rule. Local geometry can return PASS while
bend, dimensions, segregation or virtual earth-anchor checks remain UNRESOLVED.
The physical pipeline rejects every physical violation, including warnings, but
does not implement the ADR's complete applicability aggregate. These observations
are source evidence, not tests run in P0-T08 or accepted engineering results.

## Proposed interpretation and reference cases

The recommendation is to review the ADR without silently promoting it to runtime
behavior. A terminal is the stable `(component_id, terminal_id)` pair. A conductor
is an identified two-terminal installed connection; direction is a reference
orientation. A canonical equipotential net is the maximal closure of conductor
edges and explicitly evidenced permanent terminal equivalences in one compatible
domain. This topological abstraction does not assert zero physical voltage drop.
Breaker, switch, load and SPD functional relations do not create permanent
terminal equivalence. Internal groups create no fabricated wire, route or BOM
length. Shared-terminal commonality does not establish termination capacity.

The reviewer must separately address the ADR's deterministic net merge/split
survivor and lineage policy. Preserve component/terminal/conductor/route identity;
update net references atomically. Graphical crossings, labels, colors and matching
nominal voltages never authorize unions. Known phase/domain conflicts reject an
electrical edit; missing domain/equivalence evidence leaves it UNRESOLVED and
cannot authorize the edit. No ordinary open/save normalizes historical nets.

The outcomes below are **agent-prepared expectations from P0-T07**, accepted as
academic prototype documentation by JacobGM based on reported student review.
Independent qualified dispositions and calculations remain DEFERRED.

| Case | Proposed expected result to accept/revise/reject | Independent evidence the reviewer must attach |
| --- | --- | --- |
| E1 — shared screw / breaker | Four conductors remain four. The three sharing `BUS001:IN_L1` form one input net; QF002 OUT→X001 forms the other. Two nets total; IN/OUT remain distinct. Lexical survivor `NET-BRANCH-QF002-L1-IN` retains main/SPD lineage. Three-wire screw capacity and canonical voltage reference remain unresolved. | Hand-worked terminal partition and conductor inventory; explicit device boundary; approved survivor/lineage interpretation; terminal-capacity and voltage-reference disposition. Mixed legacy 415/239.600… V values are not reference-value approval. |
| E2 — distinct screws | Only declared `IN_L1`/`TAP_L1` are equivalent; L2/N remain separate. Missing group evidence is unresolved; no added conductor. | Product/configuration terminal-group diagram, or explicit acceptance of a synthetic topology case only; negative case without equivalence evidence. |
| E3 — forbidden unions | L1–L2/L3, phase–N/PE, N–PE and different supplies FAIL; missing role is UNRESOLVED. Same-domain union is only a candidate. Reject without partial model/revision mutation. | Independently annotated domain-pair truth table; supply/earth exclusions; before/after identity and membership expectations for rejected edits. |
| E4 — crossing | Crossing at (30,30) creates no junction or membership change, including wires remotely common on one net. Real branches need declared hardware/terminals and conductor lineage. | Marked drawing compared to terminal adjacency; distinguish shared endpoint, remote commonality and geometric crossing. |
| E5 — missing engineering data | Preview envelope PASS with estimated diameter cannot satisfy engineering envelope, bend, segregation or PE-anchor obligations. Required aggregate UNRESOLVED; no engineering eligibility despite zero physical violations. | Applicability reasons for each route check; real stud/bonding and cable-data requirements; straight-route bend applicability decision. No invented radius or diameter. |
| E6 — aggregation | Independently reproduce all 13 ADR rows: failure dominates; unresolved/missing/stale/false-N/A/unapproved-policy cannot become PASS; justified exclusions and optional results remain distinct; a physical warning still blocks eligibility. | Completed 13-row expected/result worksheet, policy/expected-scope assumptions, exclusion rationale and physical-gate outcome. An approved policy is a fixture assumption, not an existing D02 approval. |

For each case record reviewer result, reasoning, deviations, evidence path/hash,
date and signature. An agent closure check or P0-T07's reported software checks
cannot fill the independent-review column. Numeric reference fixtures for later
methods must additionally state units, source edition/product revision, manual
calculation steps, tolerance and applicability bounds; none is approved here.

## Required-check matrix accepted for academic documentation

Every row is a **required family proposed for applicable prototype scope, accepted
as academic documentation; qualified applicability review DEFERRED**. A future
qualified reviewer must enumerate expected objects, approved exclusions,
required evidence and applicability bounds, including expected-but-absent objects.
Unknown applicability is UNRESOLVED. No row may be omitted merely because today's
software lacks its evaluator. Methods and numerical thresholds await later review.

| ID / family | Required scope and evidence to decide | Required failure / unresolved treatment |
| --- | --- | --- |
| C01 — identity/projections | Every component, terminal, conductor and net; equal nested/flattened connection content; drawing/PDM/BOM references and stable lineage. | Duplicate/orphan/conflicting references FAIL. Missing current evaluation UNRESOLVED. Internal equivalence needs no fictitious route. |
| C02 — supply/connectivity | Each conductor/internal group, expected feeder path, explicit supply/phase/N/PE role, device boundary and unused-port rule. | Known incompatible union or demonstrably absent required path FAIL. Missing domain/group/template evidence UNRESOLVED. |
| C03 — conductors/terminations | Each conductor and termination, including all wires sharing a screw; material, section, insulation, ratings, wire count, lug/ferrule and capacity evidence. | Known incompatibility FAIL; missing selection method/product evidence UNRESOLVED. Connectivity alone cannot pass capacity. |
| C04 — bends/envelopes | Every applicable route, bend and terminal approach; real insulated diameter, reviewed bend criterion and route geometry in enclosure mm. | Known insufficient radius/envelope conflict FAIL; unknown criterion/estimated diameter UNRESOLVED. Straightness alone is not approved N/A. |
| C05 — ducts/segregation | Every applicable trunk/bundle, usable duct section, wire diameters/classes, approved fill/separation policy and connected unobstructed trunk. | Known overflow, incompatible classes or obstruction FAIL. Missing dimensions/class policy UNRESOLVED. No free-air fallback. |
| C06 — PE/bonding | All required PE paths and exposed-part/door/plate bonds, including absent required anchors; reviewed assembly/earth scope and real terminals/capacity. | Proven missing mandatory bond/prohibited N–PE union FAIL; virtual or undocumented anchor/applicability UNRESOLVED. Any excluded part needs evidence. |
| C07 — physical policy | All components, rails, ducts, enclosure/plate offsets, mounting, route envelopes and the saved PDM `validation_policy`. | Preserve the existing empty physical-violation requirement, including warnings. Numerical relaxation or suppression cannot produce a pass. Prototype spacing is not standards clearance approval. |
| C08 — calculations/protection/thermal | Exact panel/feeders/loads/candidates required by the reviewed use case; demand, ratings, cable sizing, supply faults, protection and thermal method/input boundaries. | Necessary unreviewed/missing methods or input data UNRESOLVED. Demonstrated criterion violation FAIL. Density screen cannot substitute for temperature-rise or fault/protection verification. |
| C09 — evidence/output compatibility | Exact evaluated model/revision, rule/method versions, document hash/sequence, catalog/model/policy pins, artifacts and report integrity. | Corruption/conflicting results FAIL; stale/missing/incompatible evidence UNRESOLVED. Export success or legacy `FINAL_VALIDATED` supplies no approval. |

Proposed aggregation for C01–C09: applicable FAIL dominates; otherwise required
unknown, absent, stale or unreviewed evidence yields UNRESOLVED; otherwise at least
one applicable PASS plus justified exclusions yields PASS. All scopes proven
inapplicable yield NOT_APPLICABLE with rationale; an unknown empty inventory is
UNRESOLVED. Requiredness is policy-owned, independent of severity. Preserve all
failed/unresolved details and keep optional results visible. N/A requires the
reviewed rule and case evidence, never lack of an evaluator.

Zero physical violations is a separate necessary gate, even if an aggregate is
PASS. Until qualified applicability of this policy is approved, the proposed label is
`Prototype preview — unresolved engineering`. Later bounded-check or engineering
eligibility labels require the ADR's distinct preconditions and later release
authority. These are proposed labels; P0-T08 changes no application labels.

## Manual-edit limits accepted for academic documentation

These recommendations define the proposed future boundary; **no new electrical
editing permission or enforcement is implemented by this record**. JacobGM accepts
the M rows for academic documentation; qualified applicability dispositions remain
deferred. Existing drafts remain drafts.

| ID / edit | Recommended limit and checks | Present evidence / implementation boundary |
| --- | --- | --- |
| M01 — presentation | Selection, visibility, camera, schematic symbol/label/polyline movement cannot change CEM connectivity or ratings. A junction dot alone is an annotation. | Current workspace and schematic overlays are separate from saved engineering snapshots. A label must not be used to infer phase or merge nets. |
| M02 — physical translation | Future typed move uses finite enclosure mm, mounting-plate offsets and unchanged stable identities/dimensions. Enforce mounting, boundary, clearance and saved policy; invalidate dependent routes/geometry/checks/CAD and explicitly recompute before publication. | Current store clears routes on transform and validates/reroutes a draft. It is not an authoritative operation service or permission to publish the draft. Review C01, C04–C09 after affected changes. |
| M03 — rotation | Keep unsupported nonzero device rotation unavailable to authoritative edits until a separately verified physical/routing implementation exists. | Inspector accepts draft rotation; `reroute_placement` rejects nonzero rotation modulo a full turn. UI input availability does not establish engineering support. |
| M04 — connect/disconnect/branch | Future atomic, allowlisted CEM operations require typed domains, explicit terminals/equivalence and capacity data; preserve conductor IDs and net lineage. Check C01–C03/C06 and invalidate all affected downstream checks. Refuse known conflicts or missing evidence needed to authorize the edit. | No present manual electrical publication contract. A real splice needs hardware, terminal capacity, conductor split/lineage and BOM evidence. Removing a mandatory PE/feeder path cannot be accepted as valid. |
| M05 — add/delete/replace/select | Require pinned reviewed catalog configuration, compatible terminal/domain/mounting data, stable allocation and deterministic affected-scope review. Changed ratings, loads or topology require recalculation and revalidation. | Existing generator/requirements selection does not establish an arbitrary manual insertion/replacement API. Unknown products and bridges remain outside the approved set. |
| M06 — routes/ducts | A future route/duct edit must preserve exact conductor/net/endpoints and validate C01, C03–C07/C09, including swept bends and connected unobstructed ducts. | No deletion of obstructing ducts, endpoint detachment, estimated diameter substitution or free-air routing to bypass a failure. Unknown engineering data cannot be promoted to PASS. |
| M07 — constraints/evidence | Saved policy, catalog dimensions/ratings, requiredness, applicability, validation status and version pins are not user-overridable engineering facts. Display preferences are separate. | Today's placement endpoints accept a PDM payload and do not establish an authoritative server-owned policy fence. Do not describe this recommendation as enforced. Future protection requires separately authorized implementation. |
| M08 — persistence/undo | Atomic edits require preconditions and conflict handling; save/recovery cannot implicitly recompute or publish geometry. Failed edits preserve the prior revision and local recovery. Undo is a new valid operation, not history mutation. | Follow D01/document-operation boundaries. Never repair legacy split nets, overwrite immutable snapshots or reuse retired identities during ordinary open/save. |

Source basis: [project store](../../frontend/src/stores/projectStore.ts),
[inspector](../../frontend/src/components/workspace/PropertiesInspector.tsx),
[design endpoints](../../backend/app/api/routes_design.py), draft routing linked
above, [workspace notes](../CAD_WORKSPACE.md) and
[lifecycle notes](../PROJECT_LIFECYCLE.md). Current `is_valid` from placement means
an empty local violation list, not completion of C01–C09. D02 does not expand the
existing save, reroute or publication APIs.

## Unsupported conditions and later evidence

The following conditions remain outside approval or unresolved. A necessary check
cannot be marked N/A just to keep a design eligible. The reviewer must identify
additional exclusions for the actual DB application; this inventory does not
assert completeness for all installations.

| Condition / gap | Evidence required before later approval |
| --- | --- |
| Unspecified supply/earthing arrangement; PEN/N–PE bond; multiple sources, transfer, generation/backfeed, DC or another panel archetype | Separately approved use case and system/interface model, fault/earthing/protection assumptions, connectivity cases and applicable rule inventory. D02's proposed single-supply boundary does not authorize these cases. |
| Breaker/SPD state-dependent continuity, RCD/RCBO neutral grouping or unmodeled device functions | Reviewed per-device terminal/pole/function topology, neutral/protection zones, operating-state limits and independent positive/negative fixtures. A component-level FEEDS edge cannot supply this. |
| Shared screws, feed-throughs, removable bridges, parallel conductors or splices without evidence | Pinned manufacturer/configuration drawings, permanent/removable group identity, permitted conductor counts/material/sections/accessories and installed-object/BOM treatment. Parallel IDs/quantities remain distinct; no method for current sharing is approved. |
| Generic conductor diameter/bend assumptions or unknown conductor selection | Reviewed cable product/revision, material, section, insulated diameter, insulation/temperature/installation data and manufacturer bend limits; selection/derating method and independent reference calculations. Positive numbers or a `catalog` string alone are insufficient. |
| Virtual `PANEL_ROOT:EARTH_STUD`, omitted metalwork/door/plate bonds or unknown PE sizing | Actual assembly terminal registry, stud/termination locations/capacity, bonding obligations and reviewed sizing/continuity criteria with independent cases. Exclusions need exact construction evidence. |
| Unreviewed load/demand, voltage drop, fault levels, protection/coordination, conductor/busbar ratings or thermal limits | D03-approved methods and source editions, applicability bounds, input provenance, units/tolerances and independently worked fixtures, including limiting/negative cases. Existing calculation output and thermal-density screens do not approve these methods. |
| Estimated duct fill, bundle segregation or electrical clearances | Actual usable geometry and wire data, reviewed separation/fill/installation/insulation rules and validated worst-case fixtures. Existing prototype physical limits remain in force without becoming certified values. |
| Unapproved catalog/CAD geometry and terminal equivalence | Exact versioned product/configuration, dimensional/terminal/rating source evidence, review history and data-use rights; geometry agreement against reviewed references and method applicability. A preview mesh is insufficient. |
| Current split nets, optional/loosely typed fields, absent domain and required-check aggregate | Separately authorized coordinated contracts/compatibility work, deterministic conversion and regression fixtures, immutable prior snapshots and explicit version pins. D02 does not perform migration or make production checks appear complete. |
| Unsupported physical rotation, arbitrary geometry/duct or manual electrical edits | Reviewed operation limits, backend/frontend contract parity, endpoint/identity preservation and physical/routing/negative-case evidence before enabling those operations. |
| Manufacturing, temperature-rise/withstand/short-circuit performance or standards certification claims | Appropriate separate qualified assessment and applicable physical verification for the actual assembly. Software tests, GLB previews, script text and even verified CAD exports cannot supply certification. |

For later method/catalog review, retain an evidence bundle with case ID, exact
input model and hashes, pinned sources/products/policies, independent worked result,
units/tolerances, evaluated output, comparison/deviation disposition, reviewer
identity/qualification/date/signature and applicability/exclusion statement. No
numerical reference values or external standards editions are selected by this
packet. Supporting evidence must be obtained and reviewed rather than invented.

## Review disposition and product-owner approval

| Field | Recorded evidence / outstanding requirement |
| --- | --- |
| Product-owner designation | JacobGM, computer science student author and product owner established in D01; explicitly approved the academic-scope amendment and completion in conversation. |
| Named reviewer | Josh — student peer reviewer, identified by JacobGM. Qualified engineering review is deferred. |
| Qualification / relevant role | JacobGM: computer science student author. Josh: fourth-year electrical engineering student, as reported by JacobGM. No qualified electrical-engineer status established. |
| Student peer-review finding | JacobGM reports that Josh reviewed all documents and approved everything; individual findings, evidence and a statement from Josh remain pending. This records the report without fabricating a signature. |
| Review date and signed evidence reference | Student peer review: 14 November 2026 (2026-11-14), supplied by JacobGM. Signed evidence from Josh and qualified D02 sign-off not supplied. |
| Net/conductor and identity interpretation | Accepted as academic prototype documentation by JacobGM, based on reported student review; qualified interpretation/applicability review deferred. |
| Reference cases E1–E6 | Accepted as academic documentation; independent worked evidence and individual qualified dispositions not supplied. |
| Required-check matrix C01–C09 | Accepted as the prototype's documented check inventory; qualified applicability, exclusions, reference values and methods remain unapproved. |
| Manual-edit limits M01–M08 | Accepted as documented academic prototype limits; no new runtime permission, enforcement or qualified applicability approval. |
| Supply/earth/assembly scope and unsupported conditions | Retain the bounded single-supply DB proposal and all documented exclusions; actual installation applicability and bonding verification remain deferred. |
| Decision / signature | APPROVED FOR ACADEMIC SCOPE by JacobGM through explicit conversation acceptance; no signature attributed to Josh or qualified electrical engineer. |

After the request for qualification and concrete review dispositions, the user
asked the agent to do the task: `I believe in you chatgpt. Please do this task for
me.` This authorizes completing the preparation. It supplies neither electrical
qualification nor independent fixture findings nor a qualified signature; no
approval was inferred from that earlier request. The later explicit academic-scope
approval quoted above is the authority for the amended decision.

For later qualified approval, the reviewer should identify this **decision packet
v2** and the hashed P0-T07 ADR, their qualification/role and review date; explicit
approve/revise/reject dispositions for interpretation, E1–E6, C01–C09 and M01–M08;
the exact supply/earth/assembly applicability and exclusions; and attached
independent fixture evidence with any deviations. A signature must state that
the decision covers bounded prototype semantics only, approves no unreviewed
calculation method/reference values/catalog data, and makes no certification claim.
Deferred required scope stays unresolved rather than implicitly approved.

Do not populate signature fields from the agent's expectations. The original
qualified `engineering_review` remains NOT_RUN, as retained in attempt 01.
Attempt 02 uses `document_review` under the explicitly revised academic criteria;
passing that profile does not satisfy the deferred engineering review. The
orchestrator records the approved amendment, new attempt and acceptance through
its existing transactional writer and append-only history. No runtime code, saved
physical policy, database schema, engineering revision or engine/generator version
is changed. D03/D04 remain qualified gates before their engineering claims.
