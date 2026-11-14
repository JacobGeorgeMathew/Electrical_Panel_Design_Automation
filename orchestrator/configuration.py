from pathlib import Path
from .io_utils import read_json, confined
from .errors import OrchestratorError

DEFAULT_CONFIG = Path(__file__).parent / "config/execution_config.json"


def load_config(path=DEFAULT_CONFIG):
    path = Path(path).resolve()
    data = read_json(path)
    if not isinstance(data, dict):
        raise OrchestratorError("Execution config must be an object.")
    root_value = data.get("project_repository_root")
    if not isinstance(root_value, str) or not root_value:
        raise OrchestratorError("Configure project_repository_root relative to the configuration file.")
    root = (path.parent / root_value).resolve()
    if not root.is_dir():
        raise OrchestratorError(f"Repository root does not exist: {root}")
    paths = {key: confined(root, data.get(key)) for key in (
        "lifecycle_path", "schema_path", "state_path", "history_path", "reports_dir", "model_config_path")}
    if len(set(paths.values())) != len(paths):
        raise OrchestratorError("Configuration paths must be distinct.")
    for key in ("show_dry_run_on_startup", "require_launch_confirmation", "stop_after_failed_task", "stop_after_incomplete_report"):
        if type(data.get(key)) is not bool:
            raise OrchestratorError(f"{key} must be true or false.")
    if data["require_launch_confirmation"] is not True:
        raise OrchestratorError("This version requires confirmation before every interactive launch.")
    if data.get("approval_behavior") != "on-request":
        raise OrchestratorError("approval_behavior must be on-request; permission bypass is unsupported.")
    if data.get("scheduling_policy", "strict") != "strict":
        raise OrchestratorError("Only strict declared ordering is supported; correct forward dependencies explicitly.")
    return {**data, **paths, "root": root, "config_path": path}
