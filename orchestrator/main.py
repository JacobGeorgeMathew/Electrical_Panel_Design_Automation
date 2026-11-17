"""Run with python -m orchestrator.main. No task runs without confirmation."""
import argparse
import hashlib
from pathlib import Path
import sys

from .configuration import load_config, DEFAULT_CONFIG
from .lifecycle_loader import load_lifecycle
from .progress_tracker import ProgressTracker
from .task_scheduler import TaskScheduler
from .model_selector import ModelSelector
from .report_manager import ReportManager
from .decision_manager import DecisionManager
from .prompt_generator import generate_prompt
from .codex.interactive_dispatcher import InteractiveDispatcher
from .git_safety import git_snapshot
from .io_utils import execution_lock, now
from .errors import OrchestratorError, LifecycleChanged
from . import terminal_ui as ui


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--dry-run", action="store_true")
    sub = p.add_subparsers(dest="command")
    for name in ("status", "init", "recover", "setup-models"):
        sub.add_parser(name)
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--previous-lifecycle", type=Path, help="Original lifecycle matching the saved fingerprint; preserve unaffected progress")
    reconcile.add_argument("--preview", action="store_true", help="Show reconciliation impact without writing execution state or history")
    validate = sub.add_parser("validate")
    validate.add_argument("--require-models", action="store_true")
    validate.add_argument("--lifecycle-only", action="store_true", help="Validate a revised plan before migrating saved progress")
    for name in ("reports", "retry", "reopen", "review", "complete"):
        command = sub.add_parser(name)
        command.add_argument("task_id")
    model = sub.add_parser("set-model")
    model.add_argument("target", help="Lifecycle agent ID or task ID with --task")
    model.add_argument("model")
    model.add_argument("effort")
    model.add_argument("--task", action="store_true")
    return p


def report_for(task, tracker, reports):
    record = tracker.state["tasks"][task["id"]]
    if not record["attempts"]:
        raise OrchestratorError("Task has no execution attempts.")
    attempt = record["attempts"][-1]
    report = reports.inspect(tracker.config["root"] / attempt["report_path"], task, attempt["number"])
    return attempt, report


def decision_menu(task, tracker, reports, decisions):
    """Return retry instructions only after explicit human action; never launch here."""
    tid = task["id"]
    while True:
        ui.display("\n1 ACCEPT TASK  2 REVIEW REPORT  3 RETRY  4 RETRY WITH INSTRUCTIONS\n5 REOPEN  6 SKIP  7 MARK BLOCKED  8 PAUSE / EXIT\n9 RECORD HUMAN GATE APPROVAL  10 CONFIRM HUMAN INPUT\n11 MARK PARTIAL TASK COMPLETED (HUMAN OVERRIDE)\n12 MARK ANY TASK COMPLETED (BYPASS ALL ACCEPTANCE CHECKS)")
        action = ui.ask("Action: ")
        try:
            if action == "1":
                if ui.confirm("Have you independently reviewed all criterion/profile evidence and required approvals?"):
                    decisions.accept(tid, ui.ask("Reviewer name: "), ui.ask("Evidence reviewed (references and results): "))
                    return None
            elif action == "2":
                attempt, report = report_for(task, tracker, reports)
                ui.show_report(report, attempt)
            elif action in {"3", "4", "5"}:
                reason = ui.ask("Reason: ")
                extra = ui.ask("Additional instructions (original requirements remain binding): ") if action == "4" else ""
                if ui.confirm("Record this retry/reopen request?"):
                    decisions.retry(tid, reason, reopen=action == "5", instructions=extra)
                    return extra
            elif action in {"6", "7"}:
                if action == "6":
                    dependents = [key for key, item in tracker.lifecycle.tasks.items() if tid in item["dependencies"]]
                    ui.display(f"Skipping {tid} will not complete it. Direct dependent tasks remain blocked: {dependents}")
                reason = ui.ask("Reason: ")
                if ui.confirm("Record this decision? Skips never satisfy dependencies."):
                    decisions.mark(tid, "SKIPPED" if action == "6" else "BLOCKED", reason)
                    return None
            elif action == "8":
                # Leave NEEDS_REVIEW intact, allowing acceptance on restart without rerunning.
                tracker.commit("ORCHESTRATOR_PAUSED", tid, {"reason": "Human chose pause/exit"})
                return None
            elif action == "9":
                approver = ui.ask(f"Named approver acting with authority of {task.get('approver', 'not a human gate')}: ")
                evidence = ui.ask("Approval decision and evidence reference: ")
                if ui.confirm("Record this explicit human approval?"):
                    decisions.gate(tid, approver, evidence)
            elif action == "10":
                decisions.human_input(tid, ui.ask("Human input supplied / evidence: "))
            elif action == "11":
                review = decisions.partial_acceptance_review(tid)
                ui.display(f"Human completion override for {tid}, attempt {review['attempt']}. Original report: {review['report_path']}")
                ui.display("This accepts the task and unlocks dependencies. The original PARTIALLY_COMPLETED assessment and test results remain recorded.")
                for item in review["exceptions"]:
                    ui.display(f"{item['kind']} {item['id']}: {item['result']} — {item['description']}\nEvidence: {item['evidence']}")
                if not review["exceptions"]:
                    ui.display("All structured results say PASS; review Remaining work and Problems encountered for the reason Codex reported partial completion.")
                _, report = report_for(task, tracker, reports)
                ui.show_report(report, tracker.state["tasks"][tid]["attempts"][-1])
                reviewer = ui.ask("Developer accepting responsibility (name): ")
                evidence = ui.ask("Evidence reviewed (references and results): ")
                rationale = ui.ask("Why accept completion? Address remaining work, accepted exceptions and follow-up: ")
                if ui.confirm("I have reviewed this attempt and accept responsibility for marking it COMPLETED, including the listed exceptions and downstream consequences. Confirm?"):
                    decisions.accept_partial(tid, reviewer, evidence, rationale, responsibility_acknowledged=True)
                    ui.display(f"{tid}: COMPLETED by human override (saved as VERIFIED for dependency scheduling).")
                    return None
            elif action == "12":
                target = ui.ask(f"Task ID (blank selects {tid}): ") or tid
                target_task = tracker.lifecycle.tasks.get(target)
                if target_task is None:
                    raise OrchestratorError(f"Unknown task: {target}")
                manual_completion(target_task, tracker, decisions)
                return None
            else:
                ui.display("Choose a number from the menu.")
        except OrchestratorError as exc:
            ui.display(f"Cannot apply decision: {exc}")


