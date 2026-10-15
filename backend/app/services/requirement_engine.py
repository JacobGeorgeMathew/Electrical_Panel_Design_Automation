import json
import os
from typing import Any, Dict, List, Tuple
from app.models.requirements import (
    DependencyRule,
    QuestionSchema,
    RequirementItem,
    RequirementSet,
    RequirementState,
)


class RequirementEngine:
    def __init__(self, templates_path: str = None):
        if templates_path is None:
            templates_path = os.path.join(os.path.dirname(__file__), "..", "data", "panel_templates.json")
        self.templates_path = templates_path
        self._load_templates()

    def _load_templates(self):
        if os.path.exists(self.templates_path):
            with open(self.templates_path, "r", encoding="utf-8") as f:
                self._templates = {t["archetype"]: t for t in json.load(f)}
        else:
            self._templates = {}

    def get_template(self, archetype: str = "DB") -> Dict[str, Any]:
        template = self._templates.get(archetype)
        if template is None:
            from app.services.design_errors import DesignError
            raise DesignError("UNSUPPORTED_ARCHETYPE", f"No requirement template is configured for '{archetype}'.",
                              {"archetype": archetype, "supported": sorted(self._templates)})
        return template

    def get_questions(self, archetype: str = "DB") -> List[QuestionSchema]:
        tmpl = self.get_template(archetype)
        questions_raw = tmpl.get("questions", [])
        return [QuestionSchema(**q) for q in questions_raw]

    def evaluate_dependencies(self, questions: List[QuestionSchema], current_values: Dict[str, Any]) -> List[QuestionSchema]:
        visible_questions = []
        for q in questions:
            if not q.depends_on:
                visible_questions.append(q)
                continue

            visible = True
            for dep in q.depends_on:
                current_val = current_values.get(dep.field)
                if dep.operator == "equals" and current_val != dep.value:
                    visible = False
                    break
                elif dep.operator == "greater_than" and (current_val is None or current_val <= dep.value):
                    visible = False
                    break
                elif dep.operator == "less_than" and (current_val is None or current_val >= dep.value):
                    visible = False
                    break
                elif dep.operator == "in" and current_val not in dep.value:
                    visible = False
                    break

            if visible:
                visible_questions.append(q)
        return visible_questions

    def validate_requirements(self, project_id: str, archetype: str, values: Dict[str, Any]) -> RequirementSet:
        questions = self.get_questions(archetype)
        items = []
        errors = []
        warnings = []

        visible_questions = self.evaluate_dependencies(questions, values)
        visible_ids = {q.id for q in visible_questions}

        known_ids = {q.id for q in questions}
        for unknown in sorted(set(values) - known_ids):
            errors.append(f"Unknown requirement field '{unknown}'.")

        for q in questions:
            if q.id not in visible_ids:
                items.append(RequirementItem(
                    id=q.id,
                    label=q.label,
                    value=None,
                    unit=q.unit,
                    state=RequirementState.ASSUMED,
                    source="SYSTEM",
                    message="Not applicable for current selection"
                ))
                continue

            val = values.get(q.id, q.default)
            state = RequirementState.CONFIRMED if q.id in values else RequirementState.ASSUMED

            # Check required
            if q.required and val is None:
                errors.append(f"Field '{q.label}' ({q.id}) is required.")
                state = RequirementState.MISSING

            # Validate the questionnaire's declared type and options before ranges.
            if val is not None:
                type_valid = {
                    "number": lambda x: isinstance(x, (int, float)) and not isinstance(x, bool),
                    "boolean": lambda x: isinstance(x, bool),
                    "select": lambda x: True,
                    "text": lambda x: isinstance(x, str),
                }.get(q.type, lambda x: True)(val)
                if not type_valid:
                    errors.append(f"'{q.label}' must be a {q.type} value.")
                    state = RequirementState.CONFLICTING
                elif q.options is not None and val not in q.options:
                    errors.append(f"'{q.label}' must be one of: {', '.join(map(str, q.options))}.")
                    state = RequirementState.CONFLICTING
                elif q.id in {"phases", "num_feeders", "frequency", "incomer_rating", "supply_voltage", "spare_capacity_pct"} and isinstance(val, float) and not val.is_integer():
                    errors.append(f"'{q.label}' must be a whole number.")
                    state = RequirementState.CONFLICTING

            # Check range validation only for correctly typed numeric values.
            if q.validation and val is not None and isinstance(val, (int, float)) and not isinstance(val, bool):
                if q.validation.min is not None and val < q.validation.min:
                    errors.append(f"'{q.label}' must be at least {q.validation.min} {q.unit or ''}.")
                    state = RequirementState.CONFLICTING
                if q.validation.max is not None and val > q.validation.max:
                    errors.append(f"'{q.label}' cannot exceed {q.validation.max} {q.unit or ''}.")
                    state = RequirementState.CONFLICTING

            items.append(RequirementItem(
                id=q.id,
                label=q.label,
                value=val,
                unit=q.unit,
                state=state if not errors or state != RequirementState.CONFLICTING else RequirementState.CONFLICTING,
                source="USER" if q.id in values else "DEFAULT"
            ))

        # Cross-field engineering checks
        incomer = values.get("incomer_rating", 250)
        feeders = values.get("num_feeders", 12)
        if isinstance(incomer, (int, float)) and isinstance(feeders, int) and incomer <= 100 and feeders > 16:
            warnings.append(f"Incomer rating {incomer}A may be undersized for {feeders} outgoing feeders.")

        if values.get("phases") == 1 and values.get("neutral_required") is True:
            warnings.append("Neutral bus bar is not applicable to the selected single-phase configuration.")

        is_valid = len(errors) == 0

        return RequirementSet(
            project_id=project_id,
            archetype=archetype,
            items=items,
            is_valid=is_valid,
            validation_errors=errors,
            validation_warnings=warnings
        )
