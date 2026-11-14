# ADR: DB electrical identity and validation applicability

P0-T07 · proposed semantics · source review 2026-11-14.

## Status, authority and scope

**AWAITING P0-T08 qualified human approval (D02). Not approved for implementation.**
This document prepares review evidence for the qualified electrical engineer
designated by the product owner. Completing or accepting P0-T07 does not approve
applicability, reference values, engineering methods or implementation. No person
has signed this proposal. The future P0-T08 decision record is
`docs/decisions/approved-electrical-semantics.md`; this task does not create it.

Scope is the existing prototype Distribution Board (DB). CEM owns electrical
intent; PDM owns physical arrangement. Proposed rules below are software contracts
for review, not statements of electrical standards or certification. No additional
panel archetype, earthing system, neutral-earth bond or manufacturer capability
is authorized. All examples are synthetic; their IDs and values are review inputs,
not approved catalog data. Runtime behavior and immutable historical revisions
remain unchanged.

## Implementation evidence and gaps

The [current inventory](current-contracts.md), [document ADR](document-operation-adr.md),
[product scope](../decisions/approved-product-scope.md),
[wiring notes](../WIRING_IMPLEMENTATION.md) and
[strict physical policy](../CONSTRAINT_POLICY_UPDATE.md) provide context. Source
takes precedence over historical status/version claims in those notes.

| Evidence | Observed behavior; implication for this proposal |
| --- | --- |
| [NetlistEngine](../../backend/app/services/netlist_engine.py): `generate_netlist`, `validate_netlist` | Generates separate `NET-MAIN-L1`, `NET-SPD-L1` and branch-input nets even when they share `BUS001:IN_L1`. Validates duplicate net/connection IDs and endpoint references, but not equipotential closure, phase compatibility, terminal capacity or internal equivalence. The graph argument does not determine its terminal topology. |
| [GraphEngine](../../backend/app/services/graph_engine.py): `build_electrical_graph`; [graph models](../../backend/app/models/electrical_graph.py) | Component-level directed `FEEDS`/`PROTECTED_BY`/`CONNECTED_TO` relationships have no required terminal endpoints or conductor ID. These are functional relationships, not proof of physical conductors or equipotential membership. |
| [CEM](../../backend/app/models/cem.py): `ComponentRef`, `ConnectionRef`, `NetRef`, `CEMState` | Terminals are dictionaries; conductor specifications are optional, with positive finite validation on supplied section/diameter/bend fields. No typed phase domain, equivalence groups or four-state report exists. `voltage_level` alone has no voltage-reference contract. Top-level `connections` duplicates the nested net connections. |
| [SchematicEngine](../../backend/app/services/schematic_engine.py): `generate_schematic_data`; [frontend schematic](../../frontend/src/components/schematic/schematicGraph.ts): `buildSchematicGraph`, `validateSchematicGraph` | Wires preserve connection IDs/endpoints. A backend junction requires a shared terminal and net, while crossings do not connect; coincident tracks give drawing warnings. Frontend draft checks do not establish phase/domain safety or publish CEM edits. Legacy split nets can obscure a shared-terminal junction. |
| [DuctRouter](../../backend/app/algorithms/duct_routing.py): `route_layout`; [PDM](../../backend/app/models/pdm.py): `WireRoute`, `WireGeometry`, `DesignValidationPolicy` | Routes retain `conductor_id`, net and terminal references. Missing diameter uses generic 3/4/6 mm preview estimates; `PANEL_ROOT:EARTH_STUD` is accepted as a special virtual endpoint. Coordinate finiteness and some dimensions are checked, not engineering provenance. |
| [wire_geometry](../../backend/app/services/wire_geometry.py): `circular_centerline`, `build_wire_geometry` | Geometry can return `status='PASS'` with UNRESOLVED bend, segregation, dimensions and virtual earth-anchor checks. A supplied bend value or `dimension_source='catalog'` can produce a local PASS without approved provenance. These are separate local facts, not engineering-release approval. |
| [ValidationEngine](../../backend/app/services/validation_engine.py): `validate_pdm` | Returns geometric/identity/thermal-density/duct violations, not a complete applicability report. Skips the virtual root terminal position check; matches routes through the `ROUTE-` ID convention. Does not aggregate geometry subchecks or prove phase/PE integrity. Thermal density is a prototype screen, not temperature-rise verification. |
| [Orchestrator](../../backend/app/services/orchestrator.py): `generate_design`, `_physical_design`; [draft routing](../../backend/app/services/physical_routing.py): `reroute_placement` | Placement → DuctRouter → physical validation → wire geometry. Any physical violation, including warnings, fails generation. `FINAL_VALIDATED` may still coexist with unresolved wire subchecks; it denotes the existing pipeline state only. |
| [Revision writer](../../backend/app/persistence/revisions.py): `write_revision`; [ProjectService](../../backend/app/services/project_service.py): `ENGINE_VERSION`; [API](../../backend/app/models/api.py): `DesignPackage`; [frontend CEM](../../frontend/src/types/cem.ts), [frontend PDM](../../frontend/src/types/pdm.ts) | Revision projections preserve logical keys and save existing violation-based reports. Current backend optional conductor fields and frontend shapes are not fully aligned. No existing API/schema proves this proposal or eligibility; future changes require coordinated contracts, pins and immutable evidence. |

