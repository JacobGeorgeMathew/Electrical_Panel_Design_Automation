# Orchestrator verification

## Backend environment prompt update — 2026-11-12

Executed `orchestrator/.venv/bin/python -m unittest discover -s orchestrator/tests -t . -q`: **64 tests passed**. The two added regressions verify backend interpreter/cwd instructions, preservation of verification profiles and retry guidance when the test fixture has no backend environment.

An actual-lifecycle dry run passed and contained the new environment section. Hash checks confirmed no changes to the lifecycle, schema, execution state/history or live model mappings. No application task, backend test suite or real Codex session was launched. The prompt example and README were updated; model choices are documented recommendations only.

Verified on 2026-11-11. This record concerns the development orchestrator, not execution of PanelFlow's application-development lifecycle.

## Environment

- Linux; Python 3.14.8.
- Isolated test environment: `/tmp/panelflow-orchestrator-venv`.
- Direct dependency: `jsonschema==4.26.0`.
- Installed Codex CLI: `codex-cli 0.167.1`.
- Actual lifecycle: 9 phases, 32 milestones, 118 tasks, 11 agents.
- Source files: `planning/development_lifecycle.json`, `planning/schema.json`.

## Executed checks

Commands below used `/tmp/panelflow-orchestrator-venv/bin/python`; use your activated orchestrator environment for the equivalent `python` commands.

| Check | Actual result |
| --- | --- |
| `python -m unittest discover -s orchestrator/tests -t . -q` | 62 tests passed; no real Codex sessions launched. |
| `python -m compileall -q orchestrator` | Passed. |
| `python -m orchestrator.main validate` | Actual lifecycle/schema and initialized state valid. All 11 model mappings correctly reported unconfigured. |
| `python -m orchestrator.main --dry-run` | Exit 0; generated the actual first-task prompt; first five task IDs and agents matched declared order. No task launched. |
| `python -m orchestrator.main init` followed by `status` | State initialized and reloaded successfully: 0 attempts, 0 verified tasks, one initialization event. |
| `InteractiveDispatcher().preflight()` | Installed CLI exposes the required interactive prompt/model/configuration/approval/sandbox/root arguments. |
| `codex --version`, `codex --help`, `codex login --help` | Read-only CLI inspection completed. This did not authenticate or launch a task session. |
| Git comparison of lifecycle/schema/application/instruction files | No changes to lifecycle, schema, `backend`, `frontend`, root `AGENTS.md` or root `README.md`. |

Tests initially exposed a fixture-root path error, an incorrect exception import and a test terminal-mock issue; these were corrected before the passing run. Tests subsequently added checks for state integrity, explicit decisions, invalidated prerequisites, removed tasks and strict ordering.

## Actual first-five preview

| Task | Assigned agent | Initial state |
| --- | --- | --- |
| P0-T01 | architecture_lead | READY |
| P0-T02 | quality_engineer | BLOCKED: P0-T01 unverified |
| P0-T03 | quality_engineer | BLOCKED: P0-T02 unverified |
| P0-T04 | architecture_lead | BLOCKED: P0-T01 unverified |
| P0-T05 | cad_kernel_engineer | BLOCKED: P0-T03 unverified |

Configured model overrides are tested using clearly synthetic fixture IDs in temporary configurations. No synthetic ID appears as a production model default. Actual account-specific availability must be checked by the user through the Codex `/model` picker.

## Verified safeguards

- A zero process exit does not mark a task verified; explicit human acceptance and complete required evidence are necessary.
- Nonzero/interrupted execution, incomplete reports, missing evidence and missing human gates cannot be accepted.
- Retries retain earlier reports and increment attempt numbers at launch.
- Reopening invalidates downstream acceptance and detects attempts based on older prerequisite approvals.
- Skipped tasks never satisfy dependencies; deferred tasks require explicit human activation.
- Dry run does not write state/prompts or launch Codex.
- Mocked TUI dispatch uses `subprocess.Popen` without stdin/stdout/stderr pipes, `shell`, `codex exec` or App Server.
- Atomic state/history recovery is tested with failure injection between event append and state replacement.
- A second execution lock holder is rejected; malformed state/history is never silently reset.
- Actual forward dependencies are reported. The controller stops rather than reordering tasks.

## Unverified boundaries and setup required

- **Live TUI behavior and authentication/model access:** no real task session was launched, as requested. Terminal inheritance is established by subprocess tests, not a live application-development run.
- **Human evidence:** the controller checks report completeness and records human decisions. It cannot independently prove engineering correctness or the authenticity of a signed decision.
- **Application implementation:** no application tests, database migrations, engineering tasks or native CAD workloads were run.
- **Ordering conflict:** P2-T10 and P2-T11 depend on later P2-T12. The original lifecycle is unchanged; strict ordering will block until the owner explicitly corrects it and reconciles state.
- **State protection:** same-user Codex can technically edit repository files. Prompt restrictions and hash checks detect protected-file changes; they are not an OS security sandbox around progress files.
- **Linux scope:** POSIX locking and directory fsync are intentional. Other operating systems are not validated.

Start with `python -m orchestrator.main setup-models`, then `python -m orchestrator.main validate --require-models` and `python -m orchestrator.main --dry-run`. Launch normal orchestration only after reviewing the task and choosing your model mappings.
