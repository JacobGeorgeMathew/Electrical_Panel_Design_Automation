import json
from .agent_registry import AgentRegistry
from .report_manager import ReportManager, HEADINGS


def generate_prompt(lifecycle, task, selection, state, report_path, attempt, root, instructions=""):
    phase, milestone = lifecycle.context(task["id"])
    agent = AgentRegistry(lifecycle).get(task["assigned_agent"])
    prior = state["tasks"][task["id"]]["attempts"]
    lines = [f"# Specialist identity: {agent['id']}", agent["specialization"],
             agent.get("authority", "Follow the lifecycle-defined responsibilities; human approval is never delegated."),
             "\n# Project context", f"Project: {lifecycle.data['project']}",
             "PanelFlow is a prototype DB modular monolith: FastAPI/Python, PostgreSQL, React/TypeScript/Zustand, Three.js and Tauri.",
             "CEM owns electrical intent; PDM owns physical arrangement. Preserve stable identities, immutable revisions and strict physical constraints.",
             f"Read-only lifecycle: {lifecycle.path.relative_to(root)}", f"Lifecycle objective: {lifecycle.data.get('scope', {})}",
             "Read root AGENTS.md and all applicable nested AGENTS.md/AGENTS.override.md before edits. Read relevant architecture documentation and verify against source."]
    # Include root rules, not arbitrary source files or secret configuration.
    rules = root / "AGENTS.md"
    if rules.exists():
        lines += ["\n## Repository instructions (root AGENTS.md)", rules.read_text(encoding="utf-8")]
    lines += ["\n# Task", f"ID: {task['id']}", f"Title: {task['title']}", f"Type: {task['type']}",
              f"Agent: {task['assigned_agent']}", f"Model: {selection['model']}",
              f"Reasoning effort: {selection['reasoning_effort']}",
              f"Phase: {phase['id']} — {phase['title']}", f"Milestone: {milestone['id']} — {milestone['title']}"]
    if task.get("description"):
        lines.append(task["description"])
    for key, heading in (("implementation_steps", "Implementation requirements"), ("planned_outputs", "Expected outputs"),
                         ("input_files", "Input files"), ("acceptance_criteria", "Acceptance criteria")):
        lines += [f"\n# {heading}"] + [f"{i}. {value}" for i, value in enumerate(task[key], 1)]
    lines += ["\n# Verification profiles", json.dumps({p: lifecycle.data["verification_profiles"][p]
              for p in task["verification_profiles"]}, indent=2),
              "\n# Python environments and command execution",
              "The orchestrator has its own Python environment. Codex may inherit that environment; do not assume bare python, pip, pytest, uvicorn or alembic selects the backend environment.",
              "For backend Python commands, use backend/.venv/bin/python relative to the repository root. When the working directory is backend/, use .venv/bin/python.",
              "Run backend application modules and tests with backend/ as the working directory so app imports resolve correctly. Invoke tools through the backend interpreter with -m, including pytest, pip, uvicorn and alembic.",
              "Interpret a backend verification profile's python -m pytest command as .venv/bin/python -m pytest from backend/. Preserve its arguments, environment flags, fixture isolation and permission requirements; do not change the lifecycle file.",
              "Example from repository root, only when the task authorizes backend tests: (cd backend && .venv/bin/python -m pytest). This is interpreter-selection guidance, not a request to run the full suite for every task.",
              "Before required backend execution, verify that backend/.venv/bin/python exists and inspect sys.executable and sys.prefix using that interpreter. If it is missing, broken or lacks required packages, report the environment blocker; do not silently fall back to the orchestrator or system Python.",
              "Do not install backend dependencies into the orchestrator environment, or orchestrator dependencies into the backend environment. When dependency installation is authorized, use the target environment's python -m pip and the appropriate requirements file; do not recreate or alter environments merely to bypass a failed check.",
              "Use the orchestrator's own Python environment for orchestrator-only checks, and the existing npm commands from frontend/ for frontend checks. Activating an environment in another terminal does not switch this session's interpreter.",
              "Record the actual working directory, interpreter command, exit status and any unrun verification in the attempt report. Never claim unavailable environment checks passed.",
              "\n# Prerequisites"]
    for dep in task["dependencies"]:
        record = state["tasks"][dep]
        lines.append(f"{dep}: {record['status']}; acceptance: {json.dumps(record['acceptance'])}")
        lines.extend(f"  report: {a['report_path']}" for a in record["attempts"])
    lines += ["\n# Human authority and scope", f"Human input: {task.get('human_input', 'None specified')}",
              f"Approver: {task.get('approver', 'Human task acceptance required')}",
              f"Decision ID: {task.get('decision_id', 'None')}",
              f"Permitted modification scope: {task.get('permitted_modification_scope', 'Only files necessary for this task and its tests/documentation; preserve unrelated changes.')}",
              "For human_gate tasks, prepare evidence and recommendations only; do not fabricate approval or sign on behalf of a person.",
              "\n# Execution instructions",
              "Inspect implementation before editing. Reuse existing architecture and repository conventions. Avoid unrelated refactoring.",
              "Run required verification only where authorized; report commands, failures, skips and unverified behavior honestly.",
              "Preserve unrelated user edits. Do not automatically commit, push, merge, reset, deploy or create worktrees.",
              "Do not change the lifecycle, schema, orchestrator configuration, execution state, journal or history. Python owns progress and human decisions.",
              "Complete only this task. Do not execute subsequent lifecycle tasks. Preserve all prior attempt reports."]
    if prior:
        lines += ["\n# Prior attempts (read before retrying)"]
        for item in prior:
            lines.append(f"Attempt {item['number']}: {item['report_path']}; exit={item['exit_code']}; findings={json.dumps(item.get('verification_results', {}))}")
    if instructions:
        lines += ["\n# Additional human instructions", instructions,
                  "These do not replace the original acceptance criteria or grant missing engineering approvals."]
    lines += ["\n# Mandatory execution report", f"Write the report to: {report_path}",
              f"Attempt: {attempt}. Create a NEW Markdown file; never overwrite an earlier report.",
              "Write a report for COMPLETED, PARTIALLY_COMPLETED or FAILED attempts. If writing is impossible, explain why in your final response.",
              "Use every exact level-two heading below; use 'None' with an explanation where appropriate."]
    lines.extend(f"## {heading}" for heading in HEADINGS)
    lines += ["Separate implementation claims from actual verification evidence. Include command exit codes and evidence references.",
              "Include exactly one machine-readable block as below, replacing results/evidence truthfully. Use PASS only with evidence; never silently waive required profiles.",
              "```orchestrator-result", json.dumps(ReportManager.result_template(task, attempt), indent=2), "```",
              "Your report is evidence for human review, never automatic task acceptance."]
    return "\n".join(lines) + "\n"
