import re
from .errors import OrchestratorError
from .io_utils import read_json, atomic_json

EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}


class ModelSelector:
    def __init__(self, path, lifecycle):
        self.path, self.lifecycle = path, lifecycle
        self.data = read_json(path)
        if not isinstance(self.data, dict) or set(self.data) != {"agents", "task_overrides"}:
            raise OrchestratorError("Model config requires agents and task_overrides objects.")
        for kind, known in (("agents", {a["id"] for a in lifecycle.data["agents"]}),
                            ("task_overrides", set(lifecycle.tasks))):
            if not isinstance(self.data[kind], dict) or set(self.data[kind]) - known:
                raise OrchestratorError(f"Unknown or malformed model configuration {kind}.")
            for key, selection in self.data[kind].items():
                self.validate(selection, allow_empty=True)

    @staticmethod
    def validate(selection, allow_empty=False):
        if not isinstance(selection, dict) or set(selection) - {"model", "reasoning_effort", "confirmed_in_cli"}:
            raise OrchestratorError("Invalid model selection fields.")
        if "confirmed_in_cli" in selection and type(selection["confirmed_in_cli"]) is not bool:
            raise OrchestratorError("confirmed_in_cli must be a boolean.")
        model, effort = selection.get("model"), selection.get("reasoning_effort")
        if allow_empty and model is None and effort is None:
            return
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model):
            raise OrchestratorError("Configure a model identifier shown by your Codex /model picker.")
        if effort not in EFFORTS:
            raise OrchestratorError(f"Invalid reasoning_effort; choose one supported by the selected model: {sorted(EFFORTS)}")
        if selection.get("confirmed_in_cli") is not True:
            raise OrchestratorError("Confirm this model/effort pair in Codex /model and set confirmed_in_cli=true.")

    def select(self, task):
        selection = self.data["task_overrides"].get(task["id"], self.data["agents"].get(task["assigned_agent"], {}))
        try:
            self.validate(selection)
        except OrchestratorError as exc:
            raise OrchestratorError(f"{task['assigned_agent']} / {task['id']}: {exc} Run setup-models.") from exc
        return {"model": selection["model"], "reasoning_effort": selection["reasoning_effort"]}

    def configure(self, key, model, effort, task_override=False):
        known = self.lifecycle.tasks if task_override else {a["id"] for a in self.lifecycle.data["agents"]}
        if key not in known:
            raise OrchestratorError(f"Unknown model mapping target: {key}")
        selection = {"model": model, "reasoning_effort": effort, "confirmed_in_cli": True}
        self.validate(selection)
        self.data["task_overrides" if task_override else "agents"][key] = selection
        atomic_json(self.path, self.data)
