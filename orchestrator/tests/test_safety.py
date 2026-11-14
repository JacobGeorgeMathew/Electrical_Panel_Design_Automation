import contextlib
import copy
import io
import json
import os
import unittest
from unittest.mock import patch

from orchestrator.codex.base_dispatcher import DispatchResult
from orchestrator.codex.interactive_dispatcher import InteractiveDispatcher
from orchestrator.configuration import load_config
from orchestrator.errors import OrchestratorError
from orchestrator.io_utils import atomic_json, read_json
from orchestrator.lifecycle_loader import load_lifecycle
from orchestrator.lifecycle_validator import validate_lifecycle
from orchestrator.main import decision_menu, launch, main
from orchestrator.model_selector import ModelSelector
from orchestrator.progress_tracker import ProgressTracker
from orchestrator.report_manager import ReportManager
from orchestrator.task_scheduler import TaskScheduler
from orchestrator.terminal_ui import dry_run
from .support import Harness, ROOT


class SafetyTests(Harness):
    def test_multiple_active_attempts_are_rejected(self):
        state = self.tracker.state
        state["tasks"]["P0-T01"]["status"] = "IN_PROGRESS"
        state["tasks"]["P0-T02"]["status"] = "IN_PROGRESS"
        with self.assertRaises(OrchestratorError):
            self.tracker.validate_state(state)

    def test_report_path_escape_in_state_is_rejected(self):
        self.execute()
        state = copy.deepcopy(self.tracker.state)
        state["tasks"]["P0-T01"]["attempts"][0]["report_path"] = "../private.md"
        with self.assertRaises(OrchestratorError):
            self.tracker.validate_state(state)

    def test_all_skipped_does_not_mean_complete(self):
        for tid in self.lifecycle.tasks:
            self.decisions.mark(tid, "SKIPPED", "Explicit test skip")
        self.assertIsNone(self.scheduler.get_next_task())
        self.assertIsNone(self.scheduler.first_pending())
        self.assertFalse(self.scheduler.get_execution_progress()["complete"])

    def test_human_input_is_required_for_acceptance(self):
        self.execute()
        self.accept()
        self.execute("P0-T02")
        with self.assertRaisesRegex(OrchestratorError, "human input"):
            self.accept("P0-T02")
        self.decisions.human_input("P0-T02", "Confirmed isolated fixture setup")
        self.accept("P0-T02")

    def test_interrupt_finish_is_paused_never_verified(self):
        path = self.reports.path("P0-T01", 1)
        self.tracker.reserve("P0-T01", {"model": "fixture-model", "reasoning_effort": "low"}, path.relative_to(self.root), {})
        self.tracker.start("P0-T01")
        self.make_report(self.lifecycle.tasks["P0-T01"])
        report = self.reports.inspect(path, self.lifecycle.tasks["P0-T01"], 1)
        self.tracker.finish("P0-T01", DispatchResult(0, "Interrupted", True), report, {})
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "PAUSED")
        with self.assertRaises(OrchestratorError):
            self.accept()

    def test_external_and_malformed_schema_refs_fail_closed(self):
        for ref in ("https://example.invalid/schema.json", 123):
            with self.assertRaises(OrchestratorError):
                validate_lifecycle(self.data, {"$ref": ref})

    def test_invalid_menu_input_then_pause_preserves_review(self):
        self.execute()
        with patch("orchestrator.main.ui.ask", side_effect=["invalid", "8"]), patch("orchestrator.main.ui.display"):
            result = decision_menu(self.lifecycle.tasks["P0-T01"], self.tracker, self.reports, self.decisions)
        self.assertIsNone(result)
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "NEEDS_REVIEW")

    def test_accepting_report_requires_human_evidence(self):
        self.execute()
        with self.assertRaises(OrchestratorError):
            self.decisions.accept("P0-T01", "", "")

    def test_nonterminal_never_starts_subprocess(self):
        with patch("orchestrator.codex.interactive_dispatcher.sys.stdin.isatty", return_value=False):
            with patch("orchestrator.codex.interactive_dispatcher.subprocess.Popen") as popen:
                result = InteractiveDispatcher().run("test", {"model": "fixture-model", "reasoning_effort": "medium"}, self.root)
        popen.assert_not_called()
        self.assertIn("real terminal", result.error)

    def test_reconciliation_preserves_removed_task_history(self):
        self.execute()
        self.accept()
        changed = copy.deepcopy(self.data)
        tasks = changed["phases"][0]["milestones"][0]["tasks"]
        tasks.pop(0)
        tasks[0]["dependencies"] = []
        atomic_json(self.lifecycle_path, changed)
        new = ProgressTracker(load_lifecycle(self.lifecycle_path, self.schema_path), self.config)
        new.load(allow_changed=True)
        new.reconcile("Owner removed task from lifecycle")
        self.assertIn("P0-T01", new.state["retired_tasks"])
        self.assertEqual(len(new.state["retired_tasks"]["P0-T01"][0]["attempts"]), 1)


class ActualLifecycleDryRunTests(unittest.TestCase):
    def test_actual_first_five_and_assignments_without_writes_or_launch(self):
        config = load_config()
        lifecycle = load_lifecycle(config["lifecycle_path"], config["schema_path"])
        tracker = ProgressTracker(lifecycle, config)
        # Intentionally use fresh in-memory progress: this test does not depend on a user's live progress.
        tracker.state = tracker.initial_state()
        models = ModelSelector(config["model_config_path"], lifecycle)
        reports = ReportManager(config["root"], config["reports_dir"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch("subprocess.Popen") as popen:
            dry_run(lifecycle, tracker, TaskScheduler(lifecycle, tracker), models, reports, config)
        text = output.getvalue()
        expected = [f"{t['id']} | {t['assigned_agent']} |" for _, _, t in lifecycle.ordered[:5]]
        positions = [text.index(s) for s in expected]
        self.assertEqual(positions, sorted(positions))
        popen.assert_not_called()
