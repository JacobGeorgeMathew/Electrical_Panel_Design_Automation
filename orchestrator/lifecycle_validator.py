"""Validate the supplied schema, then cross-reference and graph invariants."""
import re
from jsonschema import Draft202012Validator, validators, exceptions
from referencing.exceptions import Unresolvable
from .errors import OrchestratorError


def validate_lifecycle(data, schema):
    def local_refs(node):
        if isinstance(node, dict):
            for key in ("$ref", "$dynamicRef", "$recursiveRef"):
                if key in node and (not isinstance(node[key], str) or not node[key].startswith("#")):
                    raise OrchestratorError("Schema references must be local strings; external schemas are not fetched.")
            for value in node.values():
                local_refs(value)
        elif isinstance(node, list):
            for value in node:
                local_refs(value)

    local_refs(schema)
    # The repository uses the historic unversioned alias with basic JSON Schema keywords.
    alias = schema.get("$schema") if isinstance(schema, dict) else None
    cls = (Draft202012Validator if alias in (None, "http://json-schema.org/schema#")
           else validators.validator_for(schema, default=None))
    if cls is None:
        raise OrchestratorError(f"Unsupported schema dialect: {alias}")
    try:
        cls.check_schema(schema)
        errors = sorted(cls(schema).iter_errors(data), key=lambda e: str(list(e.path)))
    except (exceptions.SchemaError, Unresolvable) as exc:
        raise OrchestratorError(f"Invalid lifecycle schema: {exc}") from exc
    if errors:
        raise OrchestratorError("Lifecycle schema errors:\n" + "\n".join(
            f"  {'/'.join(map(str, e.path)) or '$'}: {e.message}" for e in errors[:30]))
    if not isinstance(data, dict):
        raise OrchestratorError("Lifecycle must be an object.")
    agents = data.get("agents", [])
    agent_ids = [a["id"] for a in agents]
    if len(set(agent_ids)) != len(agent_ids):
        raise OrchestratorError("Duplicate agent IDs.")
    ordered, seen, phase_ids, milestone_ids = [], set(), set(), set()
    for phase in data.get("phases", []):
        if phase["id"] in phase_ids:
            raise OrchestratorError(f"Duplicate phase: {phase['id']}")
        phase_ids.add(phase["id"])
        for milestone in phase["milestones"]:
            if milestone["id"] in milestone_ids:
                raise OrchestratorError(f"Duplicate milestone: {milestone['id']}")
            milestone_ids.add(milestone["id"])
            for task in milestone["tasks"]:
                tid = task.get("id", "")
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", tid) or tid in seen:
                    raise OrchestratorError(f"Duplicate or unsafe task ID: {tid!r}")
                seen.add(tid)
                for key in ("title", "type", "status", "assigned_agent"):
                    if not isinstance(task.get(key), str) or not task[key].strip():
                        raise OrchestratorError(f"{tid}: missing/empty {key}")
                for key in ("dependencies", "planned_outputs", "implementation_steps", "acceptance_criteria", "verification_profiles", "input_files"):
                    value = task.get(key)
                    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
                        raise OrchestratorError(f"{tid}: invalid {key}")
                if not task["acceptance_criteria"] or not task["implementation_steps"] or not task["verification_profiles"]:
                    raise OrchestratorError(f"{tid}: incomplete task/verification definition")
                if task["assigned_agent"] not in agent_ids:
                    raise OrchestratorError(f"{tid}: unknown agent {task['assigned_agent']}")
                if len(set(task["dependencies"])) != len(task["dependencies"]):
                    raise OrchestratorError(f"{tid}: duplicate dependencies")
                for profile in task["verification_profiles"]:
                    if profile not in data.get("verification_profiles", {}):
                        raise OrchestratorError(f"{tid}: unknown verification profile {profile}")
                if task["type"] == "human_gate" and not task.get("approver"):
                    raise OrchestratorError(f"{tid}: missing human approver")
                ordered.append((phase, milestone, task))
    if not ordered:
        raise OrchestratorError("Lifecycle has no tasks.")
    merged_sources = set()
    for _, _, task in ordered:
        if "merged_from" not in task:
            continue
        sources = task["merged_from"]
        if (not isinstance(sources, list) or len(sources) < 2
                or any(not isinstance(source, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", source) for source in sources)
                or sources[0] != task["id"] or len(set(sources)) != len(sources)):
            raise OrchestratorError(f"{task['id']}: malformed merged_from provenance")
        if task["type"] in {"human_gate", "phase_acceptance"} or merged_sources & set(sources) or (set(sources) - {task["id"]}) & seen:
            raise OrchestratorError(f"{task['id']}: consolidation overlaps executable tasks, another merge or an approval checkpoint")
        merged_sources.update(sources)
    pending = {t["id"]: set(t["dependencies"]) for _, _, t in ordered}
    for tid, deps in pending.items():
        if deps - seen:
            raise OrchestratorError(f"{tid}: nonexistent dependencies {sorted(deps - seen)}")
    done = set()
    while pending:
        ready = [tid for tid, deps in pending.items() if deps <= done]
        if not ready:
            raise OrchestratorError(f"Circular dependencies involving: {', '.join(pending)}")
        for tid in ready:
            done.add(tid)
            del pending[tid]
    for decision in data.get("human_decisions", []):
        if decision["gate_task_id"] not in seen:
            raise OrchestratorError(f"Unknown human decision task: {decision['gate_task_id']}")
    return ordered
