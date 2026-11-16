# Bounded DB connectivity projection

P2-T05 implements the academic prototype topology basis in
[D02](../decisions/approved-electrical-semantics.md), especially E1–E3 and the
identity/connectivity portion of C01/C02. Qualified engineering review remains
deferred. Software fixtures are synthetic topology expectations, not independent
engineering approval, terminal capacity evidence or reference-value approval.

## Service contract

`backend/app/services/electrical_consistency.py` exposes
`project_legacy_connectivity(cem, *, domains=None, equivalences=())`.
It returns an immutable Pydantic `ConnectivityProjection` with schema version
`db-connectivity/1`. Supply/role assignments use `(component_id, terminal_id)`
keys and explicit `ElectricalDomain(supply_id=..., role=...)` values. Roles are
limited to L1/L2/L3/N/PE. Inputs are caller-supplied topology evidence; the service
does not authenticate review provenance or load the latest catalog.

Each `ConnectionRef.id` represents one conductor. Conductor direction is a
reference orientation. Sharing a terminal joins conductors into one maximal
undirected equipotential group without combining their identities or quantities.
Parallel conductors remain separate. Declared unused terminals remain singleton
groups; their presence does not invent an obligation to connect them.

Different screws join only through an explicit `TerminalEquivalence` with an
evidence ID. This bounded profile permits internal groups within one BUSBAR,
NEUTRAL_BAR, EARTH_BAR or TERMINAL component. Cross-component installed bridges
and permanent groups through breakers, switches, SPDs or loads are unsupported.
A missing evidence ID leaves distinct screws separate and records UNRESOLVED.
Known incompatible roles or supplies fail even for an unevidenced proposal.
Providing any evidence string alone does not establish product applicability.

Functional graph edges, terminal coordinates, labels, legacy net names, nominal
voltages and wire classes never create equipotential unions or phase assignments.
Functional graph identities/references are checked separately. Explicit domains
are checked over the full connected closure, including paths through terminals
with missing domains. Different known supplies or incompatible phase/N/PE roles
fail. PEN and N–PE union have no supported role/interface in this profile.

Nested net conductors and the flattened CEM conductor list must agree by ID and
complete content; list ordering does not affect this comparison. Duplicate IDs,
dangling references, invalid IDs, self-connections, empty nets, nonfinite legacy
voltages and incorrect containing-net references fail with stable issue codes.
Issue ordering, member ordering and output group ordering are deterministic.
Any FAIL produces no groups or legacy mapping, preventing use of a partial
failed partition. `require_consistent()` raises a structured `DesignError` for
FAIL or UNRESOLVED. Historical preview callers may explicitly use
`require_resolved=False`; known failures still raise.

## Compatibility and identity

This service is an explicit read-only analysis entry point. It is not wired into
historical revision reads, generation, save, recovery, operation application or
HTTP schemas. No migration or automatic conversion occurs. Existing CEM/PDM,
OpenAPI and TypeScript contracts, engine/generator version pins and baseline
payloads remain unchanged: the service neither generates geometry nor changes
serialized engineering output. A future published conversion must separately
review those pins and atomically update affected projections/references.

Legacy split net IDs can refer to one actual equipotential. The projection labels
that group with the lexical minimum predecessor ID and lists all predecessor
IDs. It preserves every conductor ID and every legacy net's voltage observation
and routing class. It does not select a canonical voltage or infer voltage
reference from those observations. Mixed 415 V / 239.600… V observations in E1
remain historical data requiring separate voltage-reference reconciliation.

One legacy net can also contain disconnected conductor groups. Its ID is assigned
only to the class containing its smallest surviving terminal key; other classes
may have `net_id=None` until a later explicit conversion allocates identities.
`legacy_net_ids` on every group retains predecessor membership.
`legacy_nets[].equipotential_ids` lists only assigned projection labels; it is not
a complete split-allocation receipt. A split records `LEGACY_NET_SPLIT` as
UNRESOLVED. An isolated terminal with no predecessor also has `net_id=None`.
These projection labels never replace historical connection/net references.

Legacy inputs without explicit domains remain representable with
`MISSING_TERMINAL_DOMAIN`. Only the exact virtual pair
`PANEL_ROOT:EARTH_STUD` is allowed as a historical endpoint; it always records
`VIRTUAL_PE_ANCHOR` as UNRESOLVED. An explicit non-PE role at that endpoint fails.
A real stud, required cabinet/door/plate bonds, termination capacity and reviewed
earthing applicability require separate evidence; this virtual endpoint proves
none of them.

## Verification boundary

`backend/tests/test_electrical_consistency.py` exercises E1's three-conductor
shared junction and breaker boundary, E2's explicit screw equivalence, the full
pairwise incompatible-role table, transitive conflicts, separate supplies,
identity/reference failures, parallel conductors, disconnected legacy nets,
functional/coordinate non-unions, deterministic errors and JSON round trips.
It checks that historical JSON bytes, CEM serialization, hashes and references
are unchanged and projects currently supported generated 4/8/12/16-feeder DB
netlists. The published prototype catalog currently supplies 3P incomers; no
single-phase product support is claimed.

PASS in this service is limited to the implemented topology checks. It does not
evaluate terminal wire count/capacity, required feeder or bonding inventory,
conductor sizing, protection, voltage references, physical routes or engineering
release eligibility. Those checks remain due under D02 and later reviewed work.
No new manual electrical edit/publication command is introduced by this task.