## Proposed electrical identity

### Distinct entities and ownership

| Entity | Proposed meaning and invariant |
| --- | --- |
| Terminal | Stable pair `(component_id, terminal_id)`. Labels/coordinates are attributes, never identity. Several graphical ports may reference one terminal. Different terminal IDs remain distinct even at equal coordinates. |
| Conductor edge | One identified installed conductor between two declared terminals, represented by `ConnectionRef.id`. `from`/`to` express a consistent reference direction, not a diode or AC current direction. Parallel conductors retain distinct IDs and quantities. No automatic deduplication by endpoints. |
| Equipotential net | Maximal connected set under conductor edges and approved permanent terminal equivalences, within one supply/domain. This is a topological idealization; it does not assert zero real voltage drop. A net has member terminals and conductor IDs; its name, nominal voltage and graphical shape cannot define membership. |
| Terminal equivalence | Explicit, versioned evidence that distinct terminals belong to one permanently conductive internal group, e.g. one busbar phase strip or approved feed-through block. It creates no fabricated wire, route, wire length or BOM conductor. A removable bridge must be a recorded installed object/configuration, not inferred from a product name. |
| Functional device relationship | A separate relation across terminals/poles of a breaker, switch, SPD or load. It can describe supply/protection and operating state, but never collapses the adjacent nets in this structural netlist. A closed breaker is still a device boundary. Operational continuity analysis is a separate reviewed method. |
| Physical route / drawing wire | Route and schematic IDs reference the conductor and its net, plus exact terminal endpoints. Routing, coincident tracks, selection and moving a symbol do not create electrical connections. A busbar solid may represent an internal group without an artificial route. |

Ordinary terminal equivalence is reflexive, symmetric and transitive. A terminal
can belong to only one canonical equipotential net in a document. Two conductors
sharing the same terminal are electrically common there; whether both fit that
terminal is a separate required capacity check. Missing equivalence evidence
between *different* terminals leaves the needed continuity check UNRESOLVED;
matching labels, coordinates, category or component identity cannot supply it.
Each isolated declared terminal is a singleton class; only terminals that the
approved DB template expects to be connected create an open-circuit obligation.
Unused catalog ports require explicit template/applicability treatment.

### Phase, neutral and protective-earth boundaries

Associate every participating terminal/net with an explicit supply identity and
role in `{L1, L2, L3, N, PE}`. Names, wire colors, `POWER`, 0 V and pole count are
insufficient classifiers. A single-phase supply needs an explicit phase mapping;
feeder ordering cannot silently reassign it. Voltage needs a finite value, unit V
and reference (line-to-line or line-to-neutral as appropriate); current legacy
`voltage_level` values must not be used to infer common potential or safe merging.

