import contextlib
import copy
import io
from unittest.mock import patch

from orchestrator.io_utils import atomic_json
from orchestrator.main import decision_menu
from orchestrator.progress_tracker import ProgressTracker, STATUSES
from orchestrator.terminal_ui import show_status
from .support import Harness
from .test_execution import CLIHarness


class ManualCompletionTests(Harness):
    def test_every_task_status_can_be_completed_and_reloaded(self):
        for status in sorted(STATUSES):
            with self.subTest(status=status):
                self.tracker.state = self.tracker.initial_state()
                self.tracker.state["event_sequence"] = len(self.tracker.events())
                # State fixture has no invented execution evidence. Active states
                # are established by real reserve/start calls below.
                if status in {"RESERVED", "IN_PROGRESS"}:
                    self.tracker.reserve("P0-T01", {"model": "fixture-model", "reasoning_effort": "medium"},
                                         self.reports.path("P0-T01", 1).relative_to(self.root), {})
                    if status == "IN_PROGRESS":
                        self.tracker.start("P0-T01")
                else:
                    self.tracker.state["tasks"]["P0-T01"]["status"] = status
                # Keep existing append-only history while switching test fixtures.
                self.tracker.state["event_sequence"] = len(self.tracker.events())
                attempts = copy.deepcopy(self.tracker.state["tasks"]["P0-T01"]["attempts"])
                self.decisions.complete_manually("P0-T01")
                resumed = ProgressTracker(self.lifecycle, self.config)
                resumed.load()
                record = resumed.state["tasks"]["P0-T01"]
                self.assertEqual(record["status"], "VERIFIED")
                self.assertEqual(record["acceptance"]["previous_status"], status)
                self.assertEqual(record["attempts"], attempts)
                self.assertIsNone(resumed.state["current_task_id"])
                self.assertEqual(resumed.events()[-1]["event_type"], "TASK_COMPLETED_MANUALLY")

    def test_incomplete_dependencies_gate_input_blocker_and_deferral_do_not_block(self):
        task = self.data["phases"][0]["milestones"][0]["tasks"][1]
        task.update(type="human_gate", approver="Engineer", human_input="External input", status="deferred")
        self.reload()
        record = self.tracker.state["tasks"]["P0-T02"]
        record["manual_blocker"] = "Unavailable runtime"
        self.decisions.complete_manually("P0-T02")
        self.assertEqual(record["status"], "VERIFIED")
        self.assertFalse(record["deferred"])
        self.assertIsNone(record["manual_blocker"])
        self.assertEqual(record["attempt_count"], 0)
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "READY")
        self.decisions.complete_manually("P0-T01")
        self.assertEqual(self.scheduler.get_next_task()["id"], "P0-T03")

    def test_failed_exit_missing_and_changed_reports_do_not_block(self):
        for report in (False, True):
            with self.subTest(report=report):
                if self.tracker.state["tasks"]["P0-T01"]["status"] == "VERIFIED":
                    self.decisions.retry("P0-T01", "Test retry", reopen=True)
                self.execute(code=9, report=report, assessment="FAILED", fail_profile=True)
                record = self.tracker.state["tasks"]["P0-T01"]
                latest = self.reports.path("P0-T01", record["attempt_count"])
                if report:
                    latest.write_text("Changed, malformed report")
                before = latest.read_bytes() if report else None
                attempts = copy.deepcopy(record["attempts"])
                with patch.object(self.reports, "inspect", side_effect=AssertionError("Report must not gate completion")):
                    self.decisions.complete_manually("P0-T01", "Developer", "Override failed run")
                self.assertEqual(record["attempts"], attempts)
                self.assertEqual(latest.read_bytes() if report else None, before)
                ProgressTracker(self.lifecycle, self.config).load()

    def test_stale_context_and_dependency_acceptance_are_bypassed(self):
        self.execute(assessment="PARTIALLY_COMPLETED")
        attempt = self.tracker.state["tasks"]["P0-T01"]["attempts"][-1]
        attempt["lifecycle_fingerprint"] = "Older lifecycle"
        attempt["dependency_acceptances"] = {"old": "old hash"}
        self.decisions.complete_manually("P0-T01")
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "VERIFIED")

    def test_previous_acceptance_survives_repeat_and_reopen(self):
        self.decisions.complete_manually("P0-T01", "Developer", "First decision")
        old = copy.deepcopy(self.tracker.state["tasks"]["P0-T01"]["acceptance"])
        self.decisions.complete_manually("P0-T01", "Developer", "Second decision")
        record = self.tracker.state["tasks"]["P0-T01"]
        self.assertEqual(record["human_decisions"][-1]["previous_acceptance"], old)
        self.decisions.retry("P0-T01", "Do the work now", reopen=True)
        self.assertEqual(record["status"], "READY")
        self.assertEqual(record["human_decisions"][-1]["previous_acceptance"]["mode"], "MANUAL_COMPLETION")

    def test_other_active_task_is_not_cleared(self):
        self.tracker.reserve("P0-T01", {"model": "fixture-model", "reasoning_effort": "medium"},
                             self.reports.path("P0-T01", 1).relative_to(self.root), {})
        self.decisions.complete_manually("P0-T02")
        self.assertEqual(self.tracker.state["current_task_id"], "P0-T01")
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "RESERVED")
        ProgressTracker(self.lifecycle, self.config).load()

    def test_menu_selects_any_task_and_displays_manual_status(self):
        with patch("orchestrator.main.ui.ask", side_effect=["12", "P0-T03", "", ""]), \
                patch("orchestrator.main.ui.confirm", return_value=True), patch("orchestrator.main.ui.display"):
            decision_menu(self.lifecycle.tasks["P0-T01"], self.tracker, self.reports, self.decisions)
        self.assertEqual(self.tracker.state["tasks"]["P0-T03"]["status"], "VERIFIED")
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "READY")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            show_status(self.scheduler)
        self.assertIn("Completed manually (acceptance checks bypassed): P0-T03", output.getvalue())


