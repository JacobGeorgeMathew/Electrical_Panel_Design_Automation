"""Versioned validation evidence; prototype feasibility is not release approval."""
from typing import Any, Literal

from pydantic import ConfigDict, Field, model_validator

from app.models.identity import ContractModel, StableID, unique_ids
from app.models.pdm import ValidationViolation


Status = Literal['PASS', 'FAIL', 'UNRESOLVED', 'NOT_APPLICABLE']
Applicability = Literal['APPLICABLE', 'UNKNOWN', 'NOT_APPLICABLE']
Domain = Literal['REQUIREMENT', 'ELECTRICAL', 'PHYSICAL', 'THERMAL_SCREEN', 'GEOMETRY']
Severity = Literal['CRITICAL', 'WARNING', 'INFO']


class ValidationRule(ContractModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, frozen=True)

    id: StableID
    object_id: StableID
    object_kind: StableID
    domain: Domain
    purpose: Literal['PROTOTYPE', 'ENGINEERING'] = 'ENGINEERING'
    rule_id: StableID
    rule_version: StableID
    severity: Severity = 'CRITICAL'
    required: bool = True
    applicability: Applicability = 'APPLICABLE'
    applicability_rationale: str | None = None

    @model_validator(mode='after')
    def justified_exclusion(self):
        if self.applicability == 'NOT_APPLICABLE' and not (
            self.applicability_rationale and self.applicability_rationale.strip()
        ):
            raise ValueError('NOT_APPLICABLE requires a recorded rationale.')
        return self


class ValidationResult(ContractModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, frozen=True)

    rule: ValidationRule
    status: Status
    message: str = Field(min_length=1)
    evidence: tuple[StableID, ...] = ()
    current: bool = True
    actual_value: float | None = None
    required_value: float | None = None
    unit: StableID | None = None

    @model_validator(mode='after')
    def consistent_result(self):
        if (self.status == 'NOT_APPLICABLE') != (self.rule.applicability == 'NOT_APPLICABLE'):
            raise ValueError('NOT_APPLICABLE status and applicability must agree.')
        if self.rule.applicability == 'UNKNOWN' and self.status == 'PASS':
            raise ValueError('Unknown applicability cannot PASS.')
        if (self.actual_value is not None or self.required_value is not None) and self.unit is None:
            raise ValueError('Numeric validation evidence requires an explicit unit.')
        return self


def required_status(results: tuple[ValidationResult, ...], *, required_only: bool = True) -> Status:
    """Requiredness is independent of severity; optional failures stay visible."""
    required = tuple(result for result in results if result.rule.required or not required_only)
    if any(result.status == 'FAIL' for result in required):
        return 'FAIL'
    if not required or any(
        result.status == 'UNRESOLVED' or not result.current
        or result.rule.applicability == 'UNKNOWN' for result in required
    ):
        return 'UNRESOLVED'
    return 'PASS' if any(result.status == 'PASS' for result in required) else 'NOT_APPLICABLE'


class ValidationGroup(ContractModel):
    object_id: StableID
    object_kind: StableID
    domain: Domain
    rule_id: StableID
    rule_version: StableID
    severity: Severity
    applicability: Applicability
    check_ids: tuple[StableID, ...]
    status: Status


class ValidationReport(ContractModel):
    """Derived fields are recalculated on deserialization, never accepted as authority."""
    schema_version: Literal['aggregate-validation/1'] = 'aggregate-validation/1'
    project_id: StableID
    panel_id: StableID
    revision_id: StableID | None = None
    checks: tuple[ValidationResult, ...]
    physical_evaluated: bool = False
    physical_violation_count: int = Field(default=0, ge=0)
    # Only a trusted caller with independently recorded review may supply this.
    # The runtime snapshot adapter deliberately supplies no such approval.
    engineering_policy_review_reference: StableID | None = None
    groups: tuple[ValidationGroup, ...] = ()
    required_status: Status = 'UNRESOLVED'
    engineering_status: Status = 'UNRESOLVED'
    geometric_feasible: bool = False
    physical_generation_eligible: bool = False
    prototype_preview_available: bool = False
    engineering_release_eligible: bool = False
    blocking_check_ids: tuple[StableID, ...] = ()

    @model_validator(mode='after')
    def derive_outcomes(self):
        unique_ids((result.rule.id for result in self.checks), 'validation.checks')
        self.required_status = required_status(self.checks)
        self.engineering_status = self.required_status
        if self.engineering_status != 'FAIL' and self.engineering_policy_review_reference is None:
            self.engineering_status = 'UNRESOLVED'
        self.blocking_check_ids = tuple(result.rule.id for result in self.checks if result.rule.required and (
            result.status in {'FAIL', 'UNRESOLVED'} or not result.current
            or result.rule.applicability == 'UNKNOWN'))
        geometric = tuple(result for result in self.checks if result.rule.purpose == 'PROTOTYPE'
                          and result.rule.domain in {'GEOMETRY', 'PHYSICAL'})
        self.geometric_feasible = self.physical_evaluated and required_status(geometric) in {'PASS', 'NOT_APPLICABLE'}
        prototype = tuple(result for result in self.checks if result.rule.purpose == 'PROTOTYPE')
        self.physical_generation_eligible = (self.physical_evaluated and self.physical_violation_count == 0
            and required_status(prototype) in {'PASS', 'NOT_APPLICABLE'})
        self.prototype_preview_available = self.geometric_feasible and self.physical_generation_eligible
        self.engineering_release_eligible = (
            self.prototype_preview_available and self.engineering_status in {'PASS', 'NOT_APPLICABLE'})
        grouped = {}
        for result in self.checks:
            rule = result.rule
            key = (rule.object_id, rule.object_kind, rule.domain, rule.rule_id, rule.rule_version,
                   rule.severity, rule.applicability)
            grouped.setdefault(key, []).append(result)
        fields = ('object_id', 'object_kind', 'domain', 'rule_id', 'rule_version', 'severity', 'applicability')
        self.groups = tuple(ValidationGroup(**dict(zip(fields, key)),
            check_ids=tuple(result.rule.id for result in results),
            status=required_status(tuple(results), required_only=False))
            for key, results in sorted(grouped.items()))
        return self


class ProjectValidationResponse(ContractModel):
    project_id: StableID
    revision_id: StableID
    violations: list[ValidationViolation]
    results: list[dict[str, Any]]
    thermal_density_index: float
    total_heat_loss_watts: float
    aggregate: ValidationReport