| Proposed connection/equivalence | Outcome before applying a change |
| --- | --- |
| Same known supply and same L1 (or L2/L3/N) role | Candidate for union; still check references, topology, terminal capacity and domain constraints. |
| L1 ↔ L2/L3, or any phase ↔ N/PE | FAIL; reject atomically. Common nominal voltage or `POWER` class cannot permit a short. |
| N ↔ PE | FAIL in this bounded DB profile. Both can have nominal 0 V yet must remain separate. No inferred bond, PEN or upstream earthing topology. Supporting any bond requires separate reviewed scope and an explicit modeled interface, never an ordinary union. |
| Same PE domain with documented bar/stud/termination | Candidate PE continuity; require physical anchor, capacity and bonding evidence. Shared enclosure coordinates are not proof. |
| Different supply identities or unclassified terminals | Different known supplies: FAIL under this single-supply DB profile. Missing identity/role/equivalence evidence: UNRESOLVED and refuse an electrical edit requiring that evidence. Do not guess compatible domains. |
| Device terminals on opposite sides of one breaker, SPD L/PE ports or different poles | No equivalence. Model the device relationship separately; an SPD's protective function never shorts its phase and PE nets. |

PE continuity must refer to real modeled terminals/anchors and any required
cabinet/door/plate bonds in the approved assembly scope. Neither the current
virtual root endpoint nor a neutral path discharges that obligation. Omitted
required PE conductors are failures when absence is established; missing system,
anchor or bonding data is UNRESOLVED. No ordinary switching/protection relation
is treated as a permanent PE equivalence. Applicability to metalwork must come
from reviewed construction data, not from whether a PE route happens to exist.

### Determinism, identity and graphical junctions

Proposed derivation: validate unique IDs and references; classify domains; collect
approved internal equivalences and explicit conductor edges; check every proposed
union for boundary conflicts; compute undirected connected components. Sort stable
terminal/edge keys for repeatable traversal/output. No functional `FEEDS` edge or
geometric intersection enters this closure. Known conflicts FAIL; absent evidence
stays UNRESOLVED, even if a provisional partition can be drawn for preview.

Persistent net IDs are not recomputed from traversal order or conductor IDs.
An unchanged partition retains its ID when its conductor inventory changes.
Extending one existing unsplit net with new terminals retains that net ID.
A merge retains the lexicographically
smallest existing net ID and records all predecessor aliases; a split retains
the old ID on the class containing its smallest stable terminal key and allocates
new IDs for the others. The authoritative operation receipt records allocated
IDs, membership and lineage so replay does not allocate again. New isolated nets
allocate IDs once. For a batch with both splits and merges, derive all final
terminal classes first: assign each predecessor ID only to the final class
containing its smallest surviving terminal; each final class keeps the smallest
assigned ID or allocates one if none is assigned. Retired/removed nets retain
historical lineage. Conductor, terminal, route and component IDs survive merges;
only net references change atomically across CEM/schematic/PDM/BOM projections.
Aliases are historical lookup evidence, not extra active nets. Approval must
confirm this proposed policy before implementation.

A graphical junction marker is a projection of an explicit CEM shared terminal
or approved junction hardware. An internal busbar equivalence may use a busbar
symbol with distinct referenced ports; it does not invent a screw or splice.
A crossing with no shared electrical terminal has no junction, even for wires
already on the same net through a remote connection. Merely adding a dot,
overlapping segments, moving a symbol, or touching an endpoint to a line is a
presentation edit. Creating a real branch requires an explicit electrical batch
with junction hardware/terminals, capacity checks and conductor split/lineage;
the current two-endpoint conductor cannot silently become a three-ended object.
Unknown splice hardware remains unsupported/UNRESOLVED rather than fabricated.

## Proposed validation and applicability

### Check records, applicability and freshness

Each result binds a stable `check_id`, versioned rule/method, object IDs and scope,
required/optional designation from the **approved policy**, applicability decision
and reason/evidence, status, measured/reference values with units/tolerance,
input hashes/document sequence, catalog/model/policy pins and provenance.
Missing measured data is null/missing with a reason, never zero. Reject invalid
IDs, unknown status strings, nonfinite numbers and incompatible schema versions.
Unknown rule versions, stale hashes, unavailable evaluators and unevaluated
required scopes produce UNRESOLVED; a stale previous PASS remains historical
evidence but is not current PASS. Missing P0-T08 approval itself blocks eligibility.
Requiredness cannot be downgraded by a client or inferred from severity.

