from collections import Counter
from .errors import OrchestratorError


class TaskScheduler:
    def __init__(self, lifecycle, tracker):
        self.lifecycle, self.tracker = lifecycle, tracker

    def get_task_by_id(self, task_id):
        try:
            return self.lifecycle.tasks[task_id]
        except KeyError as exc:
            raise OrchestratorError(f"Unknown task: {task_id}") from exc

    def first_pending(self):
        self.tracker.refresh()
        # An explicit skip advances the cursor but NEVER satisfies a dependency.
        return next((t for _, _, t in self.lifecycle.ordered
                     if self.tracker.state["tasks"][t["id"]]["status"] not in {"VERIFIED", "SKIPPED"}), None)

    def get_next_task(self):
        task = self.first_pending()
        if task and self.tracker.state["tasks"][task["id"]]["status"] == "READY":
            return task
        return None

    def get_blocked_tasks(self):
        self.tracker.refresh()
        return [(t, self.tracker.state["tasks"][t["id"]]["blockers"]) for _, _, t in self.lifecycle.ordered
                if self.tracker.state["tasks"][t["id"]]["blockers"]]

    def get_tasks_by_phase(self, phase_id):
        return [t for p, _, t in self.lifecycle.ordered if p["id"] == phase_id]

    def get_tasks_by_milestone(self, milestone_id):
        return [t for _, m, t in self.lifecycle.ordered if m["id"] == milestone_id]

    def get_execution_progress(self):
        first = self.first_pending()
        counts = Counter(r["status"] for r in self.tracker.state["tasks"].values())
        p, m = self.lifecycle.context(first["id"]) if first else (None, None)
        return {"project": self.lifecycle.data["project"], "phases": len(self.lifecycle.data["phases"]),
                "milestones": sum(len(p["milestones"]) for p in self.lifecycle.data["phases"]),
                "tasks": len(self.lifecycle.tasks), "counts": dict(counts),
                "remaining": len(self.lifecycle.tasks) - counts["VERIFIED"],
                "current_phase": p["id"] if p else None, "current_milestone": m["id"] if m else None,
                "complete": counts["VERIFIED"] == len(self.lifecycle.tasks)}
