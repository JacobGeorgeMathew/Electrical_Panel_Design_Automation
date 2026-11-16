import contextlib
import copy
import io
from unittest.mock import patch

from orchestrator.decision_manager import DecisionManager
from orchestrator.errors import OrchestratorError
from orchestrator.main import decision_menu
from orchestrator.progress_tracker import ProgressTracker
from orchestrator.task_scheduler import TaskScheduler
from orchestrator.terminal_ui import show_status
from .support import Harness
from .test_execution import CLIHarness


class HumanOverrideTests(Harness):
    def override(self, **kwargs):
        options = dict(reviewer="Responsible developer", evidence="Reviewed report and source",
                       rationale="Accept missing platform run; track it before release", responsibility_acknowledged=True)
        options.update(kwargs)
        self.decisions.accept_partial("P0-T01", **options)

    def test_partial_override_preserves_report_unlocks_dependencies_and_resumes(self):
        self.execute(assessment="PARTIALLY_COMPLETED", fail_profile=True)
        before = copy.deepcopy(self.tracker.state["tasks"]["P0-T01"]["attempts"])
        path = self.reports.path("P0-T01", 1)
        raw = path.read_bytes()
        self.override()
        record = self.tracker.state["tasks"]["P0-T01"]
        self.assertEqual(record["status"], "VERIFIED")
        self.assertEqual(record["attempts"], before)
        self.assertEqual(path.read_bytes(), raw)
        acceptance = record["acceptance"]
        self.assertEqual(acceptance["human_assessment"], "COMPLETED")
        self.assertEqual(acceptance["original_assessment"], "PARTIALLY_COMPLETED")
        self.assertEqual(acceptance["accepted_exceptions"][0]["result"], "NOT_RUN")
        self.assertEqual(self.scheduler.get_next_task()["id"], "P0-T02")
        restarted = ProgressTracker(self.lifecycle, self.config)
        restarted.load()
        self.assertEqual(restarted.state["tasks"]["P0-T01"]["acceptance"], acceptance)
        self.assertEqual(restarted.events()[-1]["event_type"], "TASK_COMPLETED_BY_HUMAN_OVERRIDE")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            show_status(TaskScheduler(self.lifecycle, restarted))
        self.assertIn("Completed by human override", output.getvalue())
        self.assertIn("P0-T01", output.getvalue())

    def test_failed_and_unverified_checks_are_explicitly_recorded(self):
        self.execute(assessment="PARTIALLY_COMPLETED")
        # A complete new attempt with failing results, rather than changing an
        # already finalized report (which must fail hash checking).
        self.decisions.retry("P0-T01", "Inspect failed checks")
        task = self.lifecycle.tasks["P0-T01"]
        self.tracker.reserve("P0-T01", {"model": "fixture-model", "reasoning_effort": "high"},
                             self.reports.path("P0-T01", 2).relative_to(self.root), {})
        self.tracker.start("P0-T01")
        path = self.make_report(task, 2, assessment="PARTIALLY_COMPLETED")
        path.write_text(path.read_text().replace('"result": "PASS"', '"result": "FAIL"', 1))
        from orchestrator.codex.base_dispatcher import DispatchResult
        self.tracker.finish("P0-T01", DispatchResult(0), self.reports.inspect(path, task, 2), {})
        self.override()
        exceptions = self.tracker.state["tasks"]["P0-T01"]["acceptance"]["accepted_exceptions"]
        self.assertEqual(exceptions[0]["kind"], "criterion")
        self.assertEqual(exceptions[0]["result"], "FAIL")

    def test_normal_acceptance_still_rejects_partial(self):
        self.execute(assessment="PARTIALLY_COMPLETED")
        with self.assertRaisesRegex(OrchestratorError, "PARTIALLY_COMPLETED"):
            self.accept()

    def test_requires_name_evidence_rationale_and_acknowledgement(self):
        self.execute(assessment="PARTIALLY_COMPLETED")
        before = self.config["state_path"].read_bytes()
        for kwargs in ({"reviewer": " "}, {"evidence": ""}, {"rationale": ""},
                       {"responsibility_acknowledged": False}):
            with self.assertRaises(OrchestratorError):
                self.override(**kwargs)
        self.assertEqual(before, self.config["state_path"].read_bytes())

    def test_changed_missing_or_malformed_report_rejected(self):
        self.execute(assessment="PARTIALLY_COMPLETED")
        path = self.reports.path("P0-T01", 1)
        raw = path.read_bytes()
        for contents in (raw + b"\nEdited", b"Malformed report"):
            path.write_bytes(contents)
            with self.assertRaises(OrchestratorError):
                self.override()
        path.unlink()
        with self.assertRaises(OrchestratorError):
            self.override()

    def test_failed_process_cannot_use_partial_override(self):
        self.execute(code=1, assessment="PARTIALLY_COMPLETED")
        with self.assertRaisesRegex(OrchestratorError, "PARTIALLY_COMPLETED task"):
            self.override()

    def test_changed_lifecycle_requires_new_attempt(self):
        self.execute(assessment="PARTIALLY_COMPLETED")
        self.tracker.state["tasks"]["P0-T01"]["attempts"][-1]["lifecycle_fingerprint"] = "obsolete"
        with self.assertRaisesRegex(OrchestratorError, "earlier lifecycle"):
            self.override()

    def test_human_gate_and_required_input_still_explicit(self):
        task = self.data["phases"][0]["milestones"][0]["tasks"][0]
        task.update(type="human_gate", approver="Named engineer", human_input="Reference cases")
        self.reload()
        self.execute(assessment="PARTIALLY_COMPLETED")
        with self.assertRaisesRegex(OrchestratorError, "gate approval"):
            self.override()
        self.decisions.gate("P0-T01", "Named engineer", "Explicit gate decision")
        with self.assertRaisesRegex(OrchestratorError, "human input"):
            self.override()
        self.decisions.human_input("P0-T01", "Reference supplied")
        self.override()

    def test_incomplete_and_changed_prerequisites_cannot_be_overridden(self):
        self.execute()
        self.accept()
        self.decisions.human_input("P0-T02", "Fixture ready")
        self.execute("P0-T02", assessment="PARTIALLY_COMPLETED")
        self.decisions.retry("P0-T01", "Recheck prerequisite", reopen=True)
        with self.assertRaisesRegex(OrchestratorError, "prerequisites"):
            self.decisions.accept_partial("P0-T02", "Developer", "Evidence", "Rationale", True)
        self.execute()
        self.accept()
        with self.assertRaisesRegex(OrchestratorError, "Prerequisite acceptance changed"):
            self.decisions.accept_partial("P0-T02", "Developer", "Evidence", "Rationale", True)

    def test_reopen_preserves_override_history(self):
        self.execute(assessment="PARTIALLY_COMPLETED")
        self.override()
        accepted = copy.deepcopy(self.tracker.state["tasks"]["P0-T01"]["acceptance"])
        self.decisions.retry("P0-T01", "Resolve remaining work", reopen=True)
        record = self.tracker.state["tasks"]["P0-T01"]
        self.assertIsNone(record["acceptance"])
        self.assertEqual(record["human_decisions"][-1]["previous_acceptance"], accepted)
        self.assertEqual(record["attempt_count"], 1)

    def test_missing_override_audit_record_fails_state_validation(self):
        self.execute(assessment="PARTIALLY_COMPLETED")
        self.override()
        state = copy.deepcopy(self.tracker.state)
        state["tasks"]["P0-T01"]["human_decisions"] = []
        with self.assertRaisesRegex(OrchestratorError, "Malformed execution state"):
            self.tracker.validate_state(state)

    def test_menu_confirmation_and_cancel(self):
        self.execute(assessment="PARTIALLY_COMPLETED", fail_profile=True)
        with patch("orchestrator.main.ui.ask", side_effect=["11", "Developer", "Report checked", "Accept documented gap", "8"]), \
                patch("orchestrator.main.ui.confirm", return_value=False), patch("orchestrator.main.ui.display"):
            decision_menu(self.lifecycle.tasks["P0-T01"], self.tracker, self.reports, self.decisions)
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "PARTIALLY_COMPLETED")
        with patch("orchestrator.main.ui.ask", side_effect=["11", "Developer", "Report checked", "Accept documented gap"]), \
                patch("orchestrator.main.ui.confirm", return_value=True), patch("orchestrator.main.ui.display") as display:
            decision_menu(self.lifecycle.tasks["P0-T01"], self.tracker, self.reports, self.decisions)
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "VERIFIED")
        self.assertTrue(any("NOT_RUN" in str(call) for call in display.call_args_list))


class OverrideCLITests(CLIHarness):
    def test_review_after_restart_overrides_without_launch(self):
        self.execute(assessment="PARTIALLY_COMPLETED", fail_profile=True)
        with patch("orchestrator.main.ui.ask", side_effect=["11", "Developer", "Checked source and report", "Accept missing platform check"]), \
                patch("orchestrator.main.ui.confirm", return_value=True), patch("subprocess.Popen") as popen:
            code, output = self.invoke("review", "P0-T01")
        self.assertEqual(code, 0, output)
        self.assertIn("COMPLETED by human override", output)
        popen.assert_not_called()
        self.assertEqual(self.invoke("validate")[0], 0)
        self.assertIn("Next eligible task: P0-T02", self.invoke("status")[1])