def manual_completion(task, tracker, decisions):
    tid = task["id"]
    ui.display(f"Mark {tid} COMPLETED from {tracker.state['tasks'][tid]['status']}. Acceptance checks, reports, dependencies and approval gates will be bypassed.")
    reviewer = ui.ask("Developer name (optional): ")
    reason = ui.ask("Note (optional): ")
    if ui.confirm(f"Mark {tid} COMPLETED now?"):
        decisions.complete_manually(tid, reviewer, reason)
        ui.display(f"{tid}: COMPLETED manually (saved as VERIFIED for dependency scheduling).")


def protected_hashes(paths):
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None for p in paths}


def launch(task, tracker, scheduler, models, reports, decisions, config, lock_fd, instructions=""):
    current = load_lifecycle(config["lifecycle_path"], config["schema_path"])
    if current.fingerprint != tracker.lifecycle.fingerprint:
        raise LifecycleChanged("Lifecycle/schema changed before launch. Reconcile or restore it first.")
    if scheduler.get_next_task() != task:
        raise OrchestratorError("Strict order or dependencies prevent this task from launching.")
    selection = models.select(task)
    dispatcher = InteractiveDispatcher()
    dispatcher.preflight()
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise OrchestratorError("A real terminal is required. Use --dry-run for unattended inspection.")
    tid = task["id"]
    instructions = instructions or tracker.state["tasks"][tid].get("pending_instructions", "")
    number = tracker.state["tasks"][tid]["attempt_count"] + 1
    path = reports.path(tid, number)
    ui.show_task(task, tracker.lifecycle, selection, path)
    git = git_snapshot(config["root"])
    ui.display(f"Git repository: {git['is_repository']} | Branch: {git['branch'] or '(detached/unavailable)'} | Commit: {git['commit']}")
    if git["uncommitted"]:
        ui.display("Uncommitted changes to preserve:\n" + git["uncommitted"])
    if not git["is_repository"]:
        ui.display("WARNING: Git safety metadata is unavailable; no Git operations will be performed.")
    if task.get("human_input"):
        ui.display("Required human input: " + task["human_input"])
        if not ui.confirm("Has this input been supplied for this attempt?"):
            return None
        decisions.human_input(tid, ui.ask("Input/evidence note (no secrets): "))
    if not ui.confirm("Start this task in the interactive Codex TUI?"):
        return None
    prompt = generate_prompt(tracker.lifecycle, task, selection, tracker.state, path, number, config["root"], instructions)
    reports.prepare(tid, number)
    prompt_path = path.with_suffix(".prompt.md")
    # Exclusive creation prevents overwriting any prior prompt or report.
    with prompt_path.open("x", encoding="utf-8") as stream:
        stream.write(prompt)
    tracker.reserve(tid, selection, path.relative_to(config["root"]), git, instructions)
    tracker.start(tid)
    protected = [tracker.path, tracker.history, tracker.lifecycle.path, tracker.lifecycle.schema_path,
                 config["model_config_path"], config["config_path"]]
    protected.extend(config["root"] / attempt["report_path"] for record in tracker.state["tasks"].values()
                     for attempt in record["attempts"] if attempt["report_path"] != str(path.relative_to(config["root"])))
    before = protected_hashes(protected)
    argument = prompt if len(prompt.encode()) < 64000 else (
        f"Execute ONLY {tid}. Read the complete mandatory task prompt at {prompt_path}. "
        f"Write its required attempt report at {path}. Do not modify lifecycle or orchestration state.")
    result = dispatcher.run(argument, selection, config["root"], lock_fd)
    if protected_hashes(protected) != before:
        raise OrchestratorError("Protected lifecycle/config/progress files changed during Codex. No result accepted. Preserve files, inspect changes and recover explicitly.")
    report = reports.inspect(path, task, number)
    tracker.finish(tid, result, report, git_snapshot(config["root"]))
    attempt = tracker.state["tasks"][tid]["attempts"][-1]
    ui.show_report(report, attempt)
    retry = decision_menu(task, tracker, reports, decisions)
    stop = ((config["stop_after_failed_task"] and (result.exit_code != 0 or result.interrupted or report.get("assessment") == "FAILED")) or
            (config["stop_after_incomplete_report"] and bool(report["errors"])))
    if stop and retry is not None:
        ui.display("Retry decision saved. Stop policy requires a new orchestrator invocation.")
        return None
    return retry


