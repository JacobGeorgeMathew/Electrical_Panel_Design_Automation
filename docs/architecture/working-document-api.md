# Working-document API v1

P1-T03 adds `GET` and explicit `PUT` Save at
`/api/v1/projects/{project_id}/document`. Project UUIDs and existing project-code
aliases are accepted in the path; payload ownership uses the canonical project
UUID. Open returns `DocumentView`: a resolved v1 document, its typed snapshots
and the engineering `content_sha256`. Reads verify stored hashes, identities,
references and supported schemas. No engine is called.

New projects receive an empty input-only document in the project creation
transaction, with stable document/panel UUIDs, S=0 and the current project lock L.
Its requirements are empty and its generated model references are null. All
stages are dirty. Its input catalog manifest identifies the selected archetype
version only; engine/generator/policy labels describe the intended contract, not
computed or validated outputs. Existing questionnaire defaults/answers remain in
the legacy project API. Old projects without document storage return 409
`DOCUMENT_NOT_INITIALIZED`; Open never silently converts historical revisions.

Save accepts `DocumentSave`:

```json
{
  "schema_version": "1.0.0",
  "document_id": "<document UUID returned by Open>",
  "expected_version": 1,
  "expected_document_sequence": 0,
  "requirements": {
    "project_id": "<canonical project UUID>",
    "archetype": "DB",
    "items": [],
    "is_valid": false,
    "validation_errors": [],
    "validation_warnings": []
  },
  "configuration": {}
}
```

Requirements and configuration are complete replacement input values, not
patches. Configuration defaults to `{}` and is restricted to the existing
`enclosure_id`/`enclosure_parameters` shape. Save validates finite numbers,
requirement IDs and structural ownership. Typed requirement states and messages
round-trip without being recomputed. Saved `is_valid` and diagnostics are input
metadata, never engineering approval; stage status remains dirty. Configuration
selection and engineering applicability must be checked by explicit computation
before publication. Missing/conflicting typed requirements may be persisted;
unfinished untyped inputs remain in the separate recovery document.

The bounded input Save cannot replace CEM, PDM, schematic, pins, provenance,
dirty stages or base revision. Later engineering edits use their separately
scheduled typed operation boundary. This API does not expose arbitrary aggregate
replacement before those operations exist.

Save serializes through the existing PostgreSQL project row lock. It checks L,
document ID and S before any write. A changed Save advances S and L exactly once,
stores a new immutable requirements snapshot and conservatively marks every
stage dirty. It retains prior referenced snapshots, existing generated snapshots,
head/base revision pointers, display/workspace and recovery checkpoints. A fresh
unchanged Save returns existing versions. No-op requests still require current
versions. No Save invokes calculations, placement, routing, CAD, publication or
artifact creation. The content hash excludes L/S/base pointer, retaining stable
engineering identity, inputs, references, pins, provenance and dirty status.

Failures use the existing structured error envelope, e.g.
`{"error":{"code":"DOCUMENT_CONFLICT","message":"..."}}`.
Stale L returns 409 `REVISION_CONFLICT`; stale S or document ID returns 409
`DOCUMENT_CONFLICT`. Ownership errors return 422 `DOCUMENT_IDENTITY_MISMATCH`;
invalid request shapes use FastAPI's structured 422 response. Corrupt or
incompatible stored values return 409 `DOCUMENT_INTEGRITY` with no internal paths
or SQL. Missing/tombstoned projects return 404. Failed saves roll back entirely;
clients must keep their submitted edits and explicitly reload/compare on 409.

L is read from the project, so metadata changes do not leave returned document
locks stale. This versioned endpoint coexists with legacy Save/generation and
does not synchronize their input projections or reinterpret old workspace
overlays. Clients must choose the versioned workflow explicitly. General
operations, idempotent receipts, conversion, complete immutable publications and
frontend workflow bindings remain separate lifecycle tasks. Prototype DB limits
and engineering review requirements remain unchanged.
