# Working-document contract v1

P1-T01 introduces model contracts in `backend/app/models/document.py`,
`backend/app/models/schematic.py` and `frontend/src/types/document.ts`.
These contracts do not change the existing Save/generation endpoints or storage.
The D01-approved document semantics remain the implementation direction; this
task implements only the contract boundary, without operations, clocks advanced
by services, migrations, publication eligibility or historical-output conversion.

`WorkingDocument` carries schema `1.0.0`, opaque document/project/panel IDs,
document sequence S (starting at zero), project lock L, optional base revision,
configuration, snapshot references, version pins, provenance and dirty stages.
S is distinct from CEM's `revision` string, database revision number and recovery
version. Structural validation accepts dirty working content; it cannot declare
engineering PASS or authorize Publish.

Requirements, CEM, PDM and schematic are referenced by schema and SHA-256.
Requirements are mandatory; the other references can be null before computation.
Each reference uses snapshot envelope schema integer `1`; the aggregate and
schematic payload each use `1.0.0`. Unsupported versions are rejected without
automatic conversion. External version compatibility and catalog ownership must
be resolved by future services; a recorded pin is not proof of availability.

`ResolvedDocument` pairs metadata with all referenced typed snapshots. It checks
reference presence, project/panel ownership and hashes, then stable-ID uniqueness,
terminal/component/net membership, PDM bindings/routes/ducts, graph edges and
schematic symbol/pin/conductor references. A reference-only `WorkingDocument`
cannot establish those guarantees. Use the resolved boundary when accepting
engineering content; resolving storage and authorized catalog versions is still
the application's responsibility. Hashes use sorted compact UTF-8 JSON with
`ensure_ascii=False`, `allow_nan=False`, and fully defaulted Pydantic
`model_dump(mode='json')` values. This is compatible with the existing canonical
JSON encoding; do not reuse raw legacy snapshot hashes without explicit conversion.

Logical IDs remain opaque case-sensitive strings, preserved without normalization.
Uniqueness is scoped by namespace (component, net, connection, route, symbol,
pin, wire, etc.); this contract does not allocate IDs or permit their reuse.
External enclosure electrical endpoints require an explicit
`enclosure_interfaces` terminal registry. `PANEL_ROOT` receives no implicit bypass.
PDM components refer to CEM component IDs; route endpoints and net must match
their canonical CEM conductor. The saved validation policy version must match
the document pin. Numerical validation recursively rejects NaN and infinities,
including legacy dictionaries and numeric strings coerced by legacy typed fields.

Schematic presentation has exactly one page, finite schematic mm coordinates,
symbols referencing electrical components, pins referencing their terminals,
and wires referencing canonical conductors and presentation pins. Wire endpoints
must agree with CEM. Waypoints and symbol placement do not change connectivity;
crossings carry no connectivity authority. It is a new contract, not an automatic
reinterpretation of the current engine's untyped output. Future adapters must
explicitly map those outputs and preserve identities.

Physical snapshots retain enclosure mm, existing mounting-plate offsets and
rotation degrees. No transforms or recalculation occur during validation.
The shared synthetic fixture `frontend/src/types/fixtures/document-v1.json`
contains nonzero mounting offsets and exact decimal positions. Its pins/hashes
are deterministic contract data, not proof of real catalog availability or
engineering validity. Backend tests exercise all requirement states, reference
and version failures, hash integrity and FastAPI/OpenAPI errors; frontend tests
compile matching metadata/presentation and the fixture's structural shape.
TypeScript interfaces describe wire data; runtime acceptance remains on the
server. Snapshot-specific nullable views avoid changing existing UI contracts.

Malformed content raises structured Pydantic errors (including error type,
location and reference/path context where applicable), usable by FastAPI's
existing 422 validation response. No database, optimizer or CAD execution is
needed for these contract checks. Prototype DB assumptions and qualified
engineering/manufacturing review limits are unchanged.
