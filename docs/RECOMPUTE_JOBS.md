# Recompute jobs

P3-T08 adds document-scoped HTTP transport over the existing durable jobs table.
No schema or generated engineering geometry changes are required.

| Request | Response / effect |
| --- | --- |
| `POST /api/projects/{project}/design/recompute/jobs` | `202`, queued job; body is the existing `RecomputeRequest`, with `Idempotency-Key`. No inline stage execution. |
| `GET .../jobs` | Most recent 20 recompute jobs for this live project. |
| `GET .../jobs/{id}` | Durable state, base clocks/hash, attempts, current stage, completed stage records and structured failure. Successful jobs include a review response. |
| `POST .../jobs/{id}/cancel` | Persist cancellation and revoke the active parent/stage leases. Terminal outcomes remain terminal. |

The existing synchronous Recompute endpoint stays compatible. The application job
runner consumes queued recomputes alongside CAD exports. Catalog materialization
and stage work run outside read transactions. Individual workloads retain the
existing bounded subprocess execution. A parent heartbeat covers materialization
and cached stages; completion rechecks the live lease and saved base under short
project/document locks. Each parent attempt scopes its own child jobs. Explicit
retry creates a new submission key; automatic expired-lease recovery remains bounded
by `max_attempts`. Neither completion nor cancellation changes working snapshots or
publishes a revision. Status never exposes worker inputs, execution keys or leases.

Live stage progress is derived from child job records because the frozen jobs
schema reserves `result` for success. Cache hits/retained steps appear in the final
execution records. Materialization and brief cache-only work have indeterminate
progress; the UI does not invent a percentage. Cancelled stage leases are revoked
immediately; process termination follows the existing bounded polling path.

The frontend persists the submission key, job ID, acceptance key and base/draft
fingerprint separately from engineering documents. It polls once per second without
overlapping requests while a working workspace is mounted. Unmount aborts polling
transport; only Cancel job cancels server execution. A lost submit acknowledgement
is reconciled using the same request/key. Recent server jobs permit discovery when
browser tracking is absent. Only the most recently tracked job is shown per project.
Selection, camera and visibility remain display state.

Explicit Apply uses the existing generation-proposal acceptance endpoint and shared
undo boundary. It checks the document ID, sequence, lock, hash and local draft state
before sending, and fences the receipt against edits/switches while in flight. If
the server accepted while the editor changed, the editor retains its newer state
and tells the user to resolve drafts and reopen. Lost receipts retain the exact
acceptance key. Background status success does not dismiss action conflicts.

Proposal review storage still has the existing process-local 15-minute/32-proposal
limit. A completed job survives reload/restart as evidence, but acceptance after
server restart, eviction or expiry returns a visible proposal-expired error; use
Retry recompute from saved base to obtain a fresh review proposal. This task does
not make proposal storage durable or implement publication, session authorization,
native CAD qualification or standards certification.