| Status | Meaning |
| --- | --- |
| PASS | Rule is applicable, required inputs/evidence are complete and current, and the reviewed method satisfies its bounded criterion. A local geometry PASS proves only that geometry criterion. |
| FAIL | An applicable criterion is demonstrably violated, or an established structural contract is invalid. Record the offending objects and values; absent evidence alone is not proof of physical failure. |
| UNRESOLVED | Applicability is unknown, or required inputs/method/evidence/provenance are missing, assumed, unsupported, stale or not evaluated. Blocks eligibility when required. |
| NOT_APPLICABLE | An approved applicability rule proves the check is outside this exact scope, with reason and input evidence. Missing data, evaluator or approval is never such a proof. |

First enumerate expected scopes from the approved DB template, requirements,
catalog/assembly and the exact model, independently of returned results. This
includes expected-but-absent objects (a required PE anchor is not skipped because
there are zero anchors). For each expected scope, determine applicability:
true → evaluate; false with approved evidence → NOT_APPLICABLE; unknown →
UNRESOLVED. A missing required result becomes an explicit UNRESOLVED record.
Conflicting duplicate results fail the report-integrity check; do not select the
most favorable. Extra/unsupported results cannot satisfy a required rule.

### Required-check scopes proposed for qualified review

All rows below are proposed required families when applicable. This is a minimum
review inventory, **not an approved engineering-release checklist**. P0-T08 must
bound each method and required scope; later method/reference-data and engineering
release gates still apply. Unsupported necessary checks stay UNRESOLVED.

| Family | Enumerated scope and applicability evidence | Missing evidence / observed failure |
| --- | --- | --- |
| Identity and projection integrity | Every CEM component/terminal/net/conductor; flattened connections equal nested connections by ID/content; each required route/drawing/BOM reference; one canonical net per terminal. | Orphan/duplicate/conflicting references FAIL; no current report UNRESOLVED. Explicit internal equivalence needs no wire route. |
| Supply, connectivity and terminal compatibility | Each edge/group, expected feeder path, device boundary, phase/N/PE domain and unused-port policy. | Cross-phase/boundary short or proven missing required conductor FAIL; absent role/equivalence/template UNRESOLVED. |
| Termination and conductor selection | Each conductor/end and multi-conductor terminal; size/material/insulation, ratings, number of wires, ferrule/lug and terminal capacity from reviewed data. | Unknown size/capacity/selection method UNRESOLVED; demonstrated overload/incompatible termination FAIL. A common terminal is not unlimited capacity. |
| Bend and swept geometry | Each routed conductor, terminal approach and relevant bend; reviewed cable bend/installation criteria, diameter and actual route geometry in mm. | Missing bend criterion UNRESOLVED even for a straight preview unless approved applicability proves exclusion; insufficient radius FAIL. Generic diameter cannot yield engineering envelope PASS. |
| Duct fill and segregation | Each route/trunk and relevant bundle/duct; all wire diameters/classes, usable section, separation and approved fill policy. | Estimated/missing diameters or empty class policy UNRESOLVED; disconnected/obstructed trunk, known overflow or forbidden class FAIL. |
| Protective earth and anchors | Every required PE path/termination and exposed conductive part/bonding obligation; reviewed supply/earthing and assembly scope, stud position/capacity and connection evidence. | Virtual/missing anchor data UNRESOLVED; known missing mandatory bond or prohibited N–PE connection FAIL. Non-metal/excluded part needs an approved N/A rationale. |
| Placement and physical policy | All placed components, rails/ducts/enclosure, route envelopes, plate offsets and saved PDM `validation_policy`. | Any physical violation, including warnings, blocks generation/publication; no numerical weakening or free-air fallback. Known prototype geometry limits do not prove standards clearances. |
| Electrical calculations, protection and thermal | Panel/feeder/load/candidate as required by bounded use case; reviewed demand, device/cable ratings, fault/protection assumptions and thermal method/data. | Missing required fault/current/temperature/reference data UNRESOLVED. Density-screen PASS cannot substitute for any required temperature-rise/protection check. Numeric criteria await qualified review. |
| Output/evidence compatibility | Exact evaluated document/revision, pins, report/schema/generator versions and artifact references/hashes. | Corrupt references FAIL; stale/missing evidence or unavailable compatible method UNRESOLVED. Export success adds no engineering approval. |

