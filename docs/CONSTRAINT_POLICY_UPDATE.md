# Strict placement and thermal constraints

## What changed

The reported 1.8 mm terminal gaps came from a special terminal-packing rule in CP-SAT and a matching backend exemption. The editor correctly applied a 4 mm DIN clearance, so it showed nine warnings. Terminals now obey the same declared minimum as the other DIN devices. The saved PDM carries `validation_policy`, and the 2D editor, 3D editor and server validator read those values.

The reported 0.502 W/L came from choosing an enclosure by plate size and its catalog heat-loss capacity while the final validator also applied a separate 0.45 W/L limit. Candidate selection now applies both limits before placement. It chooses a larger sealed catalog enclosure when needed, preserving the requested minimum IP rating. If placement/routing/validation fails, automatic selection tries the next feasible candidate. An explicitly selected enclosure is not silently replaced.

Generation publishes a revision only when its physical validation list is empty. Clearance and thermal failures are critical; even a remaining warning from a physical check prevents publication. Infeasible selections return a structured error and leave the previous revision unchanged. Old snapshots stay intact and are marked stale when they use an earlier generation engine. Generate a new revision to apply the updated rules.

For the 415 V / 3-phase / 250 A / 20% spare / IP54 examples:

| Feeders | Automatically selected enclosure | Prototype heat density | Minimum terminal gap |
|---|---|---|---|
| 12 | 800 × 1200 × 300 mm, IP54 | approximately 0.418 W/L | 5.4 mm |
| 16 | 1000 × 1200 × 300 mm, IP65 | approximately 0.387 W/L | 5.4 mm |

Both generated with zero physical validation violations. The actual generated PDMs also produced zero warnings when passed through the frontend's `analyzeEditorGeometry` function. Both saved 12-feeder demo projects were regenerated locally; the 16-feeder case was checked without saving another revision. The threshold remains 0.45 W/L and the minimum DIN gap remains 4 mm. Ventilation was not required for these examples. An arbitrary louvre/fan is not used to waive either the raw density limit or IP requirement. Actual temperature rise, airflow and manufacturer certification remain outside this prototype thermal model.

## Migration and seeds for every teammate

Commit/push the code changes and these new files together:

- `backend/migrations/versions/0003_constraints.py`: additive, data-only Alembic migration from `0002_app`; no table/column removal.
- `backend/migrations/versions/0003_constraints.seed.json`: frozen public seed data with layout values and strict policy.
- `backend/app/persistence/seed_constraints.py`: repeatable seed entry point.

The migration publishes DB_ENGINE_V1 rule-set version 2, DB_LAYOUT_CONFIG version 2 and DB_CONSTRAINT_POLICY version 1. It preserves previous published versions and project history. No new physical component or CAD asset definition is needed: this update uses the existing larger enclosure catalog and parametric models. Generated project assets remain reproducible by Generate Design and are registered with engine `db-pipeline-3`; primitive generator 2 is unchanged.

Before upgrading a database with valuable work, back it up with your normal PostgreSQL backup procedure. Keep credentials in private environment configuration; they are not part of migration/seed files.

### Existing Windows installation

From `backend/`, with the private database environment available:

```powershell
.\venv\Scripts\python.exe -m app.persistence.manage initialize
.\venv\Scripts\python.exe -m app.persistence.manage import-legacy
.\venv\Scripts\python.exe -m app.persistence.manage seed-constraints
.\venv\Scripts\python.exe -m app.persistence.manage status
```

### Arch Linux or another Linux installation

After pulling the matching source changes, activate the existing environment and load your private configuration:

```bash
cd ~/path/to/Electrical_Panel_Design_Automation/backend
source .venv/bin/activate
source "$HOME/.config/panelstudio/backend.env"
python -m app.persistence.manage initialize
python -m app.persistence.manage import-legacy
python -m app.persistence.manage seed-constraints
python -m app.persistence.manage status
```

Adapt the virtual-environment/private-configuration path if yours differs. Expected migration: `0003_constraints`; expected readiness: `True`. `initialize` applies the migration. `import-legacy` is an idempotent bootstrap for the component/hardware catalog and assets; it also attaches imported validation rules to the new rule set. `seed-constraints` is safe to repeat and does not create duplicate rule versions. A fresh database uses the same sequence after the database itself has been created.

After restoring an older `0002_app` transfer backup, run this upgrade sequence before starting the current backend. There is no need for another teammate's live database connection or a replacement dump to receive these changes.

Restart the backend, refresh the frontend, choose automatic enclosure selection (or a sufficiently large fixed enclosure) and click **Generate Design**. A previously saved model is not modified just by upgrading the database. Do not remove clearance/thermal warnings manually or edit an old snapshot to appear valid.

## Checks

Verified locally: 44 backend tests passed (including PostgreSQL tests), 27 frontend tests passed, and the production frontend build passed. The build still reports its existing large JavaScript chunk warning. The local database reports `0003_constraints (head)` and `Ready: True`; a pre-migration backup was created before applying the update.

`backend/tests/test_constraints.py` covers the exact 1.8 mm terminal case, 12/16-feeder zero-violation generation, unrounded thermal comparisons, refusal of undersized fixed enclosures, retry of a larger candidate, rejection of warning-bearing output, idempotent seeding, failed-publication preservation and upgrade from an existing `0002_app` database without rewriting saved history. Editor geometry tests cover matching terminal thresholds and edge-contact classification.

Run backend tests with `PANEL_RUN_POSTGRES_TESTS=1` to include the disposable-database tests; run `npm test` and `npm run build` from `frontend/`.
