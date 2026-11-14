# Lifecycle repair and continuation — 2026-11-13

## Verified diagnosis

P0-T05 attempt 2 successfully provisioned the pinned FreeCAD runtime, exported
STEP and reopened it in a fresh process. It found an existing exporter defect:
mounted-part bounds differed from the independent reference by up to 30 mm,
against the approved 0.05 mm bound tolerance. The native profile correctly failed.
This is a fixable implementation defect, not evidence that native CAD is impossible.

Evidence: `planning/task_reports/P0-T05/attempt-02.md` and its retained
`evidence-attempt-02/run-04/` artifacts. The exporter in
`backend/app/services/cad_engine.py:CADEngine.export_freecad_script` translates
a primitive before replacing its placement rotation; the native probe exposed
the resulting pivot discrepancy. This repair changes no application geometry.

The original task allowed an explicit unresolved prerequisite as an investigation
outcome, but also required a passing native qualification profile. The orchestrator
requires every mandatory profile to pass. Skipping P0-T05 therefore could not
satisfy the P0-T06 dependency. The report was not a wasted attempt: it supplied
the defect evidence needed to plan the correction.

## Adopted planning scope

Keep the full architecture. Separate investigation from implementation qualification,
correct strict ordering, and leave optional extensions deferred until selected.
Do not add blanket partial acceptance or convert failed geometry into passing evidence.

| Area | Revision | Remaining gate |
| --- | --- | --- |
| P0-T05 | Complete the comparison, evidence review and explicit issue register; `document_review` is mandatory. Negative experiments remain negative. | A new review attempt and human acceptance are required. |
| P0-T06 | Scope can approve the prototype MVP while native STEP and redistribution remain unqualified/deferred. | Product/technical approval remains required; distribution approval is required if distribution is selected. |
| P0-T07 / P0-T08 | Draft electrical semantics use contract/document review; qualified approval remains in P0-T08. | No dependent electrical implementation bypasses P0-T08. |
| P2-T12 | Declare browser bootstrap before P2-T10/P2-T11; remove acceptance that required those not-yet-built bindings. | Feature-specific tests accompany T10/T11; final cross-view tests are in T14. |
| New P5-T00 | Correct exporter pivot mapping, review generator compatibility, and pass retained native export/reopen regression evidence. | P5-T01 depends on it, so the native implementation branch cannot bypass the defect. |
| P8 | Keep all 20 tasks deferred, with original IDs. | P8-T02 selects branches; revise the DAG/R3 for unselected branches before activating implementation. |

The plan now has 119 tasks, 32 milestones and nine phases. One explicit correction
task was added; no feature was deleted merely to reduce task or session count.
The correction should be re-estimated at P0-T10; the existing phase estimates are
planning ranges, not a new commitment for the discovered defect.

Investigations may finish with a negative result when their deliverable is a
reviewed finding. Implementation tasks still require all their scoped criteria
and mandatory checks to pass. For oversized work, split the complete subset and
the outstanding subset into separate dependency-linked tasks. Do not allow a
generic PARTIALLY_COMPLETED result to satisfy dependencies.

Combining tasks is useful when they share ownership, outputs and independently
verifiable scope. This revision consolidates integrated browser acceptance into
P2-T14 rather than requiring it prematurely in bootstrap. It keeps implementation
and human engineering approval separate; merging those would obscure authority.

## Preserve progress and continue

Exit any active orchestrator/Codex task session first. The original lifecycle is
preserved byte-for-byte at
`planning/lifecycle_history/2026-11-13.before-repair.json`.
Back up the execution-state/history pair together with reports before adoption.
These local records can contain private notes and should not be committed.

From the repository root, with the orchestrator virtual environment active:

```sh
python -m orchestrator.main validate --lifecycle-only --require-models
python -m orchestrator.main reconcile --previous-lifecycle planning/lifecycle_history/2026-11-13.before-repair.json --preview
```

