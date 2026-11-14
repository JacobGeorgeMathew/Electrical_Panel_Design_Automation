import copy
from unittest.mock import patch

from orchestrator.errors import OrchestratorError
from orchestrator.io_utils import atomic_json, read_json
from orchestrator.lifecycle_loader import load_lifecycle
from orchestrator.lifecycle_reconciliation import reconciliation_plan
from orchestrator.progress_tracker import ProgressTracker
from .support import Harness
from .test_execution import CLIHarness


class ReconciliationTests(Harness):
    def changed_tracker(self, change):
        self.previous = self.lifecycle
        changed = copy.deepcopy(self.data)
        change(changed)
        atomic_json(self.lifecycle_path, changed)
        tracker = ProgressTracker(load_lifecycle(self.lifecycle_path, self.schema_path), self.config)
        tracker.load(allow_changed=True)
        return tracker

    def test_unrelated_change_preserves_acceptance_and_resumes(self):
        self.execute()
        self.accept()
        accepted = copy.deepcopy(self.tracker.state["tasks"]["P0-T01"])
        new = self.changed_tracker(lambda d: d["phases"][0]["milestones"][0]["tasks"][2].update(title="Revised fixture"))
        plan = reconciliation_plan(self.previous, new.lifecycle, new.state)
        self.assertEqual(plan["preserved_verified"], ["P0-T01"])
        new.reconcile("Owner adopted scoped revision", previous=self.previous)
        self.assertEqual(new.state["tasks"]["P0-T01"], accepted)
        restarted = ProgressTracker(new.lifecycle, self.config)
        restarted.load()
        self.assertEqual(restarted.state["tasks"]["P0-T01"]["acceptance"], accepted["acceptance"])
        self.assertEqual(restarted.events()[-1]["details"]["mode"], "preserve_unaffected")

    def test_changed_prerequisite_invalidates_verified_dependents(self):
        self.execute()
        self.accept()
        self.decisions.human_input("P0-T02", "Test DB supplied")
        self.execute("P0-T02")
        self.accept("P0-T02")
        old_attempts = copy.deepcopy(self.tracker.state["tasks"]["P0-T02"]["attempts"])
        new = self.changed_tracker(lambda d: d["phases"][0]["milestones"][0]["tasks"][0].update(title="Changed scope"))
        new.reconcile("New prerequisite", previous=self.previous)
        self.assertEqual(new.state["tasks"]["P0-T02"]["status"], "PAUSED")
        self.assertIsNone(new.state["tasks"]["P0-T02"]["acceptance"])
        self.assertEqual(new.state["tasks"]["P0-T02"]["attempts"], old_attempts)
        self.assertIsNotNone(new.state["tasks"]["P0-T02"]["human_decisions"][-1]["previous_acceptance"])

    def test_changed_profile_invalidates_unchanged_task(self):
        self.execute()
        self.accept()
        new = self.changed_tracker(lambda d: d["verification_profiles"]["document_review"].update(method="Stricter evidence"))
        plan = reconciliation_plan(self.previous, new.lifecycle, new.state)
        self.assertIn("P0-T01", plan["invalidated"])
        self.assertEqual(plan["preserved_verified"], [])

    def test_global_invariant_change_invalidates_all(self):
        self.execute()
        self.accept()
        new = self.changed_tracker(lambda d: d["invariants"].append("A new invariant"))
        plan = reconciliation_plan(self.previous, new.lifecycle, new.state)
        self.assertTrue(plan["global_context_changed"])
        self.assertEqual(set(plan["invalidated"]), set(self.previous.tasks))

    def test_wrong_predecessor_refused_without_writes(self):
        self.execute()
        new = self.changed_tracker(lambda d: d["phases"][0]["milestones"][0]["tasks"][2].update(title="Changed"))
        before = self.config["state_path"].read_bytes(), self.config["history_path"].read_bytes()
        with self.assertRaisesRegex(OrchestratorError, "does not match"):
            new.reconcile("Wrong source", previous=new.lifecycle)
        self.assertEqual(before, (self.config["state_path"].read_bytes(), self.config["history_path"].read_bytes()))

    def test_active_attempt_refused(self):
        self.tracker.reserve("P0-T01", {"model": "fixture-model", "reasoning_effort": "high"},
                             self.reports.path("P0-T01", 1).relative_to(self.root), {})
        with self.assertRaisesRegex(OrchestratorError, "Recover"):
            self.tracker.reconcile("Not while executing", previous=self.lifecycle)

    def test_removed_records_are_archived(self):
        self.execute()
        self.accept()
        def change(d):
            tasks = d["phases"][0]["milestones"][0]["tasks"]
            tasks.pop(0)
            tasks[0]["dependencies"] = []
        new = self.changed_tracker(change)
        new.reconcile("Removed task", previous=self.previous)
        self.assertEqual(new.state["retired_tasks"]["P0-T01"][0]["status"], "VERIFIED")

    def test_investigation_redefinition_requires_fresh_attempt(self):
        self.execute(assessment="PARTIALLY_COMPLETED", fail_profile=True)
        self.decisions.mark("P0-T01", "SKIPPED", "Blocked investigation")
        report_bytes = self.reports.path("P0-T01", 1).read_bytes()
        new = self.changed_tracker(lambda d: d["phases"][0]["milestones"][0]["tasks"][0].update(title="Review findings only"))
        new.reconcile("Separate investigation from qualification", previous=self.previous)
        self.assertEqual(new.state["tasks"]["P0-T01"]["status"], "PAUSED")
        self.assertIsNone(new.state["tasks"]["P0-T01"]["acceptance"])
        self.assertEqual(new.state["tasks"]["P0-T01"]["attempt_count"], 1)
        self.assertEqual(report_bytes, self.reports.path("P0-T01", 1).read_bytes())


