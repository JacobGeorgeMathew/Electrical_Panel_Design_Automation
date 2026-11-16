# Task consolidation — 2026-11-15

The active lifecycle combines consecutive unstarted work assigned to the same
agent after P1-T09. Human approval and phase acceptance checkpoints remain
separate, as explicitly selected by the product owner. Completed tasks remain
unchanged. The example in the request is interpreted as P2-T06/P2-T07/P2-T08:
P1-T07 and P1-T08 are already verified and use different agents.

The plan has 94 executable tasks (previously 119), 31 milestones (previously
32) and nine phases. All 119 original task scopes remain represented. There
are 19 verified tasks and 75 remaining executable tasks. Removing executable
source IDs reduces orchestration units, not engineering scope or estimated work.

| Combined task | Original scopes, in execution order | Assigned agent |
| --- | --- | --- |
| P2-T06 | P2-T06, P2-T07, P2-T08 | backend_application_engineer |
| P2-T10 | P2-T10, P2-T11 | frontend_cad_engineer |
| P3-T11 | P3-T11, P3-T12 | security_release_engineer |
| P4-T01 | P4-T01, P4-T02 | electrical_engineering_agent |
| P4-T04 | P4-T04, P4-T05, P4-T06 | electrical_engineering_agent |
| P4-T09 | P4-T09, P4-T10, P4-T11, P4-T12, P4-T13 | physical_optimization_agent |
| P5-T00 | P5-T00, P5-T01, P5-T02, P5-T03, P5-T04, P5-T05, P5-T06 | cad_kernel_engineer |
| P6-T03 | P6-T03, P6-T04, P6-T05, P6-T06, P6-T07 | ai_integration_engineer |
| P8-T03 | P8-T03, P8-T04 | backend_application_engineer |
| P8-T06 | P8-T06, P8-T07 | cad_kernel_engineer |
| P8-T12 | P8-T12, P8-T13 | electrical_engineering_agent |
| P8-T18 | P8-T18, P8-T19 | quality_engineer |

## Contracts and references

- The first task ID survives; `merged_from` records every constituent source ID.
- Dependencies become the union of external prerequisites, mapped to surviving
  IDs. Internal dependencies are removed from the scheduler DAG and enforced by
  the labelled execution order. The whole combined task must pass before any
  downstream task can be accepted.
  A later developer-authorized completion override is available through menu
  option 11; it records accepted exceptions explicitly and retains all failed
  checks. See the orchestrator README for that separate acceptance workflow.
- Each source implementation step and acceptance criterion is retained with a
  source label. Outputs, inputs and required profiles are unioned. Human inputs
  retain their source labels. A combined task gets one report per attempt with
  evidence for every criterion and required profile.
- Release definitions, requirement traceability, operation coverage, acceptance
  scenarios and phase exits reference surviving executable IDs. Historical IDs
  in narrative text or labelled criteria identify the original scopes; use this
  table to locate their current owner.
- Runs may span milestones within one phase. Combined P5-T00 belongs to P5-M1;
  now-empty P5-M2 is removed. All other milestones remain. Original milestone
  membership is available in the exact predecessor archive.
- No human gate, phase acceptance, verified task, different-agent task or
  nonconsecutive work is merged. Optional P8 remains deferred (16 combined
  executable tasks representing the original 20 scopes).
- The original three-day sizing guidance applies to constituent scopes during
  execution. The owner's explicit grouping request creates larger execution
  units; do not silently unmerge the plan. Use further attempts if necessary,
  preserve reports, and require a reviewed plan change for scope adjustments.
- The existing JSON schema permits task extension fields; the orchestrator adds
  semantic validation for `merged_from` without changing the schema or old
  fingerprints. Agent/model configuration has no task overrides and remains valid.

## Adopt and continue

The exact prior lifecycle is archived at
`planning/lifecycle_history/2026-11-15.before-consolidation.json`.
Your live state/history and previous execution reports were not migrated or edited
while preparing this change. Exit any running orchestrator/Codex task first and
back up state/history together before adoption.

From the repository root, using the orchestrator environment:

```sh
python -m orchestrator.main validate --lifecycle-only --require-models
python -m orchestrator.main reconcile --previous-lifecycle planning/lifecycle_history/2026-11-15.before-consolidation.json --preview
python -m orchestrator.main reconcile --previous-lifecycle planning/lifecycle_history/2026-11-15.before-consolidation.json
```

Review the preview: P0-T01 through P0-T10 and P1-T01 through P1-T09 must be
preserved as VERIFIED. The adoption command asks for confirmation and a reason.
Suggested reason: `Approve same-agent task consolidation after P1-T09 while preserving all verified evidence and approval checkpoints.`

Use the full predecessor argument; bare `reconcile` conservatively invalidates
all acceptances. A fingerprint mismatch must be resolved against the correct
predecessor, never by deleting progress. Removed source records are retained in
`retired_tasks`; changed combined tasks start unaccepted. Reconciliation refuses
to merge any source with an existing execution attempt.

After adoption:

```sh
python -m orchestrator.main validate --require-models
python -m orchestrator.main --dry-run
python -m orchestrator.main
```

P1-T10 remains the next task, followed by P1-T11, P2-T01, P2-T02 and P2-T03.
No retry of P0-T05 or any completed P1 task is needed for this consolidation.

## Verification

Executed on 2026-11-15:

- `orchestrator/.venv/bin/python -m unittest discover -s orchestrator/tests -t .`:
  **83 tests passed**. New tests cover complete constituent requirement retention,
  exact preservation through P1-T09, consecutive same-agent membership, source
  provenance validation, combined prompt instructions, reference remapping,
  migration/restart and refusal to merge already-attempted scopes.
- Actual lifecycle validation with `--lifecycle-only --require-models`: passed;
  94 tasks, no missing model mappings and no forward dependencies. The suite
  checks all task references and phase-exit coverage.
- Actual saved-progress reconciliation preview: all 19 VERIFIED tasks preserved;
  25 source records retired; no live state/history update committed.
- Temporary-copy migration and restart: passed; all 19 verified records remained
  exactly equal to their originals, including attempts/acceptance evidence.
  Removed records were archived. The next five dry-run rows were P1-T10,
  P1-T11, P2-T01, P2-T02 and P2-T03, with correct agents and configured models.
  No Codex subprocess was launched.
- SHA-256 checks confirmed execution state/history, schema and model configuration
  were unchanged. `git diff --check` passed. The exact predecessor was archived
  before any lifecycle edit. No prior execution report was edited.

The live plan requires the explicit reconciliation command above before normal
orchestration can resume. No application implementation task was executed.