The actual preview preserves VERIFIED P0-T01, P0-T02, P0-T03 and P0-T04.
It adds P5-T00, removes no tasks, and invalidates changed/downstream current
records while retaining their attempts and decision history. Most affected
downstream records have never been attempted. P0-T05 retains attempt count 2
and becomes PAUSED pending a fresh scoped review.

Adopt only after reviewing that preview:

```sh
python -m orchestrator.main reconcile --previous-lifecycle planning/lifecycle_history/2026-11-13.before-repair.json
```

Confirm and supply a reason such as:

```text
Approve the scoped lifecycle repair: preserve unaffected accepted work, separate P0 investigation from P5 native qualification, correct browser ordering, and retain deferred extensions.
```

Then run:

```sh
python -m orchestrator.main validate
python -m orchestrator.main retry P0-T05
```

Suggested retry reason:

```text
Review existing native investigation evidence against the revised P0-T05 scope.
```

Suggested additional instructions (paste as one line into the single-line prompt):

```text
Review P0-T05 attempts 01 and 02 and their retained evidence against the revised investigation criteria. Preserve the native FAIL and 30 mm defect; do not rerun native qualification or fix application geometry in this review. Update the investigation issue register with mandatory P5-T00 correction/qualification, P5-T02 isolation, P5-T05/P5-T06 identity and P7-T03 distribution ownership. Check references and report document_review results. Write the new attempt report at the orchestrator-provided path; completion means the investigation is complete, not that native CAD is qualified. Do not modify lifecycle, execution state or historical reports.
```

For human input, confirm permission to review local evidence. Do not claim new
distribution or engineering approval. Independently review the resulting new
report, then accept if its investigation criteria and mandatory document review
pass. P0-T06 can then run and request its actual product decisions.

No automatic task acceptance or state migration is performed by preparing this
repair. The exporter defect remains outstanding until its correction is executed
and verified. Native output remains unqualified in the meantime.

## Recurrence prevention and validation

- Strict-order validation and launch preflight reject forward dependencies.
- Skip displays the direct tasks it will leave blocked.
- Acceptance errors identify the actual stored status instead of suggesting that
  the reviewer name/evidence text is necessarily wrong.
- Reconciliation requires the fingerprint-matching predecessor to preserve
  unaffected work; changed contracts/profiles/gates and downstream dependencies
  invalidate current acceptance. All prior evidence remains in history.
- The default reconciliation mode remains conservative. Do not run bare
  `reconcile` if you intend to preserve unaffected accepted tasks.
- Existing required engineering, security, native and release checks remain
  mandatory in their implementation/release scopes. Missing human access or
  approval must be planned before reaching those tasks; no plan can guarantee
  that all future experiments will succeed.

Executed verification on 2026-11-13:

- `orchestrator/.venv/bin/python -m unittest discover -s orchestrator/tests -t .`:
  **77 tests passed**. Includes preservation, downstream invalidation, changed
  profile/global-context invalidation, predecessor mismatch, active-attempt
  rejection, history retention, confirmation, read-only preview and restart tests.
- `validate --lifecycle-only --require-models`: passed; 119 tasks, no missing
  model mappings and no forward dependencies. Tests also checked task references
  and that each phase exit covers its tasks through dependencies.
- Reconciliation preview against actual saved progress: preserves all four
  VERIFIED tasks; adds P5-T00; removes none; no state/history migration committed.
- Migration/restart simulation using temporary copies of actual state/history:
  passed. P0-T05 retained both attempts, became PAUSED, and an explicit simulated
  retry produced READY with an attempt-03 prompt. Dry-run order was P0-T05,
  P0-T06, P0-T07, P0-T08, P0-T09 with lifecycle agent assignments and configured
  models. Subprocess mocking confirmed no Codex process was launched.
- SHA-256 checks confirmed live state/history, schema and both earlier attempt
  reports/prompts remained unchanged. `git diff --check` passed.

No application-development task or application test suite was run. The native
exporter defect has not been repaired by these planning/orchestrator changes.
