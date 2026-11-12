import contextlib
import io
import json
import subprocess
from unittest.mock import MagicMock, patch

from orchestrator.configuration import load_config
from orchestrator.model_selector import ModelSelector
from orchestrator.codex.interactive_dispatcher import InteractiveDispatcher
from orchestrator.codex.base_dispatcher import DispatchResult
from orchestrator.errors import OrchestratorError
from orchestrator.io_utils import atomic_json, read_json, now
from orchestrator.main import main, launch
from orchestrator.progress_tracker import ProgressTracker
from orchestrator.terminal_ui import safe_text
from .support import Harness, ROOT


class ModelAndReportTests(Harness):
    def setUp(self):
        super().setUp()
        self.model_path = self.root / "models.json"
        atomic_json(self.model_path, {"agents": {"architecture_lead": {"model": None, "reasoning_effort": None, "confirmed_in_cli": False}}, "task_overrides": {}})

    def test_unconfigured_agent_never_falls_back(self):
        selector = ModelSelector(self.model_path, self.lifecycle)
        with self.assertRaisesRegex(OrchestratorError, "setup-models"):
            selector.select(self.lifecycle.tasks["P0-T01"])

    def test_model_and_task_overrides(self):
        selector = ModelSelector(self.model_path, self.lifecycle)
        selector.configure("architecture_lead", "fixture-model", "medium")
        selector.configure("P0-T01", "fixture-model-two", "high", task_override=True)
        loaded = ModelSelector(self.model_path, self.lifecycle)
        self.assertEqual(loaded.select(self.lifecycle.tasks["P0-T01"]), {"model": "fixture-model-two", "reasoning_effort": "high"})

    def test_invalid_model_effort_and_confirmation(self):
        for selection in ({"model": "--malicious", "reasoning_effort": "high", "confirmed_in_cli": True},
                          {"model": "fixture-model", "reasoning_effort": "invented", "confirmed_in_cli": True},
                          {"model": "fixture-model", "reasoning_effort": "high", "confirmed_in_cli": False}):
            with self.assertRaises(OrchestratorError):
                ModelSelector.validate(selection)

    def test_report_rejects_malformed_and_wrong_attempt(self):
        task = self.lifecycle.tasks["P0-T01"]
        path = self.make_report(task)
        path.write_text(path.read_text().replace('"attempt": 1', '"attempt": 2'))
        self.assertTrue(self.reports.inspect(path, task, 1)["errors"])
        path.write_text("# Report\nClaim: COMPLETED\n")
        self.assertTrue(self.reports.inspect(path, task, 1)["errors"])

    def test_report_path_traversal_and_symlink(self):
        with self.assertRaises(OrchestratorError):
            self.reports.path("../escape", 1)
        self.config["reports_dir"].mkdir(parents=True)
        (self.config["reports_dir"] / "P0-T01").symlink_to("/tmp", target_is_directory=True)
        with self.assertRaises(OrchestratorError):
            self.reports.path("P0-T01", 1)

    def test_terminal_control_characters_removed(self):
        self.assertNotIn("\x1b", safe_text("\x1b[2JMalicious terminal clear"))

    def test_deferred_requires_explicit_human_activation(self):
        self.data["phases"][0]["milestones"][0]["tasks"][0]["status"] = "deferred"
        self.reload()
        self.assertIsNone(self.scheduler.get_next_task())
        self.decisions.retry("P0-T01", "Owner approved activation", reopen=True)
        self.assertEqual(self.scheduler.get_next_task()["id"], "P0-T01")

    def test_retry_instructions_survive_restart(self):
        self.execute(code=1)
        self.decisions.retry("P0-T01", "Try a regression fix", instructions="Investigate race X first")
        other = ProgressTracker(self.lifecycle, self.config)
        other.load()
        self.assertEqual(other.state["tasks"]["P0-T01"]["pending_instructions"], "Investigate race X first")

    def test_gate_approval_must_match_current_attempt(self):
        first = self.data["phases"][0]["milestones"][0]["tasks"][0]
        first.update(type="human_gate", approver="Engineer", decision_id="D-test")
        self.reload()
        self.execute()
        self.decisions.gate("P0-T01", "Engineer", "Approved attempt one")
        self.accept()
        self.decisions.retry("P0-T01", "New evidence", reopen=True)
        self.execute()
        with self.assertRaises(OrchestratorError):
            self.accept()

    def test_invalidated_prerequisite_requires_new_attempt(self):
        self.execute()
        self.accept()
        self.decisions.human_input("P0-T02", "Fixture DB ready")
        self.execute("P0-T02")
        self.decisions.retry("P0-T01", "Recheck", reopen=True)
        self.execute()
        self.accept()
        with self.assertRaisesRegex(OrchestratorError, "Prerequisite acceptance changed"):
            self.accept("P0-T02")


