"""Plain terminal output. User-supplied report text cannot inject terminal escapes."""
import re
from .errors import OrchestratorError
from .prompt_generator import generate_prompt


def safe_text(text):
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "?", str(text))


def display(text=""):
    print(safe_text(text))


def ask(prompt):
    return input(safe_text(prompt)).strip()


def confirm(prompt):
    while True:
        value = ask(prompt + " [y/n] ").lower()
        if value in {"y", "yes", "n", "no", ""}:
            return value in {"y", "yes"}
        display("Enter y or n.")


def show_status(scheduler):
    progress = scheduler.get_execution_progress()
    display("=" * 56 + "\nDEVELOPMENT ORCHESTRATOR\n" + "=" * 56)
    for key in ("project", "phases", "milestones", "tasks", "remaining", "current_phase", "current_milestone"):
        display(f"{key.replace('_', ' ').title()}: {progress[key]}")
    display("States: " + ", ".join(f"{s}: {progress['counts'].get(s, 0)}" for s in
            ("VERIFIED", "FAILED", "BLOCKED", "READY", "NEEDS_REVIEW", "PARTIALLY_COMPLETED", "PAUSED", "SKIPPED")))
    next_task = scheduler.get_next_task()
    pending = scheduler.first_pending()
    display("Next eligible task: " + (next_task["id"] if next_task else "None"))
    if not next_task:
        if progress["complete"]:
            display("Lifecycle complete: all tasks VERIFIED.")
        elif pending:
            record = scheduler.tracker.state["tasks"][pending["id"]]
            display(f"Strict-order stop at {pending['id']} ({record['status']}): {record['blockers'] or 'Human review/retry required.'}")
        else:
            display("Not complete: skipped tasks remain unverified. Reopen them explicitly.")
    if scheduler.lifecycle.forward_dependencies:
        display(f"Ordering conflict: forward dependencies {scheduler.lifecycle.forward_dependencies}. Strict ordering will stop; lifecycle correction requires your approval.")


def show_task(task, lifecycle, selection, report_path):
    phase, milestone = lifecycle.context(task["id"])
    display(f"\nTASK {task['id']}: {task['title']}\nPhase: {phase['id']} / Milestone: {milestone['id']}")
    display(f"Agent: {task['assigned_agent']}\nModel: {selection['model']}\nReasoning effort: {selection['reasoning_effort']}")
    display(f"Dependencies: {', '.join(task['dependencies']) or 'None'}\nReport: {report_path}")


def dry_run(lifecycle, tracker, scheduler, models, reports, config):
    show_status(scheduler)
    display("\nNEXT FIVE UNVERIFIED TASKS IN DECLARED ORDER (no progress simulated)")
    candidates = [t for _, _, t in lifecycle.ordered if tracker.state["tasks"][t["id"]]["status"] != "VERIFIED"][:5]
    for task in candidates:
        try:
            model = models.select(task)
        except OrchestratorError:
            model = {"model": "UNCONFIGURED — run setup-models", "reasoning_effort": "UNCONFIGURED"}
        record = tracker.state["tasks"][task["id"]]
        display(f"{task['id']} | {task['assigned_agent']} | {model['model']} / {model['reasoning_effort']} | {record['status']} | dependencies={task['dependencies']}")
        if record["blockers"]:
            display("  Blockers: " + "; ".join(record["blockers"]))
    task = scheduler.get_next_task() or scheduler.first_pending()
    if task:
        try:
            model = models.select(task)
        except OrchestratorError:
            model = {"model": "UNCONFIGURED (launch prohibited)", "reasoning_effort": "UNCONFIGURED"}
        attempt = tracker.state["tasks"][task["id"]]["attempt_count"] + 1
        display("\nGENERATED PROMPT PREVIEW (no files written)\n")
        display(generate_prompt(lifecycle, task, model, tracker.state, reports.path(task["id"], attempt),
                                attempt, config["root"]))


def show_report(report, attempt):
    display(f"\nCodex exit code: {attempt['exit_code']}\nReport: {attempt['report_path']}\nAssessment: {report.get('assessment') or 'UNAVAILABLE'}")
    if report["errors"]:
        display("Report issues:\n" + "\n".join(report["errors"]))
    # All acceptance results, problems, remaining work and recommendations are included.
    display(report.get("text", "No report was created. Retry only after reviewing the failure."))