### Aggregation and user-facing labels

For each required rule family and the global required report, aggregate all
expected scope results after checking applicability and freshness:

1. Any applicable FAIL → FAIL (retain all unresolved/failed details).
2. Otherwise any applicable or applicability-unknown UNRESOLVED, missing result,
   stale result or unapproved required policy → UNRESOLVED.
3. Otherwise at least one applicable PASS, all others justified NOT_APPLICABLE → PASS.
4. All expected scopes proven inapplicable → NOT_APPLICABLE, with the scope rationale.
   An empty report with unknown expected scopes is UNRESOLVED, never vacuous PASS.

Optional/advisory checks have a separate aggregate and remain visible; they cannot
offset required results. Severity is independent of status/requiredness. All
physical violations remain an additional hard gate, including a warning described
as advisory elsewhere. A global report must not suppress failed details behind
one global status, an average score or `FINAL_VALIDATED`.

| Proposed label | Preconditions and meaning |
| --- | --- |
| Prototype preview — unresolved engineering | Display permitted recoverable/provisional design evidence with required failures/unresolved checks and estimates visible. This label does not waive the existing zero-physical-violation generation rule or authorize publication of an invalid physical design. A saved working draft is not an eligible engineering release. |
| Prototype preview — bounded checks passed | All currently approved bounded required checks pass, exclusions are justified and physical violations are zero, but later engineering-release authority/reference validation is not granted. Until D02, the required policy is unapproved, so the previous unresolved label applies. |
| Engineering release eligible — approved DB scope only | Future label only: required aggregate PASS, justified per-scope N/A, zero physical violations, fresh complete compatible evidence, approved scope/method/data and all qualified release gates (including P4-T16) satisfied. Eligibility is not an actual human release/signature or manufacturing/standards certification. |

Never label a whole DB engineering PASS merely because one geometric subcheck
passes, `validation_results` is empty, an export succeeds, or a legacy state is
`FINAL_VALIDATED`. This ADR changes none of today's UI/API labels.

## Review examples

These JSON fragments are documentation fixtures, not API requests or new schemas.
`review_schema` identifies a proposed review fixture only. Endpoint arrays below
mean `[component_id, terminal_id]`; positions and bend/diameter fields use mm.
The contract verification exercises current model shapes separately from proposed
invariants. It cannot establish qualified electrical applicability.

### E1 — shared busbar terminal and breaker boundary

The first three conductors below share `BUS001:IN_L1`. Today they have three net
IDs; the proposed canonical net is one supply-L1 net. Keep each conductor ID
unchanged. The outgoing conductor stays on a different net across QF002: IN and
OUT are a device relationship, never a permanent equivalence. All terminals in
this example are explicitly assigned supply `S1`, role `L1` for review.

```json
{
  "example": "E1", "review_schema": "electrical-semantics-review/1",
  "nets": [
    {"id":"NET-MAIN-L1","name":"Main L1 Feed","voltage_level":415,"wire_class":"POWER","connections":[
      {"id":"NET-MAIN-L1-C01","from_component":"QF001","from_terminal":"L1_OUT","to_component":"BUS001","to_terminal":"IN_L1","net_id":"NET-MAIN-L1","wire_class":"POWER"}]},
    {"id":"NET-SPD-L1","name":"Surge Protection L1","voltage_level":415,"wire_class":"POWER","connections":[
      {"id":"NET-SPD-L1-C01","from_component":"BUS001","from_terminal":"IN_L1","to_component":"SPD001","to_terminal":"L1","net_id":"NET-SPD-L1","wire_class":"POWER"}]},
    {"id":"NET-BRANCH-QF002-L1-IN","name":"QF002 L1 IN","voltage_level":239.6003617136947,"wire_class":"POWER","connections":[
      {"id":"NET-BRANCH-QF002-L1-IN-C01","from_component":"BUS001","from_terminal":"IN_L1","to_component":"QF002","to_terminal":"IN","net_id":"NET-BRANCH-QF002-L1-IN","wire_class":"POWER"}]},
    {"id":"NET-BRANCH-QF002-L1-OUT","name":"QF002 L1 OUT","voltage_level":239.6003617136947,"wire_class":"POWER","connections":[
      {"id":"NET-BRANCH-QF002-L1-OUT-C01","from_component":"QF002","from_terminal":"OUT","to_component":"X001","to_terminal":"LEFT","net_id":"NET-BRANCH-QF002-L1-OUT","wire_class":"POWER"}]}
  ],
  "expected_input_net_id":"NET-BRANCH-QF002-L1-IN",
  "expected_input_conductor_count":3,
  "expected_total_net_count":2,
  "terminal_capacity_status":"UNRESOLVED"
}
```

