import copy

from orchestrator.errors import OrchestratorError
from orchestrator.lifecycle_loader import load_lifecycle
from orchestrator.lifecycle_validator import validate_lifecycle
from orchestrator.lifecycle_reconciliation import reconciliation_plan
from orchestrator.progress_tracker import ProgressTracker
from orchestrator.prompt_generator import generate_prompt
from .support import Harness, ROOT


class ConsolidationTests(Harness):
    def actual_pair(self):
        return (load_lifecycle(ROOT / "planning/lifecycle_history/2026-11-15.before-consolidation.json", ROOT / "planning/schema.json"),
                load_lifecycle(ROOT / "planning/development_lifecycle.json", ROOT / "planning/schema.json"))

    def test_preserve_completed_definitions_and_every_constituent_requirement(self):
        old, new = self.actual_pair()
        old_order = [t["id"] for _, _, t in old.ordered]
        completed = old_order[:old_order.index("P1-T09") + 1]
        self.assertEqual(len(completed), 19)
        for tid in completed:
            self.assertEqual(old.tasks[tid], new.tasks[tid])
            self.assertEqual(old.context(tid)[0]["id"], new.context(tid)[0]["id"])
            self.assertEqual(old.context(tid)[1]["id"], new.context(tid)[1]["id"])
        represented = []
        for task in new.tasks.values():
            sources = task.get("merged_from", [task["id"]])
            represented.extend(sources)
            if len(sources) == 1:
                continue
            self.assertEqual([old_order.index(s) for s in sources], list(range(old_order.index(sources[0]), old_order.index(sources[0]) + len(sources))))
            self.assertNotIn(task["type"], {"human_gate", "phase_acceptance"})
            for source in sources:
                original = old.tasks[source]
                self.assertEqual(task["assigned_agent"], original["assigned_agent"])
                self.assertNotIn(original["type"], {"human_gate", "phase_acceptance"})
                for i, criterion in enumerate(original["acceptance_criteria"], 1):
                    self.assertIn(f"[{source} criterion {i}] {criterion}", task["acceptance_criteria"])
                for step in original["implementation_steps"]:
                    self.assertIn(f"[{source}] {step}", task["implementation_steps"])
                for key in ("planned_outputs", "input_files", "verification_profiles"):
                    self.assertTrue(set(original[key]) <= set(task[key]))
        self.assertEqual(represented, old_order)
        self.assertEqual(sum("merged_from" in t for t in new.tasks.values()), 12)
        self.assertEqual(len(new.tasks), 94)
        self.assertEqual(sum(len(p["milestones"]) for p in new.data["phases"]), 31)
        self.assertEqual(new.forward_dependencies, [])

    def test_reference_rewrites_preserve_19_acceptances(self):
        old, new = self.actual_pair()
        state = ProgressTracker(old, {**self.config, "root": ROOT}).initial_state()
        # This is an isolated planner fixture, never live acceptance.
        prefix = [t["id"] for _, _, t in old.ordered][:19]
        for tid in prefix:
            state["tasks"][tid]["status"] = "VERIFIED"
        plan = reconciliation_plan(old, new, state)
        self.assertFalse(plan["global_context_changed"])
        self.assertEqual(plan["preserved_verified"], sorted(prefix))
        self.assertEqual(len(plan["removed"]), 25)
        self.assertEqual(plan["consolidated_task_aliases"]["P2-T08"], "P2-T06")
        # A real policy edit still invalidates all evidence despite consolidation.
        changed = copy.deepcopy(new)
        changed.data["invariants"].append("Additional invariant")
        self.assertTrue(reconciliation_plan(old, changed, state)["global_context_changed"])

    def test_merged_attempt_cannot_be_silently_migrated(self):
        old, new = self.actual_pair()
        state = ProgressTracker(old, {**self.config, "root": ROOT}).initial_state()
        state["tasks"]["P2-T07"]["attempt_count"] = 1
        with self.assertRaisesRegex(OrchestratorError, "attempted/verified"):
            reconciliation_plan(old, new, state)

    def test_combined_prompt_uses_one_id_and_all_criteria(self):
        _, new = self.actual_pair()
        task = new.tasks["P2-T06"]
        tracker = ProgressTracker(new, {**self.config, "root": ROOT})
        prompt = generate_prompt(new, task, {"model": "fixture-model", "reasoning_effort": "high"},
                                 tracker.initial_state(), self.root / "attempt-01.md", 1, ROOT)
        self.assertIn("# Combined task execution", prompt)
        self.assertIn("P2-T06, P2-T07, P2-T08", prompt)
        self.assertIn("ONE selected lifecycle task", prompt)
        for criterion in task["acceptance_criteria"]:
            self.assertIn(criterion, prompt)

    def test_provenance_rejects_duplicate_or_live_sources(self):
        for sources in (["P0-T01", "P0-T01"], ["P0-T01", "P0-T02"]):
            data = copy.deepcopy(self.data)
            data["phases"][0]["milestones"][0]["tasks"][0]["merged_from"] = sources
            with self.assertRaisesRegex(OrchestratorError, "provenance|overlaps"):
                validate_lifecycle(data, self.schema)

    def test_merge_archives_records_and_survives_restart(self):
        # Exercise the actual merger with a temporary state/history pair only.
        old, new = self.actual_pair()
        config = {**self.config, "root": ROOT}
        before = ProgressTracker(old, config)
        before.state = before.initial_state()
        before.commit("STATE_INITIALIZED")
        migrated = ProgressTracker(new, config)
        migrated.load(allow_changed=True)
        migrated.reconcile("Test-only consolidation", previous=old)
        resumed = ProgressTracker(new, config)
        resumed.load()
        self.assertEqual(len(resumed.state["tasks"]), 94)
        self.assertIn("P2-T07", resumed.state["retired_tasks"])
        self.assertEqual(resumed.state["tasks"]["P2-T06"]["attempt_count"], 0)
        self.assertEqual(resumed.events()[-1]["details"]["mode"], "preserve_unaffected")
