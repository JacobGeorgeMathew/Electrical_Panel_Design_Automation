# PanelFlow development orchestrator

A sequential Python controller for the existing lifecycle, using the interactive Codex TUI. It does not run application-development tasks until you confirm a launch, and it never accepts a task automatically.

## Quick start

Run from the repository root. Use a separate Python environment; the orchestrator does not depend on the FastAPI application's environment.

```sh
python -m venv orchestrator/.venv
source orchestrator/.venv/bin/activate
python -m pip install -r orchestrator/requirements.txt
python -m orchestrator.main validate
python -m orchestrator.main --dry-run
python -m orchestrator.main setup-models
python -m orchestrator.main init
python -m orchestrator.main
```

The final command starts the controller, not an unattended batch. Every Codex launch requires confirmation; the program returns after a task decision. Only an explicitly requested retry can launch another attempt, with another confirmation.

### Backend environment during Codex tasks

The orchestrator supplies environment instructions automatically in every generated task prompt, including retries. You do not need to repeat them in each Codex session. Deactivating a virtual environment does not remove its packages, and a second terminal can use the backend environment independently.

Codex inherits the controller's process environment, so the prompt explicitly selects `backend/.venv/bin/python` for backend commands. From `backend/`, it selects `.venv/bin/python` and invokes tools with `-m`. For example, when backend tests are authorized, the command from the repository root is:

```sh
(cd backend && .venv/bin/python -m pytest)
```

The prompt preserves verification-profile arguments, environment flags and database-isolation requirements. It instructs Codex to check the backend interpreter, report missing/broken environments, avoid falling back to the controller's Python, and keep dependency installations separate. Frontend checks continue to use npm from `frontend/`. These are instructions to Codex, not automatic environment creation or shell-command rewriting; inspect the actual commands in its execution report.

## Repository inspection and supported environment

Inspected on 2026-11-11: clean initial working tree, branch `phase_1`, commit `8ee52fd57c7c2762f83132f4362330d7759d9f95`; root `AGENTS.md`, no nested agent instruction files found. Current application: FastAPI/Python, PostgreSQL, CEM/PDM, React/TypeScript/Zustand, Three.js, React Flow and Tauri. The orchestrator lives outside application source and changes none of those modules.

The discovered authoritative files are:

- `planning/development_lifecycle.json`
- `planning/schema.json` — this is the actual schema filename, not `development_lifecycle.schema.json`.

The consolidated plan contains **9 phases, 31 milestones, 94 tasks and 11 specialist agents**. All 19 verified tasks through P1-T09 retain their exact definitions. The 119-task predecessor is archived at `planning/lifecycle_history/2026-11-15.before-consolidation.json`; the earlier 118-task plan is also retained. Counts and assignments are read from the active lifecycle.

**Strict order is intentional.** You selected stop-at-blocker behavior. The lifecycle declares P2-T12 before combined P2-T10 (which includes former P2-T11), and limits the harness to bootstrap. Integrated checks follow implementation. Validation rejects forward dependencies; the orchestrator never silently reorders tasks. A skipped task remains unverified and cannot satisfy a dependent task.

P0-T05 accepts a reviewed investigation, including failed native experiments. Mandatory combined P5-T00 owns the exporter correction, native qualification and subsequent CAD worker/assembly/export implementation in constituent order. Sixteen consolidated P8 tasks remain deferred until explicit selection/activation. See [the consolidation guide](../planning/TASK_CONSOLIDATION.md) and the historical [repair guide](../planning/LIFECYCLE_REPAIR.md).

Combined tasks keep their first source ID and a `merged_from` list. All original criteria, steps, outputs, inputs and verification profiles remain required for ordinary acceptance; steps/criteria carry source labels. The prompt instructs Codex to complete constituent prerequisites first and report evidence for each original scope. One combined task may require multiple interactive attempts. The developer may explicitly accept a partial result using option 11 below; this records each outstanding exception instead of changing the reported checks. Human approval and phase acceptance checkpoints remain separate.

## Prerequisites and Arch Linux setup

Use Linux, Python 3.10+, Git and a real interactive terminal. Arch's Python installation includes `venv`; install the Python/Git packages through your normal Arch package-management workflow if absent. `jsonschema==4.26.0` is the only direct Python dependency; tests use standard-library `unittest`. Do not install dependencies into the system interpreter or the application backend environment.

