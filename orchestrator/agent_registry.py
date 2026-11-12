from .errors import OrchestratorError


class AgentRegistry:
    def __init__(self, lifecycle):
        self.agents = {a["id"]: a for a in lifecycle.data["agents"]}

    def get(self, agent_id):
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise OrchestratorError(f"Unknown lifecycle agent: {agent_id}") from exc