class ReconciliationCLITests(CLIHarness):
    def prepare_change(self):
        self.execute()
        self.accept()
        self.original_path = self.root / "original.json"
        atomic_json(self.original_path, self.data)
        self.data["phases"][0]["milestones"][0]["tasks"][2]["title"] += " revised"
        atomic_json(self.lifecycle_path, self.data)

    def test_preview_does_not_write_progress_or_launch(self):
        self.prepare_change()
        paths = [self.config["state_path"], self.config["history_path"]]
        before = [p.read_bytes() for p in paths]
        with patch("orchestrator.main.ui.confirm") as confirm, patch("subprocess.Popen") as popen:
            code, output = self.invoke("reconcile", "--previous-lifecycle", str(self.original_path), "--preview")
        self.assertEqual(code, 0, output)
        self.assertIn("Preserve VERIFIED tasks: ['P0-T01']", output)
        self.assertEqual(before, [p.read_bytes() for p in paths])
        confirm.assert_not_called()
        popen.assert_not_called()

    def test_confirmation_required_and_resume_works(self):
        self.prepare_change()
        args = ("reconcile", "--previous-lifecycle", str(self.original_path))
        before = self.config["state_path"].read_bytes()
        with patch("orchestrator.main.ui.confirm", return_value=False):
            self.assertEqual(self.invoke(*args)[0], 0)
        self.assertEqual(before, self.config["state_path"].read_bytes())
        with patch("orchestrator.main.ui.confirm", return_value=True), patch("orchestrator.main.ui.ask", return_value="Approved scoped plan"):
            code, output = self.invoke(*args)
        self.assertEqual(code, 0, output)
        self.assertEqual(read_json(self.config["state_path"])["tasks"]["P0-T01"]["status"], "VERIFIED")
        self.assertEqual(self.invoke("validate")[0], 0)

    def test_plan_validation_before_migration_is_read_only(self):
        self.prepare_change()
        before = self.config["state_path"].read_bytes()
        code, output = self.invoke("validate", "--lifecycle-only")
        self.assertEqual(code, 0, output)
        self.assertIn("saved state not checked", output)
        self.assertEqual(before, self.config["state_path"].read_bytes())

    def test_forward_dependency_prevents_launch(self):
        tasks = self.data["phases"][0]["milestones"][0]["tasks"]
        tasks[0]["dependencies"] = [tasks[2]["id"]]
        tasks[1]["dependencies"] = []
        tasks[2]["dependencies"] = []
        atomic_json(self.lifecycle_path, self.data)
        with patch("subprocess.Popen") as popen:
            code, output = self.invoke()
        self.assertEqual(code, 2)
        self.assertIn("forward dependencies", output)
        popen.assert_not_called()