The lexical survivor is `NET-BRANCH-QF002-L1-IN`; main/SPD predecessor IDs become
aliases in the explicit conversion receipt. This naming choice makes no physical
claim. Mixed legacy voltage values reflect different implicit references, not
different potentials at the same screw. Preserve legacy values historically;
conversion requires reviewed voltage references and a canonical net value, rather
than silently selecting one. Three wires at the screw require documented capacity;
until then termination eligibility remains UNRESOLVED despite known commonality.

### E2 — distinct screws on one strip

```json
{
  "example":"E2", "review_schema":"electrical-semantics-review/1",
  "component_id":"BUS001", "supply_id":"S1",
  "terminals":{"IN_L1":"L1","TAP_L1":"L1","IN_L2":"L2","IN_N":"N"},
  "equivalence":{"id":"EQ-BUS001-L1","members":["IN_L1","TAP_L1"],"evidence":"SYNTHETIC-REVIEW-GROUP-v1"},
  "expected_equivalent":["IN_L1","TAP_L1"],
  "expected_separate":["IN_L2","IN_N"],
  "without_equivalence_evidence":"UNRESOLVED"
}
```

Only the declared L1 group is common; the busbar component is not one node that
shorts all its poles. The synthetic evidence tests shape only. Real group evidence
requires a pinned reviewed product/configuration. Feed-through LEFT/RIGHT or
neutral/PE bar screws follow the same explicit-group rule; do not infer it from
terminal names. Internal group membership adds no wire length or route.

### E3 — cross-phase rejection and boundary matrix

```json
{
  "example":"E3", "review_schema":"electrical-semantics-review/1",
  "candidate":{"id":"CONN-REJECT","from_component":"BUS001","from_terminal":"IN_L1","to_component":"QF003","to_terminal":"L2_IN","net_id":"NET-REVIEW","wire_class":"POWER"},
  "source_domain":{"supply_id":"S1","role":"L1"},
  "target_domain":{"supply_id":"S1","role":"L2"},
  "expected_status":"FAIL", "expected_applied":false,
  "expected_reason":"PHASE_DOMAIN_CONFLICT"
}
```

Identical wire class/voltage does not permit this edge. The existing shape/reference
validator alone can accept it; the proposed electrical boundary rule must reject
before changing any CEM/PDM/drawing/revision. The same rejection applies to a bad
equivalence group. Additional review cases: L1–N FAIL; L1–PE FAIL; N–PE FAIL even
at nominal 0 V; S1-L1–S2-L1 FAIL; missing role UNRESOLVED; S1-L1–S1-L1 is only a
candidate, with all other required checks still due. No failed edit changes IDs,
net membership, saved revision or local recovery evidence.

### E4 — crossing without a junction

```json
{
  "example":"E4", "review_schema":"electrical-semantics-review/1",
  "wires":[
    {"id":"C-A","net_id":"N-L1","endpoints":[["A","T"],["B","T"]],"points":[[10,30],[50,30]]},
    {"id":"C-B","net_id":"N-L2","endpoints":[["C","T"],["D","T"]],"points":[[30,10],[30,50]]}
  ],
  "crossing":{"x":30,"y":30,"connected":false},
  "expected_junctions":[], "expected_membership_change":false
}
```

