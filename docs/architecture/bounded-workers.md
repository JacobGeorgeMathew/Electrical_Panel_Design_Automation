# Bounded execution and fenced completion

P3-T07 replaces CAD's in-memory export executor with PostgreSQL `CAD_EXPORT`
jobs and a single local consumer. Startup preserves queued work and healthy
leases. Only expired CAD leases are recovered by that consumer. Every attempt
gets a fresh token. Claims commit before computation; heartbeats and completion
use separate short transactions. The existing CAD submit/status API and
ArtifactView contract remain compatible. Repeated identical submissions at the
same project/document base return the same job and artifact identity.

Explicit Recompute still returns a review proposal synchronously. Its cache
misses now execute as durable `STAGE` attempts in separate bounded processes.
Materialization and cache reads finish before each workload starts. Each stage
stores a typed result only after checking its live token, document sequence,
project lock, document hash and input/signature evidence. The separate cache
sequence fence and explicit operation acceptance remain required. Save does not
schedule work, and neither a job nor its cache entry publishes a revision.
Expired stage attempts are recovered on subsequent explicit recomputation;
startup does not automatically accept or resume a review proposal.

The shared worker runs trusted server callables with multiprocessing `spawn`,
without inheriting database sessions. Defaults per workload are 120 seconds wall
time, 90 seconds CPU, 2 GiB address space, 32 MiB output and 64 file descriptors,
with core dumps disabled. At most two workloads run per backend process; excess
requests fail with `WORKER_BUSY`. The parent polls cancellation/lease ownership
and reaps the process on every exit. Runner transactions use 1 second lock and
2 second statement timeouts so blocked heartbeats fail instead of waiting
indefinitely. POSIX process groups let timeout/cancellation
kill native descendants. Resource limits require POSIX `resource`/`setsid`; other
platforms fail closed. Windows/Tauri packaging needs separate platform
qualification. This boundary does not authorize user-supplied Python or shell
commands and is not an untrusted-code sandbox. Native FreeCAD/STEP integration
remains separately scheduled; current exports are GLB and opaque Python scripts.

CAD attachment verifies managed blob integrity before the transaction, then
locks project, document and job. It checks the active owner/token and deadline,
base document sequence/hash, project lock, current revision and frozen input
signature. Attachment and terminal job success commit atomically. A superseded
job fails without attaching its blob; a cancelled or lease-lost worker cannot
attach. Duplicate completion cannot change accepted metadata. Worker crashes
after writing content leave a managed, unreferenced blob and preserve all prior
revision outputs. Recovery retries reuse content-addressed storage and the same
artifact row; no failure path deletes shared/historical files. Use existing
`audit-assets` reporting for orphan investigation; garbage collection is outside
this task.

Unexpected worker exceptions become controlled codes and generic messages;
their text, paths and credentials are not persisted. Expected engineering
`DesignError` responses retain the existing structured engineering contract.
Lease loss interrupts the child; database outages leave durable attempts
recoverable after expiry. Shutdown cancels local work. Explicit cancellation is
available to application code through `JobRepository.cancel`; public job controls
and asynchronous Recompute UX remain P3-T08. A terminal failed/cancelled execution
key is not silently reset. Local session authorization is the separate P3-T12
trust-boundary work; this change introduces no new public routes.
