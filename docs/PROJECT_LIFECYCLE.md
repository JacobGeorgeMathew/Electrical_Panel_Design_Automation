# Project lifecycle

Apply the additive `0004_projects` migration before starting the updated application:

```sh
cd backend
python -m app.persistence.manage initialize
```

Use the existing private PostgreSQL configuration. No development project or saved
engineering revision is rewritten by this migration. `/ready` now expects this head.

The landing dashboard creates a project with name, description, location, and a
supported panel archetype. DB remains the supported engineering pipeline. Every
project has a database UUID; legacy project codes remain accepted. New projects
have requirements defaults but no CEM/PDM revision or generated geometry.

Open records a persistent last-opened timestamp. Search covers name, description,
and location. The dashboard supports rename, duplicate, delete, import and export.
Delete is a tombstone: normal project routes return 404 and listings omit the
project, while immutable history and shared assets remain retained.

Save project writes requirements, enclosure configuration and editor draft state.
Save & close returns to the dashboard only after a successful save. Save failures
and concurrent modification conflicts retain local edits. Editor placement and
schematic changes remain drafts; saving them does not change CEM connectivity or
publish manually placed engineering revisions. Automatic generation remains in
the workspace and creates a new immutable design revision using the existing engine.

Autosave writes an immediate browser checkpoint and, after 1.5 seconds of inactivity,
a server recovery checkpoint. Recovery accepts unfinished requirement input without
publishing it. Reopening offers Recover or Discard. Local checkpoints survive frontend
reload; PostgreSQL checkpoints survive backend restart. Saved project versions and
recovery versions reject conflicting writes from other tabs. Recovery based on an
older engineering revision restores inputs but does not apply incompatible editor
transforms. Explicit save or generation clears the server checkpoint. Generation
still replaces local editor drafts with generated geometry.

Project JSON packages (format `panelstudio-project`, version 1) contain saved metadata,
requirements, enclosure configuration, editor state and all saved CEM/PDM revisions.
They export saved state, not an unresolved recovery checkpoint. Import and duplicate
always allocate a new project UUID and new revision IDs and rebind project references.
Imports verify revision hashes, validate models and publish through the existing
transactional revision writer. Required catalog/archetype/model versions must exist
in the destination installation; catalogs and arbitrary executable files are not
imported. GLB and FreeCAD-script artifacts are rebuilt with installed generators.
The project import transaction rolls back on any invalid revision. Content-addressed
files created before a rollback may remain unreferenced; existing asset audit tooling
reports them. Packages are limited to 32 MiB and 200 revisions; recovery documents to
4 MiB. Import/export is not a portable PostgreSQL/catalog backup.

## API

- `GET /api/projects?q=&recent=false&page=1&page_size=50`
- `POST /api/projects`: existing contract plus `description` and `location`
- `POST /api/projects/{id}/open`
- `PATCH /api/projects/{id}`: expected version, optional metadata/requirements/configuration/workspace
- `DELETE /api/projects/{id}`: body `{ "expected_version": 1 }`
- `POST /api/projects/{id}/duplicate`: expected version and new name
- `GET /api/projects/{id}/export`
- `POST /api/projects/import`: versioned JSON package
- `PUT /api/projects/{id}/recovery`: expected project/recovery versions and document or null

Existing generation, revision restoration, catalog and engineering contracts remain.

## Verification

Backend lifecycle tests exercise creation, empty designs, saving, reopening through a
new application instance, recent/search, duplicate/delete, generated-design copying,
package integrity, recovery and stale versions. The PostgreSQL suite uses an isolated
test database when `PANEL_RUN_POSTGRES_TESTS=1`. Frontend tests cover dashboard actions,
empty creation, save/close, late saves, recovery and debounce behavior.
