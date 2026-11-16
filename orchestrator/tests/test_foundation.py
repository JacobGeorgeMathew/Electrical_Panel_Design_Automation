import copy
import json
from unittest.mock import patch

from orchestrator.errors import OrchestratorError, LifecycleChanged
from orchestrator.io_utils import atomic_json, read_json, execution_lock
from orchestrator.lifecycle_loader import load_lifecycle
from orchestrator.lifecycle_validator import validate_lifecycle
from orchestrator.agent_registry import AgentRegistry
from orchestrator.model_selector import ModelSelector
from orchestrator.prompt_generator import generate_prompt
from orchestrator.progress_tracker import ProgressTracker
from .support import Harness, ROOT


class LifecycleTests(Harness):
    def test_real_lifecycle_schema_and_order(self):
        actual = load_lifecycle(ROOT / "planning/development_lifecycle.json", ROOT / "planning/schema.json")
        self.assertEqual(len(actual.tasks), 94)
        self.assertEqual([t["id"] for _, _, t in actual.ordered[:5]], [f"P0-T0{i}" for i in range(1, 6)])
        self.assertEqual(actual.forward_dependencies, [])
        self.assertEqual(actual.tasks["P0-T05"]["verification_profiles"], ["document_review"])
        self.assertEqual(actual.tasks["P5-T00"]["merged_from"], [f"P5-T0{i}" for i in range(7)])
        self.assertIn("native_cad", actual.tasks["P5-T00"]["verification_profiles"])
        self.assertTrue(all(t["status"] == "deferred" for t in actual.tasks.values() if t["id"].startswith("P8-")))

    def test_actual_plan_references_and_phase_coverage(self):
        actual = load_lifecycle(ROOT / "planning/development_lifecycle.json", ROOT / "planning/schema.json")
        ids = set(actual.tasks)
        def references(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"task_ids", "required_task_ids", "gate_task_ids"}:
                        self.assertTrue(set(child) <= ids, (key, child))
                    elif key in {"gate_task_id", "exit_task_id"}:
                        self.assertIn(child, ids)
                    references(child)
            elif isinstance(value, list):
                for child in value:
                    references(child)
        references(actual.data)
        for phase in actual.data["phases"]:
            covered = {phase["exit_task_id"]}
            while True:
                expanded = covered | {dep for tid in covered for dep in actual.tasks[tid]["dependencies"]}
                if expanded == covered:
                    break
                covered = expanded
            self.assertTrue({t["id"] for m in phase["milestones"] for t in m["tasks"]} <= covered)

    def test_bad_json_and_duplicate_json_keys(self):
        for raw in ("{", '{"x": 1, "x": 2}', '{"x": NaN}'):
            self.lifecycle_path.write_text(raw)
            with self.assertRaises(OrchestratorError):
                read_json(self.lifecycle_path)

    def test_missing_file(self):
        with self.assertRaises(OrchestratorError):
            load_lifecycle(self.root / "absent.json", self.schema_path)

    def test_schema_and_incomplete_task(self):
        del self.data["phases"][0]["milestones"][0]["tasks"][0]["title"]
        with self.assertRaisesRegex(OrchestratorError, "schema errors"):
            validate_lifecycle(self.data, self.schema)

    def test_invalid_schema(self):
        with self.assertRaises(OrchestratorError):
            validate_lifecycle(self.data, {"type": 42})

    def test_duplicate_task(self):
        tasks = self.data["phases"][0]["milestones"][0]["tasks"]
        tasks.append(copy.deepcopy(tasks[0]))
        with self.assertRaisesRegex(OrchestratorError, "Duplicate"):
            validate_lifecycle(self.data, self.schema)

    def test_unknown_dependency_and_agent(self):
        first = self.data["phases"][0]["milestones"][0]["tasks"][0]
        first["dependencies"] = ["absent"]
        with self.assertRaisesRegex(OrchestratorError, "nonexistent"):
            validate_lifecycle(self.data, self.schema)
        first["dependencies"] = []
        first["assigned_agent"] = "absent"
        with self.assertRaisesRegex(OrchestratorError, "unknown agent"):
            validate_lifecycle(self.data, self.schema)

    def test_cycle(self):
        self.data["phases"][0]["milestones"][0]["tasks"][0]["dependencies"] = ["P0-T03"]
        with self.assertRaisesRegex(OrchestratorError, "Circular"):
            validate_lifecycle(self.data, self.schema)

    def test_agent_lookup(self):
        registry = AgentRegistry(self.lifecycle)
        self.assertEqual(registry.get("quality_engineer")["id"], "quality_engineer")
        with self.assertRaises(OrchestratorError):
            registry.get("invented")

    def test_strict_order_stops_at_forward_dependency(self):
        tasks = self.data["phases"][0]["milestones"][0]["tasks"]
        tasks[0]["dependencies"] = [tasks[2]["id"]]
        tasks[1]["dependencies"] = []
        tasks[2]["dependencies"] = []
        self.reload()
        self.assertIsNone(self.scheduler.get_next_task())
        self.assertEqual(self.scheduler.first_pending()["id"], "P0-T01")
        self.assertTrue(self.scheduler.get_blocked_tasks())

    def test_scheduler_queries_and_progress(self):
        self.assertEqual(self.scheduler.get_next_task()["id"], "P0-T01")
        self.assertEqual(len(self.scheduler.get_tasks_by_phase("P0")), 3)
        self.assertEqual(len(self.scheduler.get_tasks_by_milestone("P0-M1")), 3)
        self.assertEqual(self.scheduler.get_execution_progress()["remaining"], 3)
        with self.assertRaises(OrchestratorError):
            self.scheduler.get_task_by_id("absent")

    def test_prompt_includes_contract_and_prior_reports(self):
        self.execute()
        task = self.lifecycle.tasks["P0-T01"]
        prompt = generate_prompt(self.lifecycle, task, {"model": "fixture-model", "reasoning_effort": "high"},
            self.tracker.state, self.reports.path(task["id"], 2), 2, self.root, "Investigate an independent edge case.")
        for token in ("architecture_lead", "P0-M1", "attempt-01.md", "attempt-02.md", "orchestrator-result", "Investigate an independent edge case.", "Python owns progress"):
            self.assertIn(token, prompt)
        for criterion in task["acceptance_criteria"]:
            self.assertIn(criterion, prompt)

    def test_prompt_selects_backend_interpreter_without_changing_profiles(self):
        task = self.lifecycle.tasks["P0-T02"]
        profiles_before = copy.deepcopy(self.lifecycle.data["verification_profiles"])
        prompt = generate_prompt(self.lifecycle, task, {"model": "fixture-model", "reasoning_effort": "high"},
            self.tracker.state, self.reports.path(task["id"], 1), 1, self.root)
        self.assertIn("backend/.venv/bin/python relative to the repository root", prompt)
        self.assertIn("working directory is backend/, use .venv/bin/python", prompt)
        self.assertIn("(cd backend && .venv/bin/python -m pytest)", prompt)
        self.assertIn("Preserve its arguments, environment flags, fixture isolation and permission requirements", prompt)
        self.assertIn("sys.executable and sys.prefix", prompt)
        self.assertIn("report the environment blocker", prompt)
        self.assertIn("Do not install backend dependencies into the orchestrator environment", prompt)
        self.assertEqual(self.lifecycle.data["verification_profiles"], profiles_before)
        self.assertIn(json.dumps({p: profiles_before[p] for p in task["verification_profiles"]}, indent=2), prompt)

    def test_retry_prompt_retains_environment_rules_without_requiring_a_venv(self):
        self.execute(code=1)
        task = self.lifecycle.tasks["P0-T01"]
        self.assertFalse((self.root / "backend/.venv/bin/python").exists())
        prompt = generate_prompt(self.lifecycle, task, {"model": "fixture-model", "reasoning_effort": "medium"},
            self.tracker.state, self.reports.path(task["id"], 2), 2, self.root, "Review the inventory again.")
        self.assertIn("attempt-01.md", prompt)
        self.assertIn("# Python environments and command execution", prompt)
        self.assertIn("do not silently fall back to the orchestrator or system Python", prompt)
        self.assertIn("not a request to run the full suite for every task", prompt)
        self.assertIn("Review the inventory again.", prompt)