Codex CLI must already be installed and authenticated for your account. Inspect your installation:

```sh
codex --version
codex --help
codex login --help
codex login
codex login status
```

Use the [official Codex CLI installation documentation](https://developers.openai.com/codex/cli/) if it is missing. Authentication is managed by Codex; the orchestrator neither reads authentication files nor stores credentials. There is no requirement to obtain an API key if your Codex authentication already provides access.

The inspected local version was `codex-cli 0.167.1`. Before every launch the controller checks installed help for the required interactive arguments. It uses `codex [OPTIONS] [PROMPT]`, not `codex exec`, App Server, worktrees or background task automation.

## Modules and data ownership

| Module | Responsibility |
| --- | --- |
| `lifecycle_loader.py`, `lifecycle_validator.py` | Load the existing schema, validate tasks and references, preserve order, detect cycles. |
| `task_scheduler.py` | Stop at the first pending task unless it is dependency-ready; expose progress and blocker queries. |
| `agent_registry.py`, `model_selector.py` | Keep lifecycle assignments; resolve explicit agent/task model settings. |
| `prompt_generator.py` | Include task, context, rules, prerequisite evidence, verification and mandatory report contract. |
| `codex/interactive_dispatcher.py` | Start one interactive Codex process with inherited stdin/stdout/stderr. |
| `progress_tracker.py`, `io_utils.py` | State transitions, attempts, atomic snapshots, recoverable journal, append-only history and process lock. |
| `report_manager.py` | Inspect Markdown sections and structured results without executing report content. |
| `decision_manager.py` | Human acceptance, gate decisions, retries, reopening and dependency invalidation. |
| `git_safety.py` | Read-only Git branch, commit and working-tree snapshots. |
| `terminal_ui.py`, `main.py` | CLI, dry run, confirmation and review menus. |

```text
read-only lifecycle + schema       explicit model configuration
             |                                  |
       validation -> strict scheduler -> generated task prompt
                              |                 |
                       human confirmation -> interactive Codex
                                                |
                           immutable attempt report + exit status
                                                |
                      human evidence review and required decisions
                                                |
                       atomic execution state + append-only events
```

Python owns execution state. Codex implements one selected task and writes its report. The controller never runs verification commands itself: it supplies the lifecycle's profiles, parses reported results and requires your evidence review. A report's `COMPLETED` claim or exit code zero is insufficient for acceptance.

## Configuration

`config/execution_config.json` contains repository-relative lifecycle, schema, state, history, report and model-config paths. `project_repository_root` is relative to the configuration file, so the supplied `../..` works without machine-specific paths. Other paths must remain inside that root. To use an alternate config:

```sh
python -m orchestrator.main --config path/to/execution_config.json status
```

Options:

- `approval_behavior`: `on-request`. Permission-bypass modes are rejected.
- `require_launch_confirmation`: must be `true` in this version.
- `show_dry_run_on_startup`: print the first five tasks and prompt before the initial menu.
- `stop_after_failed_task`: a requested retry is saved but not relaunched in the same invocation after a nonzero/missing exit code, interruption or FAILED report assessment.
- `stop_after_incomplete_report`: likewise stop after a missing or structurally incomplete report.
- `scheduling_policy`: must be `strict`, matching your chosen ordering rule.

Normal Codex permissions remain available. The invocation explicitly selects `--ask-for-approval on-request` and `--sandbox workspace-write`; managed Codex policies can impose additional constraints. Launch confirmations cannot disable Codex command approvals.

Do not place secrets in configuration, review notes or reports. Runtime state/history/reports are ignored by Git using `planning/.gitignore`; back them up together. Model mapping files contain settings only, never tokens.

## Agent-to-model setup

All 11 actual lifecycle agents have **null model/effort templates**. No default model is silently selected. In a separate interactive Codex session, inspect `/model` and confirm with `/status`. The picker is account/workspace-specific; see the [official command documentation](https://developers.openai.com/codex/cli/slash-commands/).

Then run the setup wizard:

```sh
python -m orchestrator.main setup-models
```

For each agent, enter the exact model ID and an effort supported by that model. A blank model keeps its mapping unchanged. Alternatively, after replacing the shell placeholders with values observed in your CLI:

```sh
python -m orchestrator.main set-model architecture_lead YOUR_MODEL_ID YOUR_SUPPORTED_EFFORT
python -m orchestrator.main set-model P0-T01 YOUR_MODEL_ID YOUR_SUPPORTED_EFFORT --task
python -m orchestrator.main validate --require-models
```

Those placeholder tokens are **not model recommendations or valid configured defaults**. `set-model` asks you to attest the pair is supported. Task overrides specify an explicit model/effort pair and take precedence over the assigned agent's pair; they never change the agent assignment. To override only effort, supply the same model with the new supported effort.

The CLI passes `--model MODEL` and `--config 'model_reasoning_effort="EFFORT"'`. The configuration key and model-dependent effort behavior are documented in the [official configuration reference](https://developers.openai.com/codex/config-reference/). Accepted configuration spellings include `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra`; this does **not** mean every model supports every spelling. Offline validation checks syntax and explicit confirmation, not provider entitlement or model availability. A provider rejection remains a failed/unverified attempt.

You can inspect status and dry-run prompts while mappings are incomplete. Actual launch is blocked with a setup instruction. `validate` validates lifecycle/state and reports missing mappings; `validate --require-models` also fails on any missing mapping.

### Suggested starting mappings for this lifecycle

These are project-specific recommendations, not benchmarks or confirmation of account access. Check each pair in `/model` before configuring it. The [official model guidance](https://learn.chatgpt.com/docs/models?surface=cli) positions GPT-6.1 Sol for repeated complex work, Astra for the most demanding work, Terra for writing/visual work, and Luna for focused repeatable tasks. Plus availability and reasoning options must still be checked in your signed-in CLI.

| Lifecycle agent | Suggested model ID | Effort | Project-specific reason |
| --- | --- | --- | --- |
| `architecture_lead` | `gpt-6.1-sol` | `high` | Cross-model contracts, document authority and dependency decisions. |
| `database_engineer` | `gpt-6.1-sol` | `high` | Migrations, immutable revisions, transaction boundaries and recovery. |
| `backend_application_engineer` | `gpt-6.1-sol` | `medium` | Routine service/API work; raise to high for commands, jobs and concurrency. |
| `frontend_cad_engineer` | `gpt-6.1-sol` | `medium` | React/Zustand editing and synchronized views; raise to high for transforms and undo. |
| `electrical_engineering_agent` | `gpt-6.1-sol` | `high` | Traceable methods, connectivity invariants and independently checked calculations. |
| `physical_optimization_agent` | `gpt-6.1-sol` | `high` | CP-SAT constraints, duct routing and geometry edge cases. |
| `cad_kernel_engineer` | `gpt-6.1-sol` | `high` | Kernel integration, coordinate transforms, assembly identity and export validation. |
| `ai_integration_engineer` | `gpt-6.1-sol` | `medium` | Structured proposals and retrieval; raise to high for approval/security boundaries. |
| `quality_engineer` | `gpt-6.1-sol` | `high` | Independent test design, failure injection and concurrency/history invariants. |
| `security_release_engineer` | `gpt-6.1-sol` | `high` | Trust boundaries, permissions, backup integrity and release recovery. |
| `technical_writer` | `gpt-6.1-terra` | `medium` | Clear documentation grounded in supplied implementation evidence. |

Use task-level overrides for especially ambiguous architecture, solver or kernel investigations: try `gpt-6-astra` at `medium`, increasing to `high` only when the results justify it. For tightly scoped test maintenance, formatting or report extraction, try `gpt-6-luna` at `high`; keep broader QA acceptance work on Sol. Terra is also worth trying for screenshot-based UI review and small visual fixes. GPT-6 Sol (`gpt-6-sol`) can be an alternative when available and preferred, but the table deliberately uses the current GPT-6.1 Sol starting point.

This is a conservative starting allocation for repeated Plus development sessions, not a claim of a particular token saving or subscription allowance. Compare results on representative tasks before expanding cheaper/faster overrides. Model choice never replaces the required human engineering approvals. The live `agent_model_config.json` is not populated or marked confirmed by these recommendations; use `setup-models` after checking your account's picker.

## Execution and human review

At startup the controller shows actual counts, verified/failed/blocked/remaining tasks, current phase/milestone, the next eligible task and ordering conflicts. Before launch it shows agent, model, effort, dependencies, report path, Git branch/commit and existing edits. It never commits, pushes, merges, resets, deletes edits or creates worktrees.

After Codex exits, the entire report is displayed, including acceptance results, problems, remaining work and recommendations. Available decisions:

1. **Accept**: explicitly attest independent evidence review and supply reviewer name/evidence references.
2. **Review report**: show the current report again.
3. **Retry**: preserve history and request another attempt.
4. **Retry with instructions**: preserve original task criteria and add human instructions.
5. **Reopen**: invalidate a previous acceptance and verified downstream acceptances; retain all prior evidence.
6. **Skip**: advance past an explicitly skipped task, without satisfying dependencies.
7. **Mark blocked**: record a human blocker requiring explicit resolution/retry.
8. **Pause/exit**: preserve current state. A reviewable task remains `NEEDS_REVIEW`.
9. **Record human gate approval**: supply a named authorized approver and signed-decision evidence.
10. **Confirm human input**: record required external input without storing secrets.
11. **Mark partial task completed (human override)**: review the latest partial report and outstanding checks, supply your name, evidence and rationale, then explicitly accept responsibility for completing the task with those exceptions. Unlocks dependent tasks.
12. **Mark any task completed (bypass all acceptance checks)**: select any task ID (blank selects the current task), optionally enter a developer name/note, and confirm. Works from every status, including tasks with no attempts. No report, successful exit, passing checks, completed dependencies, human input or gate approval is required.

Ordinary acceptance (option 1) requires exit code zero, a complete unchanged `COMPLETED` report, PASS evidence for every required criterion/profile, unchanged verified prerequisites, and explicit human acceptance. Human-gate tasks additionally require approval for that attempt from a named approver. Required human inputs must be recorded.

Option 11 allows you to mark a `PARTIALLY_COMPLETED` task **COMPLETED by human override**, including when criteria/profiles contain FAIL, NOT_RUN or UNVERIFIED. It displays the complete report and lists all non-PASS checks before asking for your name, reviewed evidence, rationale covering remaining work/follow-up, and responsibility acknowledgement. This is available immediately after a session or later through:

```sh
python -m orchestrator.main review TASK-ID
```

Replace `TASK-ID` with the actual task ID, then choose **11**. This is a separate decision from ordinary acceptance; an exit code or Codex claim never triggers it automatically. Cancelling the confirmation leaves the task partial.

Python saves `status: VERIFIED` so the existing scheduler treats the task as completed. Its acceptance additionally records `mode: HUMAN_OVERRIDE`, `human_assessment: COMPLETED`, the original `PARTIALLY_COMPLETED` assessment, your rationale, responsibility acknowledgement, and each accepted exception with its original result/evidence. The original attempt/report, test results, report hash and attempt count remain unchanged. A `TASK_COMPLETED_BY_HUMAN_OVERRIDE` event and human decision retain the audit trail; status output lists tasks completed this way. Downstream prompts receive the acceptance record, including exceptions.

The override requires a valid unchanged latest partial report with exit code zero and current lifecycle context. It does not accept missing/malformed reports, failed processes, stale or incomplete prerequisites, missing explicit human-gate approval or missing required human input. Use options 9/10 for the latter approvals/input; retry/recover when execution evidence is invalid. Tasks already skipped/blocked/paused must be retried to produce a current partial attempt before using option 11. The override records your choice to accept outstanding work; it does not convert a failed test into a passing test. Reopening the task preserves the override decision and invalidates dependent acceptances as usual.

The software records your assertion of authority and review; it cannot verify professional qualifications, physical measurements or whether evidence is truthful. Those remain human responsibilities.

### Unrestricted manual completion

Use option **12** from the decision menu. To open that menu for any task, including
one that has never run:

```sh
python -m orchestrator.main review TASK-ID
```

Or go directly to the same manual-completion action:

```sh
python -m orchestrator.main complete TASK-ID
```

Replace `TASK-ID` with an actual lifecycle task ID. Name and note are optional;
press Enter to use defaults, then confirm completion. The direct command and
review menu do not require a configured Codex model or launch a Codex process.

This action deliberately bypasses all task acceptance checks: status/transition
restrictions, dependencies and prerequisite hashes, required approvals/inputs,
report existence/format/hash, report assessment, test/profile results, process
exit code and the previous attempt's lifecycle fingerprint. Forward ordering
conflicts do not block this manual action. It can mark an already accepted task
again and retains the previous acceptance in its decision history.

Completion is stored as `VERIFIED` for compatibility with dependency scheduling,
with `mode: MANUAL_COMPLETION`, `human_assessment: COMPLETED`,
`checks_bypassed: true`, and `evidence_reviewed: false`. The human decision and
`TASK_COMPLETED_MANUALLY` event record the prior status and optional note. Status
output labels these completions explicitly. Original attempts/reports/results
are preserved; no attempts or passing test results are invented. A deferred or
manually blocked target is cleared, and its dependent tasks can proceed when
their other prerequisites and declared execution order allow it. Its own
unfinished prerequisites remain unfinished.

For an interrupted `RESERVED`/`IN_PROGRESS` target, manual completion clears its
current-task pointer while preserving the attempt metadata. It does not terminate
any running external Codex process. Normal file locking, valid state/history and
lifecycle loading, and atomic writes still protect persistence; malformed files,
a pending state transaction or a lifecycle/state mismatch must be repaired or
reconciled through the existing recovery workflow. These are storage-integrity
requirements, not acceptance checks. Option 1 and option 11 retain their existing
verification rules; option 12 is the unrestricted manual decision.

## Reports, retries and reopening

Real attempts produce:

```text
planning/task_reports/P0-T01/attempt-01.prompt.md
planning/task_reports/P0-T01/attempt-01.md
planning/task_reports/P0-T01/attempt-02.prompt.md
planning/task_reports/P0-T01/attempt-02.md
```

The generated prompt requests 14 exact Markdown headings and an `orchestrator-result` JSON block. See [the report example](examples/attempt-report.md). Each original criterion has a numbered result and evidence; each required profile has its ID, result and evidence. This format makes incomplete reporting detectable. Handwritten narrative-only reports remain incomplete, even if they claim success.

Retries allocate an attempt number when a launch is confirmed. Previous reports are never overwritten by Python. The new prompt includes prior report locations and parsed findings, plus saved additional instructions. Reopening an upstream task invalidates downstream acceptance. Even if the prerequisite is reaccepted, an existing downstream attempt cannot be accepted against a different prerequisite acceptance; retry it with current inputs.

```sh
python -m orchestrator.main reports P0-T01
python -m orchestrator.main review P0-T01
python -m orchestrator.main retry P0-T01
python -m orchestrator.main reopen P0-T01
```

The `review` command is how to accept/retry a task after restarting. `retry` and `reopen` require explicit confirmation and reason; they cannot bypass strict ordering. Deferred lifecycle tasks require explicit activation through reopen/retry with an approval reason.

Codex receives a detailed prompt as one literal argument without a shell. Prompts at or above 64 KiB use a short literal argument directing it to the saved full prompt file, avoiding operating-system argument-size limits. The interactive process inherits the terminal, so you can use normal Codex controls and approvals.

## State, history and crash recovery

`planning/execution_state.json` stores lifecycle/schema fingerprint, per-task definition hashes/status, attempt metadata, selected models, Git snapshots, reports, verification and human decisions. It does not duplicate the lifecycle's full task definitions. `planning/execution_history.jsonl` records ordered events and never automatically truncates previous decisions.

Writes use a pending transaction file, fsync, append-only event write, atomic state replacement and directory fsync. A crash between event and state writes can be recovered idempotently. A project-wide POSIX file lock prevents two orchestrators from executing concurrently; its descriptor is inherited by the interactive child so a parent crash does not immediately allow a competing task.

```sh
python -m orchestrator.main status
python -m orchestrator.main recover
```

`recover` asks before completing a pending state transaction and marking interrupted `RESERVED`/`IN_PROGRESS` attempts `PAUSED`. It never infers completion. Review existing evidence, then explicitly retry. Keyboard interruption attempts to interrupt and reap the Codex child, escalating to termination if necessary; a hard OS/process kill may require recovery. Wait for any surviving Codex session to exit first.

If a lifecycle or schema changes, execution stops. Restore the prior lifecycle or choose explicit reconciliation:

```sh
python -m orchestrator.main reconcile
```

Reconciliation requires a reason and confirmation. It conservatively invalidates **all** previous acceptances, preserves attempts/decisions and retains removed-task records. It does not silently transfer completion to changed definitions. Already attempted tasks become paused for explicit retry; new tasks follow their declared states. Back up the original lifecycle and state/history pair before adopting major plan changes.

To preserve unaffected progress, supply the exact predecessor lifecycle. Its fingerprint, computed with the current schema, must match saved state. If the schema changed, this mode refuses the migration; restore/review the original schema or use conservative reconciliation. Preview first:

```sh
python -m orchestrator.main validate --lifecycle-only --require-models
python -m orchestrator.main reconcile --previous-lifecycle planning/lifecycle_history/2026-11-15.before-consolidation.json --preview
python -m orchestrator.main reconcile --previous-lifecycle planning/lifecycle_history/2026-11-15.before-consolidation.json
```

The last command asks for confirmation and a reason. It preserves unchanged records only when task definitions, phase/milestone context, assigned-agent definitions, verification profiles, relevant human gates and global contracts remain compatible. Changed tasks and their dependents lose current acceptance; their attempts and decisions remain recorded. Removed task records are archived. Reordering alone does not change a task's evidence, but dependency edits do. Planning timestamps, scheduling commentary and effort estimates do not invalidate evidence. Active attempts must be recovered first.

For the November 15 consolidation, the preview preserves all 19 verified tasks through P1-T09 and keeps P1-T10 next. Removed constituent execution records are archived, with no completion inferred. Reconciliation permits reference substitutions only for validated consecutive same-agent merges with no prior attempts; global contract edits still invalidate evidence. If your saved fingerprint predates the archived predecessor, stop and identify the matching predecessor rather than resetting state.

`validate --lifecycle-only` validates the plan without loading or changing saved progress; ordinary `validate` also checks saved state. `reconcile --preview` reads state/history without committing a migration or launching Codex. It uses the normal execution lock to avoid racing an active session.

Malformed state, conflicting journals or a torn/truncated history line fail closed. The controller never silently resets progress or trims history. Preserve the damaged files, restore a matching backup pair, or perform an audited manual repair. The write-ahead journal is a recovery mechanism, not a substitute for backups.

Lifecycle, schema, state, history, configuration and prior report hashes are checked around each Codex session. Unexpected edits stop processing. This detects accidental changes; it is not an OS-level security boundary against a process running as the same user. Review unexpected changes before recovery.

## Commands and examples

```sh
python -m orchestrator.main init
python -m orchestrator.main status
python -m orchestrator.main validate
python -m orchestrator.main validate --require-models
python -m orchestrator.main --dry-run
python -m orchestrator.main
```

Dry run reads existing state or constructs an in-memory initial state, shows the first five unverified tasks in declared order and prints the next task's full prompt. It neither launches Codex nor writes state/prompts/application files. It does not simulate verification of dependencies to make later tasks look ready.

Examples: [generated prompt](examples/generated-prompt.md), [report format](examples/attempt-report.md), [actual initial terminal output](examples/terminal-output.txt). The examples are explicitly not live task completion evidence.

## Tests and limitations

```sh
python -m unittest discover -s orchestrator/tests -t . -v
```

Tests use temporary repositories/state and mocked Codex subprocesses. They cover schema/graph validation, actual lifecycle ordering, agent/model mappings, prompts, transactions, concurrency lock, acceptance gates, retry/reopen/skip/block semantics, recovery, dry run, CLI behavior and terminal inheritance. They never launch real Codex task sessions or run application tasks.

See [verification results](VERIFICATION.md) for executed checks. Live TUI rendering, account-specific model authorization and the truth of future task reports require your interactive use. Linux `fcntl`/directory fsync are intentional; Windows support is not implemented. The existing schema's unversioned `http://json-schema.org/schema#` alias is interpreted with the local Draft 2020-12 validator; its current basic keywords validate successfully. External schema references are rejected rather than fetched over the network.

Common problems:

- **No next eligible task:** inspect the first pending task and its blockers; strict order never jumps to a later task. A skip does not satisfy dependencies. Correct planning conflicts explicitly and preview reconciliation before adoption.
- **Unconfigured model:** run `setup-models`; confirm the pair in your account's `/model` picker.
- **Missing CLI/unsupported flags:** inspect `codex --help`; update through your approved installation workflow before retrying.
- **No real terminal:** run normal orchestration in a terminal; use `--dry-run` in redirected/automated environments.
- **Missing/incomplete report:** review final Codex output, then explicitly retry with instructions to provide real evidence. Python does not invent a successful report.
- **Exit code nonzero/interruption:** task remains failed/paused; a completed-looking report does not override the process failure.
- **Lock busy:** another orchestrator/Codex session is alive. Do not delete locks to bypass it; close the active session normally.
- **Lifecycle/state mismatch:** restore the original files or reconcile; never delete state just to silence validation.
