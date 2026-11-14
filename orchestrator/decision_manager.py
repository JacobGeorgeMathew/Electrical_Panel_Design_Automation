from .errors import OrchestratorError
from .io_utils import now, digest


class DecisionManager:
    def __init__(self, tracker, reports):
        self.tracker, self.reports = tracker, reports

    def record(self, tid, action, reason, **extra):
        if not reason.strip():
            raise OrchestratorError("A nonempty human reason/evidence note is required.")
        self.tracker.state["tasks"][tid]["human_decisions"].append(
            {"timestamp": now(), "action": action, "reason": reason, **extra})

    def gate(self, tid, approver, evidence):
        task = self.tracker.lifecycle.tasks[tid]
        if task["type"] != "human_gate" or not approver.strip():
            raise OrchestratorError("A gate decision needs a human_gate task and a named approver.")
        self.record(tid, "GATE_APPROVED", evidence, approver=approver,
                    decision_id=task.get("decision_id"), definition_hash=digest(task),
                    attempt=self.tracker.state["tasks"][tid]["attempt_count"])
        self.tracker.commit("HUMAN_DECISION_RECORDED", tid, {"action": "GATE_APPROVED", "approver": approver})

    def human_input(self, tid, evidence):
        self.record(tid, "INPUT_CONFIRMED", evidence, definition_hash=digest(self.tracker.lifecycle.tasks[tid]))
        self.tracker.commit("HUMAN_DECISION_RECORDED", tid, {"action": "INPUT_CONFIRMED"})

    def accept(self, tid, reviewer, evidence):
        task = self.tracker.lifecycle.tasks[tid]
        record = self.tracker.state["tasks"][tid]
        if record["status"] != "NEEDS_REVIEW":
            raise OrchestratorError(f"Cannot accept {tid}: saved status is {record['status']}, not NEEDS_REVIEW. Review the report and resolve failed/incomplete work or revise its scope explicitly before retrying. Typing a status into the evidence note does not change it.")
        if not reviewer.strip() or not evidence.strip():
            raise OrchestratorError("Acceptance requires a named reviewer and a nonempty evidence note.")
        if any(self.tracker.state["tasks"][d]["status"] != "VERIFIED" for d in task["dependencies"]):
            raise OrchestratorError("All prerequisites must still be VERIFIED.")
        attempt = record["attempts"][-1]
        expected = {d: digest(self.tracker.state["tasks"][d]["acceptance"]) for d in task["dependencies"]}
        if attempt.get("dependency_acceptances", {}) != expected:
            raise OrchestratorError("Prerequisite acceptance changed since this attempt. Retry with current prerequisites.")
        report = self.reports.inspect(self.tracker.config["root"] / attempt["report_path"], task, attempt["number"])
        if attempt["exit_code"] != 0 or report["errors"] or report["assessment"] != "COMPLETED":
            raise OrchestratorError("Cannot accept: successful exit and a complete valid COMPLETED report are required.")
        if report["sha256"] != attempt.get("report_sha256"):
            raise OrchestratorError("Report changed after execution. Preserve it and retry; existing evidence cannot be silently replaced.")
        if any(x["result"] != "PASS" for x in report["result"]["acceptance_criteria"] + report["result"]["verification_profiles"]):
            raise OrchestratorError("Every required criterion/profile must have PASS evidence, reviewed by a human.")
        valid_decisions = [d for d in record["human_decisions"] if d.get("definition_hash") == digest(task)]
        if task["type"] == "human_gate" and not any(d["action"] == "GATE_APPROVED" and d.get("attempt") == attempt["number"] for d in valid_decisions):
            raise OrchestratorError("Required named human gate approval has not been recorded.")
        if task.get("human_input") and not any(d["action"] == "INPUT_CONFIRMED" for d in valid_decisions):
            raise OrchestratorError("Required human input has not been confirmed.")
        record["acceptance"] = {"timestamp": now(), "reviewer": reviewer, "evidence": evidence,
            "evidence_reviewed": True, "definition_hash": digest(task), "attempt": attempt["number"],
            "report_sha256": report["sha256"]}
        self.record(tid, "ACCEPTED", evidence, reviewer=reviewer)
        self.tracker.transition(tid, "VERIFIED")
        self.tracker.refresh()
        self.tracker.commit("TASK_ACCEPTED", tid)

    def retry(self, tid, reason, reopen=False, instructions=""):
        record = self.tracker.state["tasks"][tid]
        if record["status"] in {"IN_PROGRESS", "RESERVED"}:
            raise OrchestratorError("Recover the interrupted attempt before retrying.")
        if record["status"] == "VERIFIED" and not reopen:
            raise OrchestratorError("Use reopen for an accepted task.")
        if record["status"] == "READY" and not record["deferred"]:
            raise OrchestratorError("Task is already ready; launch it through the normal workflow.")
        affected = self.tracker.invalidate_dependents(tid) if reopen else []
        self.record(tid, "REOPENED" if reopen else "RETRY_REQUESTED", reason,
                    previous_acceptance=record["acceptance"], invalidated_dependents=affected)
        record["acceptance"] = None
        record["manual_blocker"] = None
        record["deferred"] = False
        record["pending_instructions"] = instructions
        self.tracker.transition(tid, "READY")
        self.tracker.refresh()
        self.tracker.commit("TASK_REOPENED" if reopen else "TASK_RETRIED", tid, {"reason": reason})

    def mark(self, tid, status, reason):
        if status not in {"BLOCKED", "SKIPPED", "PAUSED"}:
            raise OrchestratorError("Unsupported human status action.")
        record = self.tracker.state["tasks"][tid]
        if record["status"] in {"IN_PROGRESS", "RESERVED", "VERIFIED"}:
            raise OrchestratorError("Recover or reopen this task before marking it.")
        self.record(tid, status, reason)
        if record["status"] != status:
            self.tracker.transition(tid, status)
        record["manual_blocker"] = reason if status == "BLOCKED" else None
        self.tracker.refresh()
        self.tracker.commit("TASK_" + status, tid, {"reason": reason})