def run(args):
    config = load_config(args.config)
    lifecycle = load_lifecycle(config["lifecycle_path"], config["schema_path"])
    tracker = ProgressTracker(lifecycle, config)
    reports = ReportManager(config["root"], config["reports_dir"])
    scheduler = TaskScheduler(lifecycle, tracker)
    decisions = DecisionManager(tracker, reports)
    command = args.command
    if lifecycle.forward_dependencies and command not in {"validate", "status", "reports", "reconcile", "recover", "complete", "review"} and not args.dry_run:
        raise OrchestratorError(f"Strict-order plan cannot execute forward dependencies: {lifecycle.forward_dependencies}. Correct the plan and reconcile before launching tasks.")
    readonly = args.dry_run or command in {"status", "validate", "reports"}
    if readonly:
        if command == "validate" and args.lifecycle_only:
            tracker.state = tracker.initial_state()
        else:
            tracker.load()
        models = ModelSelector(config["model_config_path"], lifecycle)
        if args.dry_run:
            ui.dry_run(lifecycle, tracker, scheduler, models, reports, config)
        elif command == "validate":
            ui.display(f"Valid lifecycle/schema{' (saved state not checked)' if args.lifecycle_only else ' and execution state'}: {len(lifecycle.tasks)} tasks.")
            missing = []
            for task in lifecycle.tasks.values():
                try:
                    models.select(task)
                except OrchestratorError:
                    missing.append(task["assigned_agent"])
            ui.display(f"Unconfigured agent mappings: {sorted(set(missing))}")
            ui.display(f"Forward dependencies requiring correction under strict ordering: {lifecycle.forward_dependencies}")
            if lifecycle.forward_dependencies:
                raise OrchestratorError("Strict-order plan has forward dependencies; correct declared task order before execution.")
            if args.require_models and missing:
                raise OrchestratorError("Model configuration is incomplete; run setup-models.")
        elif command == "reports":
            task = scheduler.get_task_by_id(args.task_id)
            for attempt in tracker.state["tasks"][task["id"]]["attempts"]:
                ui.show_report(reports.inspect(config["root"] / attempt["report_path"], task, attempt["number"]), attempt)
            if not tracker.state["tasks"][task["id"]]["attempts"]:
                ui.display("No attempts recorded.")
        else:
            ui.show_status(scheduler)
        return 0
    with execution_lock(config["root"] / "orchestrator/.execution.lock") as lock_fd:
        if command == "recover":
            if not ui.confirm("Recover a pending state transaction and mark interrupted attempts PAUSED?"):
                return 0
            tracker.recover_transaction()
        tracker.load(allow_changed=command == "reconcile")
        if command == "reconcile":
            previous = None
            if args.previous_lifecycle:
                from .lifecycle_reconciliation import reconciliation_plan
                path = args.previous_lifecycle
                previous = load_lifecycle(path if path.is_absolute() else config["root"] / path, config["schema_path"])
                plan = reconciliation_plan(previous, lifecycle, tracker.state)
                ui.display(f"Preserve VERIFIED tasks: {plan['preserved_verified']}")
                ui.display(f"Changed definitions/context: {plan['changed']}")
                ui.display(f"Added: {plan['added']} | Removed: {plan['removed']}")
                ui.display(f"Invalidate changed/downstream records: {len(plan['invalidated'])}; preserve {len(plan['preserved'])} unaffected records. Attempts and decisions remain in history.")
            else:
                ui.display("Conservative reconciliation invalidates all prior acceptances; attempts and decisions remain in history. Supply --previous-lifecycle to preserve unaffected progress.")
            if args.preview:
                ui.display("Preview only: execution state/history unchanged; no tasks launched.")
                return 0
            if ui.confirm("Adopt this lifecycle reconciliation?"):
                tracker.reconcile(ui.ask("Reason for adopting the lifecycle change: "), previous=previous)
            return 0
        if not tracker.path.exists():
            tracker.refresh()
            tracker.commit("STATE_INITIALIZED")
        if command == "init":
            ui.display("Execution state initialized/loaded. No tasks executed.")
            return 0
        if command == "recover":
            for tid, record in tracker.state["tasks"].items():
                if record["status"] in {"RESERVED", "IN_PROGRESS"}:
                    tracker.transition(tid, "PAUSED")
                    record["attempts"][-1].update(ended_at=now(), failure_reason="Interrupted session recovered; no completion inferred.")
            tracker.state["current_task_id"] = None
            tracker.commit("INTERRUPTION_RECOVERED")
            return 0
        if command == "complete":
            manual_completion(scheduler.get_task_by_id(args.task_id), tracker, decisions)
            return 0
        models = None if command == "review" else ModelSelector(config["model_config_path"], lifecycle)
        if command in {"setup-models", "set-model"}:
            ui.display("In a separate Codex TUI, use /model then /status to inspect available models and supported efforts. Names/access cannot be validated offline.")
            if command == "set-model":
                if ui.confirm("Have you confirmed this exact model/effort pair in your Codex CLI?"):
                    models.configure(args.target, args.model, args.effort, args.task)
            else:
                for agent in lifecycle.data["agents"]:
                    ui.display(f"\n{agent['id']}: {agent['specialization']}")
                    model = ui.ask("Model identifier (blank leaves current mapping unchanged): ")
                    if model:
                        effort = ui.ask("Supported reasoning effort: ")
                        if ui.confirm("Confirmed this exact pair in Codex /model?"):
                            models.configure(agent["id"], model, effort)
            return 0
        if config["show_dry_run_on_startup"] and command is None:
            ui.dry_run(lifecycle, tracker, scheduler, models, reports, config)
        else:
            ui.show_status(scheduler)
        if command in {"retry", "reopen", "review"}:
            task = scheduler.get_task_by_id(args.task_id)
            if command == "review":
                if tracker.state["tasks"][task["id"]]["attempts"]:
                    attempt, report = report_for(task, tracker, reports)
                    ui.show_report(report, attempt)
                else:
                    ui.display("No execution attempts. Manual completion is available as option 12.")
                extra = decision_menu(task, tracker, reports, decisions)
                if extra is None:
                    return 0
            else:
                reason = ui.ask("Reason: ")
                if not ui.confirm(f"Record {command} for {task['id']}?"):
                    return 0
                extra = ui.ask("Additional instructions (optional): ")
                decisions.retry(task["id"], reason, reopen=command == "reopen", instructions=extra)
        else:
            task = scheduler.get_next_task()
            extra = ""
            if task is None:
                pending = scheduler.first_pending()
                if pending:
                    extra = decision_menu(pending, tracker, reports, decisions)
                    task = pending
                if extra is None or task is None:
                    return 0
        # Only an explicit RETRY menu action permits another attempt, always with a new launch confirmation.
        if models is None:
            models = ModelSelector(config["model_config_path"], lifecycle)
        while True:
            extra = launch(task, tracker, scheduler, models, reports, decisions, config, lock_fd, extra)
            if extra is None:
                return 0


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return run(args)
    except LifecycleChanged as exc:
        ui.display(f"STOP: {exc}")
        if sys.stdin.isatty():
            ui.display("Current progress is unchanged. Preview reconciliation with the original lifecycle before adopting changes; see orchestrator/README.md.")
        return 2
    except (OrchestratorError, OSError, ValueError) as exc:
        ui.display(f"ERROR: {exc}")
        return 2
    except (KeyboardInterrupt, EOFError):
        ui.display("Paused. Saved events are preserved. Use status/review, or recover if an attempt was interrupted.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