class DispatcherTests(Harness):
    @patch("orchestrator.codex.interactive_dispatcher.sys.stdout.isatty", return_value=True)
    @patch("orchestrator.codex.interactive_dispatcher.sys.stdin.isatty", return_value=True)
    @patch("orchestrator.codex.interactive_dispatcher.subprocess.Popen")
    def test_interactive_invocation_inherits_terminal(self, popen, *_):
        popen.return_value.wait.return_value = 0
        dispatcher = InteractiveDispatcher()
        result = dispatcher.run("Prompt $() stays literal", {"model": "fixture-model", "reasoning_effort": "high"}, self.root, 42)
        args, kwargs = popen.call_args
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn("exec", args[0])
        self.assertNotIn("app-server", args[0])
        self.assertIn('model_reasoning_effort="high"', args[0])
        self.assertIn("--model", args[0])
        self.assertEqual(args[0][-1], "Prompt $() stays literal")
        self.assertEqual(kwargs["cwd"], self.root)
        self.assertEqual(kwargs["pass_fds"], (42,))
        for key in ("stdin", "stdout", "stderr", "capture_output", "shell"):
            self.assertNotIn(key, kwargs)

    @patch("orchestrator.codex.interactive_dispatcher.sys.stdout.isatty", return_value=True)
    @patch("orchestrator.codex.interactive_dispatcher.sys.stdin.isatty", return_value=True)
    @patch("orchestrator.codex.interactive_dispatcher.subprocess.Popen")
    def test_nonzero_and_startup_failure(self, popen, *_):
        dispatcher = InteractiveDispatcher()
        selection = {"model": "fixture-model", "reasoning_effort": "medium"}
        popen.return_value.wait.return_value = -15
        self.assertEqual(dispatcher.run("p", selection, self.root).exit_code, -15)
        popen.side_effect = OSError("missing executable")
        result = dispatcher.run("p", selection, self.root)
        self.assertIsNone(result.exit_code)
        self.assertIn("startup failed", result.error)

    @patch("orchestrator.codex.interactive_dispatcher.sys.stdout.isatty", return_value=True)
    @patch("orchestrator.codex.interactive_dispatcher.sys.stdin.isatty", return_value=True)
    @patch("orchestrator.codex.interactive_dispatcher.subprocess.Popen")
    def test_interrupt_waits_for_child(self, popen, *_):
        child = popen.return_value
        child.wait.side_effect = [KeyboardInterrupt(), 130]
        child.poll.return_value = None
        child.returncode = 130
        result = InteractiveDispatcher().run("p", {"model": "fixture-model", "reasoning_effort": "medium"}, self.root)
        self.assertTrue(result.interrupted)
        child.send_signal.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)

    @patch("orchestrator.codex.interactive_dispatcher.shutil.which", return_value=None)
    def test_missing_cli(self, _):
        with self.assertRaisesRegex(OrchestratorError, "not found"):
            InteractiveDispatcher().preflight()

    @patch("orchestrator.codex.interactive_dispatcher.shutil.which", return_value="/fixture/codex")
    @patch("orchestrator.codex.interactive_dispatcher.subprocess.run")
    def test_missing_supported_flags(self, run, _):
        run.return_value = subprocess.CompletedProcess([], 0, "Unknown CLI", "")
        with self.assertRaisesRegex(OrchestratorError, "required interactive arguments"):
            InteractiveDispatcher().preflight()


