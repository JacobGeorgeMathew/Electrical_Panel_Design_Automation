# Explicit incremental recomputation

P3-T05 adds `services/stages/scheduler.py` over the registered DB stage DAG.
The scheduler reads server-owned working-document dirty stages, expands their
downstream closure, and executes detached adapters in dependency order. Missing
CEM, PDM or schematic snapshots establish their producer roots. Existing clean
prerequisites come from the resolved working snapshots. Save remains input-only.

`POST /api/projects/{project_id}/design/recompute` requires:

```json
{
  "document_id": "loaded-document-id",
  "expected_document_sequence": 3,
  "expected_version": 4
}
```

The response extends `GenerationProposal` with `scheduled_stages` and
`stage_executions`. Records contain the registered stage, adapter, status
(`EXECUTED`, `CACHED`, `RETAINED`, `FAILED`), actual adapter invocation count,
elapsed milliseconds and input signature. Placement includes enclosure, zoning
and ducts sub-adapters. Rejected enclosure attempts remain visible in records.
An engineering failure includes attempted records in its structured error details.
The scheduler retries feasible enclosure candidates through routing/validation,
matching full generation's retry scope. Every warning still blocks generation.

Recompute computes and retains a candidate; it does not accept an operation or
publish a revision. Review `preview.candidate`, then explicitly submit the returned
`batch` to `/design/generation-proposal/accept` with `Idempotency-Key`. This uses
the existing retained server proposal, optimistic fences, atomic operation writer,
idempotent receipts and undo/redo snapshots. Changed input, expiry or server restart
requires another Recompute. Recompute approval is not electrical engineering or
task acceptance. Publication remains a separate lifecycle action.

Ordinary generation proposals retain their existing manual-intent conflict rules.
Recompute uses manual components/topology, locked physical assembly and manual
schematic presentation as authoritative inputs. It never grants clients a flag
to bypass those rules. Manual schematic presentation is retained and its references
are checked on the resolved candidate. Unsupported reconciliation fails; it does
not silently erase intent. Component moves retain catalog-local terminal offsets;
routing transforms these into enclosure coordinates exactly once.

Catalog reads finish before adapter execution. Ordered catalog content identities
bind exact materialized input payloads alongside published row-version IDs.
Existing aggregate pins must match; old generation documents without aggregate
pins have their saved component/product versions checked before binding the
catalog content identities. Unavailable saved rules/catalogs require an explicit
upgrade workflow. Catalog collection queries use deterministic ordering so query
plans cannot manufacture false catalog changes. This endpoint does not implement
historical catalog resolution or a catalog-upgrade operation.

Each adapter uses the P3-T04 typed signature and verified append-only cache. Cache
metadata is sequence fenced. Cache hits do not invoke engineering. Engineering
snapshots are only installed by explicit operation acceptance; cache completion
alone does not make a candidate current. Save, load and propagation previews do
not run this scheduler. Camera/selection edits do not schedule stages; a device
move schedules routes, physical validation and CAD, with no calculations or
netlist generation. CAD adapters still perform their independent eligibility check.
Records count adapter entries; internal validation calls are not separate jobs.

`POST /design/propagate-change` now returns `{status: "PREVIEW", persisted: false,
batch, preview}` for one `UpdateRequirement`. Commit the ordinary operation through
the document operations API, explicitly Recompute, then accept its result. The old
`new_design`/`diff_report` automatic-publication response is removed; the TypeScript
client and legacy consumer use the new contract. No revision is produced by preview,
operation acceptance or Recompute. A dedicated Recompute button and durable worker
leases/retries remain later UI/execution work.

The unchanged full `DesignOrchestrator` remains the independent oracle for
automatic generation. Tests compare both frozen DB examples and a changed feeder
count, then compare incremental and full stage recomputation with retained manual
intent. These are prototype engineering checks; primitive CAD/script generation
does not verify native FreeCAD/STEP or manufacturing/standards compliance.
