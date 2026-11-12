"""Durable state and append-only events, with a recoverable write-ahead transaction."""
import copy
import json
import os
import uuid
from pathlib import Path

from .errors import OrchestratorError, LifecycleChanged
from .io_utils import atomic_json, read_json, digest, now, sync_dir, confined

STATUSES = {"BLOCKED", "READY", "RESERVED", "IN_PROGRESS", "NEEDS_REVIEW", "VERIFIED",
            "FAILED", "PARTIALLY_COMPLETED", "PAUSED", "SKIPPED"}
TRANSITIONS = {
    "BLOCKED": {"READY", "SKIPPED", "PAUSED"},
    "READY": {"RESERVED", "BLOCKED", "SKIPPED", "PAUSED"},
    "RESERVED": {"IN_PROGRESS", "FAILED", "PAUSED"},
    "IN_PROGRESS": {"NEEDS_REVIEW", "FAILED", "PARTIALLY_COMPLETED", "PAUSED"},
    "NEEDS_REVIEW": {"VERIFIED", "READY", "BLOCKED", "SKIPPED", "PAUSED"},
    "FAILED": {"READY", "BLOCKED", "SKIPPED", "PAUSED"},
    "PARTIALLY_COMPLETED": {"READY", "BLOCKED", "SKIPPED", "PAUSED"},
    "PAUSED": {"READY", "BLOCKED", "SKIPPED", "NEEDS_REVIEW"},
    "SKIPPED": {"READY", "BLOCKED"},
    "VERIFIED": {"READY", "BLOCKED"},
}


def task_record(task):
    return {"status": "BLOCKED" if task["dependencies"] or task["status"] == "deferred" else "READY",
            "definition_hash": digest(task), "assigned_agent": task["assigned_agent"],
            "attempt_count": 0, "attempts": [], "human_decisions": [], "acceptance": None,
            "manual_blocker": None, "deferred": task["status"] == "deferred",
            "failure_reasons": [], "blockers": list(task["dependencies"]), "pending_instructions": ""}


