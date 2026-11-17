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
            if record["status"] == "PARTIALLY_COMPLETED":
                raise OrchestratorError(f"{tid} is PARTIALLY_COMPLETED. Use menu option 11 to mark it COMPLETED by explicit human override, or retry to finish the remaining work.")
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

    def partial_acceptance_review(self, tid):
        """Return the exact exceptions a human would accept; never mutate progress."""
        task = self.tracker.lifecycle.tasks[tid]
        record = self.tracker.state["tasks"][tid]
        if record["status"] != "PARTIALLY_COMPLETED" or not record["attempts"]:
            raise OrchestratorError("Human completion override requires a PARTIALLY_COMPLETED task with an execution report.")
        if self.tracker.state["current_task_id"]:
            raise OrchestratorError("Finish or recover the active attempt before accepting a task.")
        attempt = record["attempts"][-1]
        if attempt.get("lifecycle_fingerprint") != self.tracker.lifecycle.fingerprint:
            raise OrchestratorError("Attempt belongs to an earlier lifecycle. Retry under the current task definition before overriding completion.")
        if any(self.tracker.state["tasks"][d]["status"] != "VERIFIED" for d in task["dependencies"]):
            raise OrchestratorError("All prerequisites must still be VERIFIED.")
        expected = {d: digest(self.tracker.state["tasks"][d]["acceptance"]) for d in task["dependencies"]}
        if attempt.get("dependency_acceptances", {}) != expected:
            raise OrchestratorError("Prerequisite acceptance changed since this attempt. Retry with current prerequisites.")
        report = self.reports.inspect(self.tracker.config["root"] / attempt["report_path"], task, attempt["number"])
        if attempt["exit_code"] != 0 or report["errors"] or report["assessment"] != "PARTIALLY_COMPLETED":
            raise OrchestratorError("Override requires exit code zero and a valid PARTIALLY_COMPLETED report. Missing/malformed reports or process failures require recovery/retry.")
        if report["sha256"] != attempt.get("report_sha256"):
            raise OrchestratorError("Report changed after execution. Preserve it and retry before requesting an override.")
        valid = [d for d in record["human_decisions"] if d.get("definition_hash") == digest(task)]
        if task["type"] == "human_gate" and not any(d["action"] == "GATE_APPROVED" and d.get("attempt") == attempt["number"] for d in valid):
            raise OrchestratorError("Record the required named human gate approval (menu option 9) before overriding completion.")
        if task.get("human_input") and not any(d["action"] == "INPUT_CONFIRMED" for d in valid):
            raise OrchestratorError("Record required human input (menu option 10) before overriding completion.")
        exceptions = []
        for kind, items in (("criterion", report["result"]["acceptance_criteria"]),
                            ("profile", report["result"]["verification_profiles"])):
            for item in items:
                if item["result"] != "PASS":
                    identifier = item["index"] if kind == "criterion" else item["id"]
                    description = task["acceptance_criteria"][identifier - 1] if kind == "criterion" else identifier
                    exceptions.append({"kind": kind, "id": identifier, "description": description,
                                       "result": item["result"], "evidence": item["evidence"]})
        return {"task_id": tid, "attempt": attempt["number"], "report_path": attempt["report_path"],
                "report_sha256": report["sha256"], "original_assessment": report["assessment"],
                "exceptions": exceptions}

    def accept_partial(self, tid, reviewer, evidence, rationale, responsibility_acknowledged=False):
        if not reviewer.strip() or not evidence.strip() or not rationale.strip():
            raise OrchestratorError("Human override requires your name, evidence reviewed, and a rationale covering remaining work and consequences.")
        if responsibility_acknowledged is not True:
            raise OrchestratorError("Explicit responsibility acknowledgement is required for human completion override.")
        review = self.partial_acceptance_review(tid)
        record = self.tracker.state["tasks"][tid]
        acceptance = {"timestamp": now(), "reviewer": reviewer, "evidence": evidence,
                      "evidence_reviewed": True, "definition_hash": digest(self.tracker.lifecycle.tasks[tid]),
                      "attempt": review["attempt"], "report_sha256": review["report_sha256"],
                      "mode": "HUMAN_OVERRIDE", "human_assessment": "COMPLETED",
                      "original_assessment": review["original_assessment"], "rationale": rationale,
                      "responsibility_acknowledged": True, "accepted_exceptions": review["exceptions"]}
        self.record(tid, "HUMAN_COMPLETION_OVERRIDE", rationale, acceptance=acceptance)
        record["acceptance"] = acceptance
        self.tracker.transition(tid, "VERIFIED")
        self.tracker.refresh()
        self.tracker.commit("TASK_COMPLETED_BY_HUMAN_OVERRIDE", tid, acceptance)

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

    def complete_manually(self, tid, reviewer="", reason=""):
        """Explicit human completion from any status, without acceptance gates."""
        task = self.tracker.lifecycle.tasks[tid]
        record = self.tracker.state["tasks"][tid]
        previous_status = record["status"]
        previous_acceptance = record["acceptance"]
        attempt = record["attempts"][-1] if record["attempts"] else {}
        acceptance = {
            "timestamp": now(), "reviewer": reviewer.strip() or "Human developer",
            "evidence": reason.strip() or "Manually marked completed by the developer",
            "evidence_reviewed": False, "definition_hash": digest(task),
            "attempt": record["attempt_count"], "report_sha256": attempt.get("report_sha256"),
            "mode": "MANUAL_COMPLETION", "human_assessment": "COMPLETED",
            "previous_status": previous_status, "checks_bypassed": True,
        }
        self.record(tid, "MANUAL_COMPLETION", acceptance["evidence"], acceptance=acceptance,
                    previous_acceptance=previous_acceptance,
                    previous_manual_blocker=record["manual_blocker"], previously_deferred=record["deferred"])
        record["acceptance"] = acceptance
        # Deliberately bypass ordinary transition/acceptance rules. Attempts and
        # their original outcomes remain untouched, including interrupted ones.
        record["status"] = "VERIFIED"
        record["manual_blocker"] = None
        record["deferred"] = False
        if self.tracker.state["current_task_id"] == tid:
            self.tracker.state["current_task_id"] = None
        self.tracker.refresh()
        self.tracker.commit("TASK_COMPLETED_MANUALLY", tid, acceptance)

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
