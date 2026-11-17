# Project lifecycle

Apply the additive migrations during an intended database setup or upgrade before
starting the application. The current head is `0007_stage_results`, following `0006_operations`,
`0004_projects` and `0005_design_documents`:

```sh
cd backend
python -m app.persistence.manage initialize
```

Use the existing private PostgreSQL configuration and preserve valuable data before
upgrading. `/ready` checks the current migration head. Do not run initialization as
incidental verification against a development database.

The landing dashboard creates a project with name, description, location, and a
supported panel archetype. DB remains the supported engineering pipeline. Every
project has a database UUID; legacy project codes remain accepted. New projects
have requirements defaults but no CEM/PDM revision or generated geometry.

Open records a persistent last-opened timestamp. Search covers name, description,
and location. The dashboard supports rename, duplicate, delete, import and export.
Delete is a tombstone: normal project routes return 404 and listings omit the
project, while immutable history and shared assets remain retained.

Save project writes requirements and enclosure configuration to the versioned
working document. Physical, schematic and electrical operations already persist
their accepted changes to that document, independently of Save.
Save & close returns to the dashboard only after a successful save. Save failures
and concurrent modification conflicts retain local edits. `MoveComponent` changes
working PDM geometry; `MoveSymbol` changes page presentation; electrical connection
operations change working CEM connectivity. Save does not regenerate, reroute or
publish any of these drafts. Reopen installs the saved working snapshots, and
shared undo/redo uses durable server history. Historical revisions remain frozen.
Legacy documents without a working aggregate retain their separate overlay adapter.

Autosave writes an immediate browser checkpoint and, after 1.5 seconds of inactivity,
a server recovery checkpoint. Recovery accepts unfinished requirement input without
publishing it. Reopening offers Recover or Discard. Local checkpoints survive frontend
reload; PostgreSQL checkpoints survive backend restart. Saved project versions and
recovery versions reject conflicting writes from other tabs. Recovery writes are
fenced by the independent recovery version, so a project Save does not prevent
retaining a draft against its original base. Explicit Recover applies only a
compatible schema and base; incompatible checkpoints remain available, including
their editor transforms, for conflict resolution or explicit Discard. Generation
retains edits made while its response is pending as a checkpoint against their
original base. Explicit legacy Save or generation clears the server checkpoint;
the versioned working-document Save preserves it.

Recovery envelopes now carry `schema_version: 2`, `recovery_sequence`, the original
`base_version` and `saved_at`. New documents carry `schema_version: 2`,
`baseRevisionId`, and `baseDocument` (document ID, document sequence and document
schema). The legacy editor explicitly sends `baseDocument: null` and uses its
project lock/revision as the compatibility fence; it does not infer a working
aggregate base. Versioned document consumers supply their actual loaded base.
Absent schema fields identify existing checkpoints and remain readable without
rewriting their bytes. Unknown schemas remain stored and cannot be auto-applied.
Browser storage retains its existing key for compatibility. Browser
`recovery_sequence` is the last observed server clock; it becomes authoritative
only in the server response. Project L, document S and recovery R are independent.

Project JSON packages use format `panelstudio-project`, version 2. They contain
saved metadata, legacy answers/configuration/editor state, the resolved working
document, and every saved revision's frozen output snapshots, manifests and hashes.
They exclude unresolved recovery checkpoints. Managed artifact bytes and referenced
catalog preview bytes are embedded as base64, deduplicated by canonical storage key.
FreeCAD scripts are transported as opaque downloadable bytes; import never executes
scripts or calls installed CAD, schematic, BOM or geometry generators.

The package `sha256` covers canonical JSON of all fields except that digest itself.
Each revision also carries CEM/PDM, revision and output-manifest digests and the
per-output hashes. Import verifies the full payload, source ownership, model
references, strict physical validation, artifact metadata and all required catalog
pins before creating a project. Catalogs are prerequisites, not package payloads;
missing versions fail explicitly instead of selecting current versions. Hashes
detect corruption, not sender authenticity or engineering approval.

Import and duplicate allocate new project, document, panel, revision and artifact
metadata identities. Stable device/terminal/net/route IDs stay intact. Schematic,
CAD, BOM, validation and artifact content hashes are preserved. Ownership-bearing
CEM/PDM, requirements, document and manifest containers acquire new hashes when
rebound. The exact original revision, all output snapshots and their hashes remain
available as `portable_source` in the new publication's DOCUMENT snapshot. Source
evidence retains original IDs; destination restore/conversion links are rebound
to the newly allocated revisions. The working aggregate starts at document sequence
zero with import provenance and no inferred base revision.

V1 remains importable with explicit legacy limitations: it contains CEM/PDM only,
so imported revisions report `MISSING_OUTPUTS`, have no transported artifacts and
require explicit compatibility conversion to create new representations. Import
does not pretend that installed generators recreate the original outputs. V2 can
also transport such incomplete history without manufacturing missing outputs.