class ProgressTracker:
    def __init__(self, lifecycle, config):
        self.lifecycle, self.config = lifecycle, config
        self.path, self.history = Path(config["state_path"]), Path(config["history_path"])
        self.journal = self.path.with_suffix(".pending.json")
        self.state = None

    def initial_state(self):
        return {"format_version": 1, "project": self.lifecycle.data["project"],
                "lifecycle_file": str(self.lifecycle.path.relative_to(self.config["root"])),
                "lifecycle_fingerprint": self.lifecycle.fingerprint, "updated_at": now(),
                "current_task_id": None, "event_sequence": 0, "retired_tasks": {},
                "tasks": {tid: task_record(t) for tid, t in self.lifecycle.tasks.items()}}

    def events(self):
        if not self.history.exists():
            return []
        try:
            text = self.history.read_text(encoding="utf-8")
            if text and not text.endswith("\n"):
                raise ValueError("unterminated history line; preserve file and repair from backup")
            events = [json.loads(line) for line in text.splitlines()]
            for index, event in enumerate(events, 1):
                if event.get("sequence") != index or not event.get("event_id"):
                    raise ValueError("history sequence or event ID is invalid")
            return events
        except (OSError, ValueError, AttributeError) as exc:
            raise OrchestratorError(f"Malformed execution history: {exc}") from exc

    def load(self, allow_changed=False):
        if self.journal.exists():
            raise OrchestratorError("Interrupted state transaction found. Run recover before continuing.")
        events = self.events()
        if not self.path.exists() and events:
            raise OrchestratorError("State missing but history exists; restore state or recover, never reset history.")
        self.state = read_json(self.path) if self.path.exists() else self.initial_state()
        self.validate_state(self.state)
        if len(events) != self.state["event_sequence"]:
            raise OrchestratorError("State/history sequence mismatch; restore the matching pair or recover.")
        if self.state["lifecycle_fingerprint"] != self.lifecycle.fingerprint:
            if not allow_changed:
                raise LifecycleChanged("Lifecycle/schema changed. Run reconcile to review and explicitly invalidate prior acceptances, or restore the original lifecycle.")
        else:
            if set(self.state["tasks"]) != set(self.lifecycle.tasks):
                raise OrchestratorError("Execution state task IDs do not match the lifecycle.")
            for tid, task in self.lifecycle.tasks.items():
                if self.state["tasks"][tid]["definition_hash"] != digest(task):
                    raise OrchestratorError(f"State definition hash mismatch: {tid}")
        return self.state

    def validate_state(self, state):
        try:
            assert state["format_version"] == 1
            assert isinstance(state["project"], str) and state["project"]
            assert isinstance(state["updated_at"], str) and state["updated_at"]
            confined(self.config["root"], state["lifecycle_file"])
            assert isinstance(state["tasks"], dict) and isinstance(state["retired_tasks"], dict)
            assert isinstance(state["lifecycle_fingerprint"], str)
            assert type(state["event_sequence"]) is int and state["event_sequence"] >= 0
            assert state["current_task_id"] is None or state["current_task_id"] in state["tasks"]
            for tid, record in state["tasks"].items():
                assert record["status"] in STATUSES
                assert isinstance(record["definition_hash"], str)
                assert isinstance(record["assigned_agent"], str)
                assert type(record["attempt_count"]) is int
                assert isinstance(record["human_decisions"], list)
                assert isinstance(record["failure_reasons"], list)
                assert isinstance(record["blockers"], list)
                assert type(record["deferred"]) is bool
                assert "manual_blocker" in record and "acceptance" in record
                assert record["attempt_count"] == len(record["attempts"])
                for n, attempt in enumerate(record["attempts"], 1):
                    assert attempt["number"] == n
                    for key in ("report_path", "model", "reasoning_effort", "started_at", "ended_at", "exit_code", "git", "verification_results"):
                        assert key in attempt
                    path = confined(self.config["root"], attempt["report_path"])
                    expected = self.config["reports_dir"] / tid / f"attempt-{n:02d}.md"
                    assert path == expected.resolve()
                    assert isinstance(attempt["model"], str) and attempt["model"]
                    assert isinstance(attempt["reasoning_effort"], str)
                    assert attempt["exit_code"] is None or type(attempt["exit_code"]) is int
                    assert isinstance(attempt["verification_results"], dict)
                    assert isinstance(attempt["git"], dict)
                if record["status"] == "VERIFIED":
                    assert record["acceptance"] and record["acceptance"]["evidence_reviewed"]
                    assert record["acceptance"]["definition_hash"] == record["definition_hash"]
                    assert record["attempts"][-1]["exit_code"] == 0
                    assert record["acceptance"]["attempt"] == record["attempt_count"]
                    assert record["acceptance"]["reviewer"].strip() and record["acceptance"]["evidence"].strip()
                    assert record["acceptance"]["report_sha256"] == record["attempts"][-1]["report_sha256"]
            active = [tid for tid, r in state["tasks"].items() if r["status"] in {"RESERVED", "IN_PROGRESS"}]
            assert len(active) <= 1
            assert (active[0] if active else None) == state["current_task_id"]
        except (AssertionError, KeyError, TypeError, IndexError) as exc:
            raise OrchestratorError("Malformed execution state; restore a valid state/history pair. Progress was not reset.") from exc

    def _finish_transaction(self, transaction):
        events = self.events()
        event = transaction["event"]
        if len(events) == event["sequence"] - 1:
            self.history.parent.mkdir(parents=True, exist_ok=True)
            with self.history.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        elif len(events) != event["sequence"] or events[-1] != event:
            raise OrchestratorError("Pending transaction conflicts with history. Preserve files for manual recovery.")
        atomic_json(self.path, transaction["state"])
        self.journal.unlink()
        sync_dir(self.journal.parent)

    def recover_transaction(self):
        if self.journal.exists():
            transaction = read_json(self.journal)
            try:
                self.validate_state(transaction["state"])
                if transaction["state"]["event_sequence"] != transaction["event"]["sequence"]:
                    raise ValueError("sequence mismatch")
            except (KeyError, TypeError, ValueError) as exc:
                raise OrchestratorError("Malformed pending transaction; preserve it and restore from backup.") from exc
            self._finish_transaction(transaction)

    def commit(self, event_type, task_id=None, details=None):
        if self.journal.exists():
            raise OrchestratorError("Pending state transaction must be recovered before another event can be written.")
        self.state["updated_at"] = now()
        self.state["event_sequence"] += 1
        self.validate_state(self.state)
        event = {"event_id": str(uuid.uuid4()), "sequence": self.state["event_sequence"],
                 "timestamp": now(), "task_id": task_id, "event_type": event_type,
                 "attempt": self.state["tasks"][task_id]["attempt_count"] if task_id else None,
                 "details": details or {}}
        transaction = {"event": event, "state": self.state}
        atomic_json(self.journal, transaction)
        self._finish_transaction(transaction)

    def transition(self, tid, status):
        record = self.state["tasks"][tid]
        if status not in TRANSITIONS[record["status"]]:
            raise OrchestratorError(f"Invalid state transition: {record['status']} -> {status}")
        record["status"] = status

    def refresh(self):
        for tid, record in self.state["tasks"].items():
            deps = self.lifecycle.tasks[tid]["dependencies"]
            reasons = [f"Dependency {d}: {self.state['tasks'][d]['status']}" for d in deps
                       if self.state["tasks"][d]["status"] != "VERIFIED"]
            if record["manual_blocker"]:
                reasons.append(record["manual_blocker"])
            if record["deferred"]:
                reasons.append("Lifecycle task is deferred; explicit activation required.")
            record["blockers"] = reasons
            if record["status"] in {"READY", "BLOCKED"}:
                record["status"] = "BLOCKED" if reasons else "READY"

    def reserve(self, tid, selection, report_path, git, instructions=""):
        self.refresh()
        if any(r["status"] in {"IN_PROGRESS", "RESERVED"} for r in self.state["tasks"].values()):
            raise OrchestratorError("An attempt is already active; use explicit recovery.")
        self.transition(tid, "RESERVED")
        record = self.state["tasks"][tid]
        record["attempt_count"] += 1
        record["pending_instructions"] = ""
        record["attempts"].append({"number": record["attempt_count"], "report_path": str(report_path),
            "assigned_agent": self.lifecycle.tasks[tid]["assigned_agent"],
            "lifecycle_fingerprint": self.lifecycle.fingerprint,
            **selection, "started_at": None, "ended_at": None, "exit_code": None,
            "git": git, "verification_results": {}, "additional_instructions": instructions,
            "dependency_acceptances": {d: digest(self.state["tasks"][d]["acceptance"])
                                       for d in self.lifecycle.tasks[tid]["dependencies"]},
            "failure_reason": None})
        self.state["current_task_id"] = tid
        self.commit("TASK_SELECTED", tid)

    def start(self, tid):
        self.transition(tid, "IN_PROGRESS")
        self.state["tasks"][tid]["attempts"][-1]["started_at"] = now()
        self.commit("TASK_STARTED", tid)

    def finish(self, tid, result, report, git):
        record = self.state["tasks"][tid]
        attempt = record["attempts"][-1]
        attempt.update(ended_at=now(), exit_code=result.exit_code, git_after=git,
                       failure_reason=result.error, verification_results=report.get("result", {}),
                       report_sha256=report.get("sha256"), report_errors=report["errors"])
        status = "NEEDS_REVIEW"
        if result.interrupted:
            status = "PAUSED"
        elif result.exit_code != 0 or report.get("assessment") == "FAILED":
            status = "FAILED"
        elif report["errors"] or report.get("assessment") != "COMPLETED":
            status = "PARTIALLY_COMPLETED"
        self.transition(tid, status)
        if result.error or report["errors"]:
            record["failure_reasons"].append({"timestamp": now(), "attempt": attempt["number"],
                                             "reason": result.error or "; ".join(report["errors"])})
        self.state["current_task_id"] = None
        self.commit("CODEX_EXITED", tid, {"exit_code": result.exit_code, "status": status})
        if report.get("sha256"):
            self.commit("REPORT_CREATED", tid, {"path": attempt["report_path"], "sha256": report["sha256"]})
        if status == "FAILED":
            self.commit("TASK_FAILED", tid)

    def invalidate_dependents(self, tid):
        affected = {tid}
        while True:
            extra = {key for key, task in self.lifecycle.tasks.items() if set(task["dependencies"]) & affected}
            if extra <= affected:
                break
            affected |= extra
        for key in affected - {tid}:
            record = self.state["tasks"][key]
            if record["status"] == "VERIFIED":
                record["human_decisions"].append({"timestamp": now(), "action": "ACCEPTANCE_INVALIDATED",
                    "reason": f"Prerequisite {tid} reopened", "previous_acceptance": record["acceptance"]})
                record["acceptance"] = None
                record["status"] = "BLOCKED"
        return sorted(affected - {tid})

    def reconcile(self, reason):
        if not reason.strip():
            raise OrchestratorError("Reconciliation requires a human reason.")
        old = self.state
        fresh = self.initial_state()
        fresh["event_sequence"] = old["event_sequence"]
        fresh["retired_tasks"] = copy.deepcopy(old["retired_tasks"])
        for tid, previous in old["tasks"].items():
            if tid not in fresh["tasks"]:
                fresh["retired_tasks"].setdefault(tid, []).append(previous)
                continue
            record = fresh["tasks"][tid]
            for key in ("attempt_count", "attempts", "human_decisions", "failure_reasons"):
                record[key] = copy.deepcopy(previous[key])
            record["human_decisions"].append({"timestamp": now(), "action": "LIFECYCLE_RECONCILED",
                "reason": reason, "previous_status": previous["status"], "previous_acceptance": previous["acceptance"],
                "old_definition_hash": previous["definition_hash"]})
            if record["attempt_count"]:
                record["status"] = "PAUSED"
        self.state = fresh
        self.commit("LIFECYCLE_RECONCILED", details={"reason": reason,
            "old_fingerprint": old["lifecycle_fingerprint"], "new_fingerprint": fresh["lifecycle_fingerprint"]})