Render a nonconnected crossing; no terminal exists at `(30,30)`. If both wire
net IDs were `N-L1` due to a remote common terminal, this crossing would still
create no local splice. Moving B or changing a polyline changes drawing coordinates
only. A real shared `BUS001:IN_L1` endpoint in E1 may display a connected marker
after canonical net reconciliation. A dot at this crossing without a CEM endpoint
is only an annotation and cannot authorize a connection or make E3 permissible.

### E5 — geometry PASS with missing required data

```json
{
  "example":"E5", "review_schema":"electrical-semantics-review/1",
  "route":{"id":"ROUTE-C-PE","net_id":"NET-PE","net_name":"Protective earth","from_component":"PANEL_ROOT","from_terminal":"EARTH_STUD","to_component":"PEBAR01","to_terminal":"MAIN_PE","wire_class":"PE","waypoints":[{"x":50,"y":50,"z":50},{"x":80,"y":50,"z":50}],"length_mm":30,"bend_count":0,"color_hex":"#22C55E","wire_diameter_mm":4,"conductor_id":"C-PE","dimension_source":"generic-preview-estimate","minimum_bend_radius_mm":null},
  "checks":[
    {"check_id":"ROUTE-C-PE:ENVELOPE","required":true,"applicability":"APPLICABLE","status":"PASS","reason":"Preview envelope only, using estimated diameter"},
    {"check_id":"ROUTE-C-PE:BEND","required":true,"applicability":"APPLICABLE","status":"UNRESOLVED","reason":"No reviewed bend or installation criterion"},
    {"check_id":"ROUTE-C-PE:DIMENSIONS","required":true,"applicability":"APPLICABLE","status":"UNRESOLVED","reason":"No actual insulated diameter or reviewed conductor selection evidence"},
    {"check_id":"ROUTE-C-PE:EARTH_ANCHOR","required":true,"applicability":"APPLICABLE","status":"UNRESOLVED","reason":"Virtual anchor; no physical stud or termination-capacity evidence"},
    {"check_id":"ROUTE-C-PE:SEGREGATION","required":true,"applicability":"APPLICABLE","status":"UNRESOLVED","reason":"No reviewed bundle or segregation data"}
  ],
  "physical_violation_count":0,
  "expected_required_status":"UNRESOLVED",
  "expected_label":"Prototype preview — unresolved engineering",
  "engineering_release_eligible":false
}
```

The first PASS is deliberately limited to the preview calculation; it does not
satisfy the engineering swept-envelope criterion that needs a real diameter.
The straight line does not establish bend-rule inapplicability. If it is proven
that an assembly has no required cabinet earth anchor under an approved scope,
that exact anchor check may be N/A with recorded evidence; this virtual PE
route is not such evidence. Supplying any positive radius/diameter or changing
`dimension_source` to `catalog` without provenance cannot upgrade engineering
status. Known too-small bend or missing mandatory bond is FAIL, not UNRESOLVED.

### E6 — required aggregation review matrix

```json
{
  "example":"E6", "review_schema":"electrical-semantics-review/1",
  "cases":[
    {"id":"all-pass","statuses":["PASS","PASS"],"expected":"PASS"},
    {"id":"failure-dominates","statuses":["PASS","FAIL","UNRESOLVED"],"expected":"FAIL"},
    {"id":"geometry-cannot-mask","statuses":["PASS","UNRESOLVED"],"expected":"UNRESOLVED"},
    {"id":"excluded-scope","statuses":["PASS","NOT_APPLICABLE"],"na_rationale":"Approved exclusion with input evidence","expected":"PASS"},
    {"id":"family-excluded","statuses":["NOT_APPLICABLE"],"na_rationale":"All scopes excluded by approved rule","expected":"NOT_APPLICABLE"},
    {"id":"false-na","statuses":["NOT_APPLICABLE"],"expected":"UNRESOLVED"},
    {"id":"missing-result","statuses":["PASS"],"missing_required_count":1,"expected":"UNRESOLVED"},
    {"id":"stale-result","statuses":["PASS"],"fresh":false,"expected":"UNRESOLVED"},
    {"id":"unknown-applicability","statuses":["UNRESOLVED"],"expected":"UNRESOLVED"},
    {"id":"empty-unknown","statuses":[],"expected":"UNRESOLVED"},
    {"id":"unapproved-policy","statuses":["PASS"],"policy_approved":false,"expected":"UNRESOLVED"},
    {"id":"optional-failure-visible","statuses":["PASS"],"optional_statuses":["FAIL"],"expected":"PASS"},
    {"id":"physical-warning-blocks","statuses":["PASS"],"physical_violation_count":1,"expected":"PASS","engineering_release_eligible":false}
  ]
}
```