Limits are 32 MiB of received JSON (including streamed requests), 200 revisions,
2,048 unique assets, 8 MiB per decoded asset and 16 MiB total decoded asset bytes.
JSON structure is bounded to depth 64 and 500,000 values. Asset paths must exactly
match `sha256/aa/bb/<hash>.<allowed-format>`; traversal, absolute paths, alternate
backends, duplicate asset entries and missing/corrupt content fail. Export rejects
unavailable or unfinished saved artifacts. All project/revision writes share one
transaction; verified content written before a later database rollback may remain
unreferenced. Existing asset auditing reports it without deleting shared files or
tombstoned history. Recovery documents retain their separate 4 MiB limit.
Import/export is not a PostgreSQL/catalog backup or an authenticated distribution
channel. Local session authorization remains the separately scheduled P3-T12 work;
the current application has CORS restrictions but no mutation session token.

## API

The frontend document adapter now loads `GET /api/v1/projects/{id}/document`
alongside the current frozen output. Save draft sends an input-only `PUT` to that
route with both the project lock and document sequence. Requirement item IDs and
unchanged state/provenance are retained; changed answers return to PROPOSED.
The saved aggregate supplies the answers and enclosure configuration on reopen,
even when legacy project inputs or published outputs differ. Workspace camera,
selection and visibility are excluded from that contract.

Versioned Save follows the input-only document PUT with a project metadata PATCH;
it excludes transient placement transforms and schematic overlays from that PATCH.
These writes are sequential, not atomic: if the PATCH fails after the document
Save succeeds, the frontend retains the advanced document fence, local edits and
an error for retry. It does not report a fully saved draft or publish anything.
The project PATCH retains its existing recovery-clear semantics; the document PUT
itself does not clear recovery. Recovery checkpoints use the loaded document base
and can retain unfinished local previews for explicit Recover or Discard.

The workspace labels saved/unsaved drafts separately from dirty engineering
output, historical read-only views and unsupported legacy missing outputs.
`Save project` / `Save draft` persists drafts. `Recompute required before Publish`
is a status message; no standalone Recompute control/service is available yet.
`Generate & publish revision (legacy)` names the combined compute/publication
endpoint accurately. It can initialize an untouched, input-only document. After
any changed-input Save, existing CEM snapshot or generation intent, every frontend
entry point shows disabled `Publish unavailable` with an explanation that separate
Recompute and Publish are pending. The store independently blocks those requests;
the server retains `GENERATION_PROPOSAL_REQUIRED`. Saving input drafts cannot make
that legacy action eligible again. Questionnaire single-field generation also shows
disabled `Automatic change unavailable` for versioned documents. Historical viewing
uses the explicit revision GET and guards Save, recovery writes, engineering
edits, rerouting, preview jobs and publication in the store as well as the UI.
Return to working draft reloads the saved aggregate. Missing working aggregates
use the legacy adapter only on `DOCUMENT_NOT_INITIALIZED`; network, integrity and
unknown-schema failures retain local data instead of falling back.

The [automatic generation proposal API](GENERATION_PROPOSALS.md) runs the bounded
DB pipeline against saved inputs without publishing. Review then explicitly accept
the returned `ApplyGeneration` batch to change the working document as one undo
group. Exact retries are idempotent; changed bases, protected manual models and
locked placements cannot be overwritten. Acceptance leaves CAD dirty and creates
no revision or artifact. The workspace has API helpers but no proposal review UI;
the Save → Recompute → Publish workflow for edited documents is incomplete.

The input-only Save remains the explicit P1 compatibility boundary in
[working-document-api.md](architecture/working-document-api.md). It advances project
and document versions for changed inputs but does not create an operation undo
group or replace CEM/PDM. Local unfinished entries and enclosure configuration
remain recoverable; accepted operations need no duplicate Save write. The literal
P2 acceptance criterion “All user mutation paths use shared operations” conflicts
with that retained boundary and the approved D01 Save direction. Human resolution
must specify whether input Save is an intended exception or a separately reviewed
operation-based submission rollout. This task does not change those definitions or
claim the literal criterion passes. See the [acceptance evidence](verification/phase-2-acceptance.md).

Physical operations enforce the saved placement policy but retain obsolete routes
as dirty. Required routing/physical/requirement checks may be `UNRESOLVED`; a
successful operation or a geometric PASS is not engineering approval. See
[workspace operation coverage](CAD_WORKSPACE.md) and the
[P2 acceptance evidence](verification/phase-2-acceptance.md) for tested paths and
current limitations. DB calculations, catalog geometry and thermal/fill limits are
prototype assumptions; native CAD and standards compliance are not established.

- `GET /api/projects?q=&recent=false&page=1&page_size=50`
- `POST /api/projects`: existing contract plus `description` and `location`
- `POST /api/projects/{id}/open`
- `PATCH /api/projects/{id}`: expected version, optional metadata/requirements/configuration/workspace
- `DELETE /api/projects/{id}`: body `{ "expected_version": 1 }`
- `POST /api/projects/{id}/duplicate`: expected version and new name
- `GET /api/projects/{id}/export`
- `POST /api/projects/import`: versioned JSON package
- `PUT /api/projects/{id}/recovery`: original base project version, expected recovery version and document or null; only the recovery version fences writes

Existing generation, revision restoration, catalog and engineering contracts remain.

## Verification

Backend lifecycle tests exercise creation, empty designs, saving, reopening through a
new application instance, recent/search, duplicate/delete, generated-design copying,
package integrity, recovery and stale versions. The PostgreSQL suite uses an isolated
test database when `PANEL_RUN_POSTGRES_TESTS=1`. Frontend tests cover dashboard actions,
empty creation, save/close, late saves, recovery and debounce behavior.
