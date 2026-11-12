"""Markdown remains human-readable; a bounded JSON block supports reliable review."""
import hashlib
import json
import re
from .io_utils import confined
from .errors import OrchestratorError

HEADINGS = ["Task information", "Execution summary", "Implementation details", "Files modified",
            "Acceptance criteria and results", "Commands executed", "Test and build results",
            "Verification profiles executed", "Problems encountered", "Remaining work", "Recommendations",
            "Final execution assessment", "Git branch and commit information", "Uncommitted changes"]


class ReportManager:
    def __init__(self, root, directory):
        self.root, self.directory = root, directory

    def path(self, task_id, number):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", task_id) or number < 1:
            raise OrchestratorError("Unsafe report task ID or attempt number.")
        return confined(self.directory, f"{task_id}/attempt-{number:02d}.md")

    def prepare(self, task_id, number):
        path = self.path(task_id, number)
        if path.exists():
            raise OrchestratorError(f"Report already exists; it will not be overwritten: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def inspect(self, path, task, number):
        errors, result = [], {}
        try:
            path = confined(self.root, str(path.relative_to(self.root)))
            if path.stat().st_size > 8 * 1024 * 1024:
                raise OrchestratorError("Report exceeds 8 MiB.")
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError, ValueError, OrchestratorError) as exc:
            return {"errors": [f"Missing/unreadable report: {exc}"], "text": "", "assessment": None}
        headings = re.findall(r"^## (.+?)\s*$", text, re.M)
        for heading in HEADINGS:
            if heading not in headings:
                errors.append(f"Missing heading: {heading}")
            elif headings.count(heading) != 1:
                errors.append(f"Duplicate heading: {heading}")
            else:
                body = text.split(f"## {heading}", 1)[1].split("\n## ", 1)[0].strip()
                if not body:
                    errors.append(f"Empty section: {heading}")
        blocks = re.findall(r"^```orchestrator-result\s*\n(.*?)\n```", text, re.M | re.S)
        if len(blocks) != 1:
            errors.append("Expected exactly one orchestrator-result JSON block.")
        else:
            try:
                result = json.loads(blocks[0])
                if result["task_id"] != task["id"] or type(result["attempt"]) is not int or result["attempt"] != number:
                    errors.append("Report task/attempt does not match this execution.")
                if result["assessment"] not in {"COMPLETED", "PARTIALLY_COMPLETED", "FAILED"}:
                    errors.append("Invalid execution assessment.")
                criteria = result["acceptance_criteria"]
                profiles = result["verification_profiles"]
                if [c["index"] for c in criteria] != list(range(1, len(task["acceptance_criteria"]) + 1)):
                    errors.append("Acceptance criteria must cover every original criterion exactly once in order.")
                if sorted(v["id"] for v in profiles) != sorted(task["verification_profiles"]):
                    errors.append("Verification profiles must cover the original required profiles exactly once.")
                for item in criteria + profiles:
                    if item["result"] not in {"PASS", "FAIL", "NOT_RUN", "UNVERIFIED"} or not isinstance(item["evidence"], str) or not item["evidence"].strip():
                        errors.append("Every criterion/profile needs an explicit result and evidence.")
                if any(type(c["index"]) is not int for c in criteria):
                    errors.append("Criterion indexes must be integers.")
            except (ValueError, KeyError, TypeError) as exc:
                errors.append(f"Malformed result block: {exc}")
                result = {}
        return {"errors": errors, "result": result, "assessment": result.get("assessment"),
                "text": text, "sha256": hashlib.sha256(raw).hexdigest()}

    @staticmethod
    def result_template(task, number):
        return {"task_id": task["id"], "attempt": number, "assessment": "PARTIALLY_COMPLETED",
                "acceptance_criteria": [{"index": i, "result": "UNVERIFIED", "evidence": "Describe evidence or why verification was unavailable."}
                                        for i in range(1, len(task["acceptance_criteria"]) + 1)],
                "verification_profiles": [{"id": p, "result": "NOT_RUN", "evidence": "Record commands, outcomes and evidence."}
                                          for p in task["verification_profiles"]]}
