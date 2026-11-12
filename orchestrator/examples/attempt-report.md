# Example report structure — NOT evidence of task execution

This demonstration does not represent an attempt and must not be copied into the live task report directory as completion evidence.

## Task information
P0-T01, attempt 1, architecture_lead. Example only; no model/session was launched.

## Execution summary
No application lifecycle task executed. This demonstrates an incomplete report.

## Implementation details
None. Application implementation is unchanged by this example.

## Files modified
None for P0-T01.

## Acceptance criteria and results
1. Inventory with source symbols: UNVERIFIED; task was not performed.
2. Mutation paths with version/precondition records: UNVERIFIED; task was not performed.

## Commands executed
None for this illustrative attempt.

## Test and build results
NOT_RUN. Do not confuse orchestrator unit tests with lifecycle task verification.

## Verification profiles executed
document_review: NOT_RUN.

## Problems encountered
The example contains no execution evidence.

## Remaining work
Execute the real task, perform document review and provide concrete references.

## Recommendations
Configure the lifecycle agent model and inspect the generated prompt before launching a real task.

## Final execution assessment
PARTIALLY_COMPLETED. Example only; acceptance is intentionally impossible.

## Git branch and commit information
Not applicable to this non-execution example.

## Uncommitted changes
Not assessed by this example. Real reports must record actual changes.

```orchestrator-result
{
  "task_id": "P0-T01",
  "attempt": 1,
  "assessment": "PARTIALLY_COMPLETED",
  "acceptance_criteria": [
    {"index": 1, "result": "UNVERIFIED", "evidence": "Example only; no inventory was produced."},
    {"index": 2, "result": "UNVERIFIED", "evidence": "Example only; no mutation-path audit was performed."}
  ],
  "verification_profiles": [
    {"id": "document_review", "result": "NOT_RUN", "evidence": "Example only; no task review took place."}
  ]
}
```