class ManualCompletionCLITests(CLIHarness):
    def test_complete_without_attempt_or_model_config(self):
        (self.root / "models.json").unlink()
        with patch("orchestrator.main.ui.ask", return_value=""), \
                patch("orchestrator.main.ui.confirm", return_value=True), patch("subprocess.Popen") as popen:
            code, output = self.invoke("complete", "P0-T03")
        self.assertEqual(code, 0, output)
        self.assertIn("COMPLETED manually", output)
        popen.assert_not_called()
        resumed = ProgressTracker(self.lifecycle, self.config)
        resumed.load()
        self.assertEqual(resumed.state["tasks"]["P0-T03"]["status"], "VERIFIED")

    def test_review_without_report_offers_menu_12(self):
        (self.root / "models.json").unlink()
        with patch("orchestrator.main.ui.ask", side_effect=["12", "", "", ""]), \
                patch("orchestrator.main.ui.confirm", return_value=True), patch("subprocess.Popen") as popen:
            code, output = self.invoke("review", "P0-T02")
        self.assertEqual(code, 0, output)
        self.assertIn("No execution attempts", output)
        self.assertIn("COMPLETED manually", output)
        popen.assert_not_called()

    def test_cancel_does_not_complete(self):
        self.invoke("init")
        before = self.config["state_path"].read_bytes()
        with patch("orchestrator.main.ui.ask", return_value=""), patch("orchestrator.main.ui.confirm", return_value=False):
            code, output = self.invoke("complete", "P0-T01")
        self.assertEqual(code, 0, output)
        self.assertEqual(before, self.config["state_path"].read_bytes())

    def test_forward_dependencies_do_not_block_manual_completion(self):
        tasks = self.data["phases"][0]["milestones"][0]["tasks"]
        tasks[0]["dependencies"] = ["P0-T03"]
        tasks[1]["dependencies"] = []
        tasks[2]["dependencies"] = []
        atomic_json(self.lifecycle_path, self.data)
        with patch("orchestrator.main.ui.ask", return_value=""), patch("orchestrator.main.ui.confirm", return_value=True):
            code, output = self.invoke("complete", "P0-T01")
        self.assertEqual(code, 0, output)
