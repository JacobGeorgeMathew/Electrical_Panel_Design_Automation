# Local execution diagnostics

P3-T11 diagnostics are JSON lines in `PANEL_DATA_DIR/diagnostics/execution.jsonl`
(default `~/.panelstudio/diagnostics`). The application installs its safe formatter
at startup, including for Uvicorn and SQLAlchemy logs. Messages, exception text,
tracebacks, SQL, arguments, request paths/query strings, bodies, labels and
requirement values are excluded. Only enumerated events/outcomes, controlled
failure codes, durations and correlation identities are recorded. Non-UUID opaque
identities are hashed; stage names use the server registry vocabulary. This
deliberately reduces third-party diagnostic detail.

Every request receives a server-generated `X-Request-ID`; supplied IDs are ignored.
Operation handler spans include document, project, batch and operation identities.
Enqueue events join the request to the durable job ID. Runner events reuse that
job/document identity after restart; nested stage attempts link their parent job.
Worker processes receive only the correlation context, never database sessions.
Stage, worker and request failure spans include elapsed milliseconds and codes.
Repository transition events describe transaction-local outcomes; a later rollback
can still discard the corresponding write. The database is the durable authority.

Normal diagnostics never serialize an error payload. Public engineering errors
retain structural details with credential/SQL/path filtering and sensitive fields
redacted. Request validation responses omit Pydantic input, context and dynamic
messages to avoid echoing submitted answers. Unexpected exceptions become generic
structured errors. Full raw exception records are not retained in another file.

Retention is bounded by `PANEL_DIAGNOSTIC_MAX_BYTES` (default 2097152; allowed
1024–16777216 bytes per file) and `PANEL_DIAGNOSTIC_BACKUPS` (default 3; allowed
1–10 backups). Invalid values stop startup. Rotation keeps at most backups + 1
files; files use owner-only permissions. This is size-based retention, not an age
guarantee. Keep application storage private and use one backend process per local
data directory; multiprocess/shared-file logging is unsupported. Restart does not
remove prior diagnostic files. Diagnostic logs are separate from immutable revision,
job and operation audit records; retention never deletes engineering history.