class CLITests(Harness):
    def setUp(self):
        super().setUp()
        config = json.loads((ROOT / "orchestrator/config/execution_config.json").read_text())
        config.update(project_repository_root=".", model_config_path="models.json")
        self.config_path = self.root / "config.json"
        atomic_json(self.config_path, config)
        mappings = json.loads((ROOT / "orchestrator/config/agent_model_config.json").read_text())
        mappings["agents"]["architecture_lead"] = {"model": "fixture-model", "reasoning_effort": "high", "confirmed_in_cli": True}
        atomic_json(self.root / "models.json", mappings)

    def invoke(self, *args):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(["--config", str(self.config_path), *args])
        return code, stream.getvalue()

    @patch("orchestrator.codex.interactive_dispatcher.subprocess.Popen")
    def test_dry_run_is_read_only(self, popen):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        code, output = self.invoke("--dry-run")
        after = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(code, 0, output)
        self.assertEqual(before, after)
        self.assertIn("P0-T01 | architecture_lead | fixture-model / high", output)
        self.assertIn("GENERATED PROMPT PREVIEW", output)
        popen.assert_not_called()

    def test_init_validate_status_and_resume(self):
        self.assertEqual(self.invoke("init")[0], 0)
        self.assertEqual(self.invoke("validate")[0], 0)
        self.assertIn("Next eligible task: P0-T01", self.invoke("status")[1])
        self.assertEqual(self.invoke("validate", "--require-models")[0], 2)
        saved = read_json(self.root / "planning/execution_state.json")
        self.assertEqual(saved["event_sequence"], 1)
        self.assertEqual(self.invoke("init")[0], 0)
        self.assertEqual(read_json(self.root / "planning/execution_state.json")["event_sequence"], 1)

    def test_configuration_rejects_bypass_and_escaping_paths(self):
        data = read_json(self.config_path)
        data["approval_behavior"] = "never"
        atomic_json(self.config_path, data)
        self.assertEqual(self.invoke("validate")[0], 2)
        data["approval_behavior"] = "on-request"
        data["state_path"] = "../escape.json"
        atomic_json(self.config_path, data)
        self.assertEqual(self.invoke("validate")[0], 2)

    def test_recover_interrupted_session(self):
        self.tracker.reserve("P0-T01", {"model": "fixture-model", "reasoning_effort": "high"},
                             self.reports.path("P0-T01", 1).relative_to(self.root), {})
        self.tracker.start("P0-T01")
        with patch("orchestrator.main.ui.confirm", return_value=True):
            self.assertEqual(self.invoke("recover")[0], 0)
        saved = read_json(self.root / "planning/execution_state.json")
        self.assertEqual(saved["tasks"]["P0-T01"]["status"], "PAUSED")
        self.assertIsNone(saved["tasks"]["P0-T01"]["attempts"][0]["exit_code"])

    def test_reports_unknown_task_is_actionable(self):
        code, text = self.invoke("reports", "missing")
        self.assertEqual(code, 2)
        self.assertIn("Unknown task", text)

    @patch("orchestrator.main.sys.stdin.isatty", return_value=True)
    @patch("orchestrator.main.sys.stdout.isatty", return_value=True)
    @patch("orchestrator.main.InteractiveDispatcher.preflight")
    def test_full_mocked_launch_returns_without_next_task(self, *_):
        config = load_config(self.config_path)
        models = ModelSelector(config["model_config_path"], self.lifecycle)
        def dispatch(prompt, selection, root, lock_fd):
            self.assertIn("Mandatory execution report", prompt)
            self.make_report(self.lifecycle.tasks["P0-T01"])
            return DispatchResult(0)
        with patch("orchestrator.main.InteractiveDispatcher.run", side_effect=dispatch) as run:
            with patch("orchestrator.main.ui.confirm", return_value=True), patch("orchestrator.main.decision_menu", return_value=None):
                with patch("orchestrator.main.ui.display"):
                    result = launch(self.lifecycle.tasks["P0-T01"], self.tracker, self.scheduler, models,
                                    self.reports, self.decisions, config, None)
        self.assertIsNone(result)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "NEEDS_REVIEW")
        self.assertEqual(self.tracker.state["tasks"]["P0-T02"]["attempt_count"], 0)

    def test_torn_history_fails_closed(self):
        self.tracker.commit("STATE_INITIALIZED")
        with self.config["history_path"].open("a") as stream:
            stream.write('{"partial":')
        code, text = self.invoke("status")
        self.assertEqual(code, 2)
        self.assertIn("Malformed execution history", text)

    @patch("orchestrator.main.sys.stdin.isatty", return_value=True)
    @patch("orchestrator.main.sys.stdout.isatty", return_value=True)
    @patch("orchestrator.main.InteractiveDispatcher.preflight")
    def test_failed_report_stop_policy_even_with_zero_exit(self, *_):
        config = load_config(self.config_path)
        models = ModelSelector(config["model_config_path"], self.lifecycle)
        def dispatch(*args):
            self.make_report(self.lifecycle.tasks["P0-T01"], assessment="FAILED")
            return DispatchResult(0)
        with patch("orchestrator.main.InteractiveDispatcher.run", side_effect=dispatch):
            with patch("orchestrator.main.ui.confirm", return_value=True), patch("orchestrator.main.ui.display"):
                with patch("orchestrator.main.decision_menu", return_value=""):
                    result = launch(self.lifecycle.tasks["P0-T01"], self.tracker, self.scheduler, models,
                                    self.reports, self.decisions, config, None)
        self.assertIsNone(result)
        self.assertEqual(self.tracker.state["tasks"]["P0-T01"]["status"], "FAILED")
