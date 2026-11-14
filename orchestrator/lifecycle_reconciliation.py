"""Plan an explicit migration using a fingerprint-verified predecessor lifecycle."""
from .errors import OrchestratorError
from .io_utils import digest


def reconciliation_plan(previous, current, state):
    if previous.fingerprint != state["lifecycle_fingerprint"]:
        raise OrchestratorError("Previous lifecycle/schema does not match saved progress. Preserve the original schema too, or use conservative reconciliation.")
    if set(previous.tasks) != set(state["tasks"]):
        raise OrchestratorError("Previous lifecycle task IDs do not match saved progress.")
    if state["current_task_id"] or any(r["status"] in {"RESERVED", "IN_PROGRESS"} for r in state["tasks"].values()):
        raise OrchestratorError("Recover the active attempt before reconciling a lifecycle.")
    for tid, task in previous.tasks.items():
        if digest(task) != state["tasks"][tid]["definition_hash"]:
            raise OrchestratorError(f"Previous task definition does not match saved progress: {tid}")

    # Changes to executable context also invalidate evidence, even when the task
    # dictionary itself is identical. Unknown top-level fields fail conservatively.
    scoped = {"phases", "agents", "verification_profiles", "human_decisions"}
    descriptive = {"planning_validation", "scheduling_notes", "estimates"}
    def shared(lifecycle):
        return {k: v for k, v in lifecycle.data.items() if k not in scoped | descriptive}

    def context(lifecycle, tid):
        task = lifecycle.tasks[tid]
        phase, milestone = lifecycle.context(tid)
        return {
            "task": task,
            "phase": {k: v for k, v in phase.items() if k not in {"milestones", "effort_hours"}},
            "milestone": {k: v for k, v in milestone.items() if k != "tasks"},
            "agent": next(a for a in lifecycle.data["agents"] if a["id"] == task["assigned_agent"]),
            "profiles": {p: lifecycle.data["verification_profiles"][p] for p in task["verification_profiles"]},
            "decisions": [d for d in lifecycle.data.get("human_decisions", []) if d["gate_task_id"] == tid],
        }

    old_ids, new_ids = set(previous.tasks), set(current.tasks)
    global_change = digest(shared(previous)) != digest(shared(current)) or digest(previous.schema) != digest(current.schema)
    changed = {tid for tid in old_ids & new_ids if global_change or digest(context(previous, tid)) != digest(context(current, tid))}
    affected = changed | (old_ids - new_ids) | (new_ids - old_ids)
    while True:
        downstream = {tid for lifecycle in (previous, current) for tid, task in lifecycle.tasks.items()
                      if set(task["dependencies"]) & affected}
        if downstream <= affected:
            break
        affected |= downstream
    preserved = old_ids & new_ids - affected
    return {
        "global_context_changed": global_change,
        "changed": sorted(changed), "added": sorted(new_ids - old_ids), "removed": sorted(old_ids - new_ids),
        "invalidated": sorted(affected & old_ids & new_ids),
        "preserved": sorted(preserved),
        "preserved_verified": sorted(tid for tid in preserved if state["tasks"][tid]["status"] == "VERIFIED"),
    }
