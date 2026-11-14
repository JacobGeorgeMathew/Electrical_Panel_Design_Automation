import copy
import json
from pathlib import Path
import tempfile
import unittest

from orchestrator.lifecycle_loader import load_lifecycle
from orchestrator.progress_tracker import ProgressTracker
from orchestrator.task_scheduler import TaskScheduler
from orchestrator.report_manager import ReportManager, HEADINGS
from orchestrator.decision_manager import DecisionManager
from orchestrator.io_utils import atomic_json
from orchestrator.codex.base_dispatcher import DispatchResult

ROOT = Path(__file__).resolve().parents[2]


class Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = json.loads((ROOT / "planning/development_lifecycle.json").read_text())
        self.schema = json.loads((ROOT / "planning/schema.json").read_text())
        self.data = copy.deepcopy(self.data)
        self.data["phases"] = self.data["phases"][:1]
        self.data["phases"][0]["milestones"] = self.data["phases"][0]["milestones"][:1]
        self.data["human_decisions"] = []
        self.config = {"root": self.root, "state_path": self.root / "planning/execution_state.json",
                       "history_path": self.root / "planning/execution_history.jsonl",
                       "reports_dir": self.root / "planning/task_reports"}
        self.lifecycle_path = self.root / "planning/development_lifecycle.json"
        self.schema_path = self.root / "planning/schema.json"
        self.reload()

    def reload(self):
        atomic_json(self.lifecycle_path, self.data)
        atomic_json(self.schema_path, self.schema)
        self.lifecycle = load_lifecycle(self.lifecycle_path, self.schema_path)
        self.tracker = ProgressTracker(self.lifecycle, self.config)
        self.tracker.load()
        self.scheduler = TaskScheduler(self.lifecycle, self.tracker)
        self.reports = ReportManager(self.root, self.config["reports_dir"])
        self.decisions = DecisionManager(self.tracker, self.reports)

    def make_report(self, task, number=1, assessment="COMPLETED", fail_profile=False):
        path = self.reports.path(task["id"], number)
        path.parent.mkdir(parents=True, exist_ok=True)
        result = ReportManager.result_template(task, number)
        result["assessment"] = assessment
        for item in result["acceptance_criteria"] + result["verification_profiles"]:
            item.update(result="PASS", evidence="Independent fixture passed; log fixture.log, exit 0.")
        if fail_profile:
            result["verification_profiles"][0]["result"] = "NOT_RUN"
        content = "\n\n".join("## " + h + "\nFixture evidence." for h in HEADINGS)
        path.write_text(content + "\n```orchestrator-result\n" + json.dumps(result) + "\n```\n")
        return path

    def execute(self, tid="P0-T01", code=0, report=True, **report_args):
        task = self.lifecycle.tasks[tid]
        number = self.tracker.state["tasks"][tid]["attempt_count"] + 1
        path = self.reports.path(tid, number)
        self.tracker.reserve(tid, {"model": "fixture-model", "reasoning_effort": "medium"}, path.relative_to(self.root), {}, "")
        self.tracker.start(tid)
        if report:
            self.make_report(task, number, **report_args)
        result = self.reports.inspect(path, task, number)
        self.tracker.finish(tid, DispatchResult(code), result, {})
        return result

    def accept(self, tid="P0-T01"):
        self.decisions.accept(tid, "Fixture human", "Independently reviewed fixture evidence.")
