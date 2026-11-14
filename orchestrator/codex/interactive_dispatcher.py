import json
import shutil
import signal
import subprocess
import sys
from .base_dispatcher import DispatchResult
from ..errors import OrchestratorError
from ..model_selector import ModelSelector


class InteractiveDispatcher:
    def __init__(self, executable="codex"):
        self.executable = executable

    def preflight(self):
        if not shutil.which(self.executable):
            raise OrchestratorError("Codex executable not found. Install/authenticate Codex and add it to PATH.")
        try:
            result = subprocess.run([self.executable, "--help"], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OrchestratorError(f"Unable to inspect Codex CLI: {exc}") from exc
        required = ("--model", "--config", "--ask-for-approval", "--sandbox", "--cd", "[PROMPT]")
        if result.returncode or any(flag not in result.stdout for flag in required):
            raise OrchestratorError("Installed Codex help does not expose required interactive arguments; review CLI compatibility.")

    def command(self, prompt, selection, root):
        ModelSelector.validate({**selection, "confirmed_in_cli": True})
        return [self.executable, "--model", selection["model"],
                "--config", "model_reasoning_effort=" + json.dumps(selection["reasoning_effort"]),
                "--ask-for-approval", "on-request", "--sandbox", "workspace-write",
                "--cd", str(root), "--", prompt]

    def run(self, prompt, selection, root, lock_fd=None):
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return DispatchResult(None, "Interactive Codex requires a real terminal; use --dry-run here.")
        process = None
        try:
            # Intentionally inherit all terminal streams. No pipes, capture_output, shell or exec subcommand.
            process = subprocess.Popen(self.command(prompt, selection, root), cwd=root,
                                       pass_fds=() if lock_fd is None else (lock_fd,))
            code = process.wait()
            return DispatchResult(code, None if code == 0 else f"Codex exited with code {code}.")
        except KeyboardInterrupt:
            if process is not None:
                if process.poll() is None:
                    process.send_signal(signal.SIGINT)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                return DispatchResult(process.returncode, "Interrupted by user; review report before retrying.", True)
            return DispatchResult(None, "Interrupted before process startup.", True)
        except OSError as exc:
            return DispatchResult(None, f"Codex startup failed: {exc}")
