class OrchestratorError(Exception):
    """An actionable error safe to display at the terminal boundary."""


class LifecycleChanged(OrchestratorError):
    pass