Defaults in this isolated matrix assume current evidence and an approved policy
only to test aggregation; they do not claim P0-T08 approval. Statuses are required
results unless explicitly optional. N/A requires the recorded rationale to be
checked against an approved applicability rule; fixture text alone is not real
approval. The last case distinguishes aggregate status from the independent
zero-physical-violation eligibility gate.

## Compatibility and implementation boundary

No runtime model, route, engine, database or UI change is authorized by this ADR.
Keep CEM/PDM hashes, saved policy, pinned catalogs/models and compatibility checks.
Never normalize legacy split nets on open, reinterpret old `FINAL_VALIDATED` as
engineering approval, regenerate saved geometry, rewrite reports or mutate old
snapshots. Historical reports retain their original scope/method and labels.

After explicit approval and a separately authorized implementation task, propose
conversion as a reviewable atomic operation on a copy: preserve conductor/terminal
IDs, record net aliases/lineage, reconcile domain/equivalence/voltage evidence,
update every affected reference and report freshness, then publish only through
the existing short revision transaction. Failed/conflicting conversion preserves
the prior revision and local edits/recovery. No catalog/project read transaction
stays open through optimization, routing or CAD serialization.

Coordinate versioned backend Pydantic/OpenAPI and TypeScript contracts, persistence
projections and fixtures. `wire_class` remains a routing class, not a phase type.
Add typed domains/equivalence/check records only through approved compatibility
work; schema changes require additive migrations, never edits to frozen generated
mappings. Review `ENGINE_VERSION` and generator/schema/report pins for any changed
connectivity, geometry or validation behavior. Approve deterministic merge/split
fixtures, round trips, finite values/units and dangling-reference rejection before
rollout. Preserve DuctRouter and terminal-to-route references, strict physical
generation, immutable assets and explicit document operation/concurrency fences.

## P0-T08 review checklist

The qualified reviewer must record scope, version of this ADR, named decision,
date, qualifications/authority and approved/rejected/deferred items in P0-T08;
this table contains proposals only. Do not treat silence as consent.

| Decision for qualified review | Proposal / outstanding evidence |
| --- | --- |
| DB supply and earth scope | Single explicitly identified supply; separate L1/L2/L3/N/PE; no PEN or N–PE bond. Confirm permitted supply/earthing systems and required cabinet/door/plate bonds. |
| Net and device boundaries | Maximal conductor/permanent-equivalence closure; breaker/SPD functional relations excluded. Confirm feed-through/bridge representation and multi-wire terminal evidence. |
| Persistent identity and drawings | Approve merge/split survivor and lineage policy, shared busbar canonicalization, and explicit electrical-junction operation; graphical crossings remain presentation. |
| Applicability and required inventory | Approve each rule family/scope and exclusion evidence; missing bend/diameter/earth data remains UNRESOLVED. Identify unsupported methods and required reference cases. |
| Values and provenance | No new engineering numeric reference values approved here. Assign reviewed source, units, tolerance and applicability for ratings, sizing, bends, fill, segregation, anchors and thermal checks. Synthetic/generic values remain preview assumptions. |
| Aggregation, labels and authority | Approve FAIL/UNRESOLVED blocking, evidence freshness and zero physical violations. Keep prototype and future engineering eligibility distinct; later method/data and P4-T16 release gates remain required. |
| Review outcomes | Accept/revise/reject E1–E6 expected outcomes and list any scope deferrals. Task acceptance approves delivery of this proposal only; it neither supplies D02 nor authorizes implementation. |