class StateTests(Harness):
    def test_init_atomic_state_and_resume(self):
        self.tracker.commit("STATE_INITIALIZED")
        other = ProgressTracker(self.lifecycle, self.config)
        self.assertEqual(other.load(), self.tracker.state)
        self.assertEqual(len(self.tracker.events()), 1)

    def test_invalid_transition(self):
        with self.assertRaises(OrchestratorError):
            self.tracker.transition("P0-T01", "VERIFIED")

    def test_zero_exit_does_not_accept(self):
        self.execute()
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "NEEDS_REVIEW")
        self.assertIsNone(self.scheduler.get_next_task())

    def test_accept_unlocks_dependency(self):
        self.execute()
        self.accept()
        self.assertEqual(self.scheduler.get_next_task()["id"], "P0-T02")
        self.assertEqual(ProgressTracker(self.lifecycle, self.config).load()["tasks"]["P0-T01"]["status"], "VERIFIED")

    def test_nonzero_missing_and_partial_reports(self):
        for code, report, expected in ((2, True, "FAILED"), (0, False, "PARTIALLY_COMPLETED")):
            if self.tracker.state["tasks"]["P0-T01"]["status"] != "READY":
                self.decisions.retry("P0-T01", "Explicit retry")
            self.execute(code=code, report=report)
            self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], expected)
            with self.assertRaises(OrchestratorError):
                self.accept()

    def test_unverified_profile_prevents_acceptance(self):
        self.execute(fail_profile=True)
        with self.assertRaisesRegex(OrchestratorError, "PASS evidence"):
            self.accept()

    def test_retry_numbers_and_report_preservation(self):
        self.execute(code=1)
        old = self.reports.path("P0-T01", 1).read_bytes()
        self.decisions.retry("P0-T01", "Human requested retry")
        self.execute()
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["attempt_count"], 2)
        self.assertEqual(old, self.reports.path("P0-T01", 1).read_bytes())
        with self.assertRaises(OrchestratorError):
            self.reports.prepare("P0-T01", 1)

    def test_reopen_invalidates_dependents_preserves_history(self):
        self.execute()
        self.accept()
        self.decisions.human_input("P0-T02", "Isolated fixture provisioned")
        self.execute("P0-T02")
        self.accept("P0-T02")
        self.decisions.retry("P0-T01", "Changed baseline", reopen=True)
        self.assertEqual(self.tracker.state["tasks"]["P0-T02"]["status"], "BLOCKED")
        self.assertEqual(len(self.tracker.state["tasks"]["P0-T02"]["attempts"]), 1)

    def test_skip_is_not_a_successful_dependency(self):
        self.decisions.mark("P0-T01", "SKIPPED", "Human deferral")
        self.assertIsNone(self.scheduler.get_next_task())
        self.assertFalse(self.scheduler.get_execution_progress()["complete"])

    def test_manual_blocker_requires_explicit_retry(self):
        self.decisions.mark("P0-T01", "BLOCKED", "Awaiting data")
        self.tracker.refresh()
        self.assertIsNone(self.scheduler.get_next_task())
        self.decisions.retry("P0-T01", "Data supplied")
        self.assertIsNotNone(self.scheduler.get_next_task())

    def test_human_gate_required(self):
        first = self.data["phases"][0]["milestones"][0]["tasks"][0]
        first.update(type="human_gate", approver="Qualified reviewer", decision_id="D-test")
        self.reload()
        self.execute()
        with self.assertRaisesRegex(OrchestratorError, "gate approval"):
            self.accept()
        self.decisions.gate("P0-T01", "Named engineer", "Signed fixture review")
        self.accept()

    def test_changed_report_is_not_accepted(self):
        self.execute()
        path = self.reports.path("P0-T01", 1)
        path.write_text(path.read_text() + "Edited after completion")
        with self.assertRaisesRegex(OrchestratorError, "Report changed"):
            self.accept()

    def test_lifecycle_change_requires_reconcile(self):
        self.execute()
        self.accept()
        changed = copy.deepcopy(self.data)
        changed["phases"][0]["milestones"][0]["tasks"][0]["title"] += " changed"
        atomic_json(self.lifecycle_path, changed)
        lifecycle = load_lifecycle(self.lifecycle_path, self.schema_path)
        other = ProgressTracker(lifecycle, self.config)
        with self.assertRaises(LifecycleChanged):
            other.load()
        other.load(allow_changed=True)
        other.reconcile("Human approved revised requirements")
        self.assertEqual(other.state["tasks"]["P0-T01"]["status"], "PAUSED")
        self.assertEqual(len(other.state["tasks"]["P0-T01"]["attempts"]), 1)

    def test_invalid_state_does_not_reset(self):
        atomic_json(self.config["state_path"], {"broken": True})
        with self.assertRaises(OrchestratorError):
            self.tracker.load()
        self.assertEqual(read_json(self.config["state_path"]), {"broken": True})

    def test_transaction_recovery_after_history_append(self):
        original = atomic_json
        def fail_state(path, value):
            if path == self.config["state_path"]:
                raise OSError("Injected crash")
            return original(path, value)
        with patch("orchestrator.progress_tracker.atomic_json", side_effect=fail_state):
            with self.assertRaises(OSError):
                self.tracker.commit("STATE_INITIALIZED")
        other = ProgressTracker(self.lifecycle, self.config)
        with self.assertRaisesRegex(OrchestratorError, "Interrupted state"):
            other.load()
        other.recover_transaction()
        other.load()
        self.assertEqual(len(other.events()), 1)

    def test_lock_prevents_second_runner(self):
        path = self.root / "run.lock"
        with execution_lock(path):
            with self.assertRaises(OrchestratorError):
                with execution_lock(path):
                    pass
