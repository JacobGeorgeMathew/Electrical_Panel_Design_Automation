"""Pure aggregation of declared evidence; no generation, database writes or approval.

The snapshot adapter reports the bounded checks saved by the prototype engines.
It retains C01–C09 obligations with missing evaluators as UNRESOLVED. It does not
reinterpret FINAL_VALIDATED or a wire preview PASS as engineering approval.
"""
from collections.abc import Sequence
from hashlib import sha256
import json

from app.models.cem import CanonicalEngineeringModel
from app.models.identity import finite_tree, unique_ids
from app.models.pdm import PhysicalDesignModel
from app.models.requirements import RequirementState
from app.models.validation import ValidationReport, ValidationResult, ValidationRule
from app.services.design_errors import DesignError
from app.services.netlist_engine import NetlistEngine


def aggregate_validation(
    *, project_id: str, panel_id: str, expected: Sequence[ValidationRule],
    results: Sequence[ValidationResult], revision_id: str | None = None,
    physical_evaluated: bool = False, physical_violation_count: int = 0,
    engineering_policy_review_reference: str | None = None,
) -> ValidationReport:
    """Match current observations to a caller-owned expected rule inventory.

    Missing and wrong-version evidence cannot disappear. Rule requiredness,
    severity and applicability come from the inventory, never an observation.
    Conflicting duplicates/unknown check IDs are rejected rather than averaged.
    """
    unique_ids((rule.id for rule in expected), 'validation.expected')
    unique_ids((result.rule.id for result in results), 'validation.results')
    inventory = {rule.id: rule for rule in expected}
    if any(result.rule.id not in inventory for result in results):
        raise ValueError('Validation result references a check outside the expected inventory.')
    observed = {result.rule.id: result for result in results}
    checks = []
    for rule in sorted(expected, key=lambda item: item.id):
        result = observed.get(rule.id)
        if result is None or result.rule != rule:
            # An explicitly excluded expected scope still needs current evidence.
            unresolved_rule = rule.model_copy(update={'applicability': 'UNKNOWN'}) if (
                rule.applicability == 'NOT_APPLICABLE') else rule
            checks.append(ValidationResult(rule=unresolved_rule,
                status='FAIL' if result and result.status == 'FAIL' else 'UNRESOLVED', current=False,
                message='Expected evaluation is missing or its rule version/scope differs.',
                evidence=result.evidence if result else ()))
        else:
            checks.append(result)
    return ValidationReport(project_id=project_id, panel_id=panel_id, revision_id=revision_id,
        checks=tuple(checks), physical_evaluated=physical_evaluated,
        physical_violation_count=physical_violation_count,
        engineering_policy_review_reference=engineering_policy_review_reference)


def build_validation_report(
    cem: CanonicalEngineeringModel, pdm: PhysicalDesignModel, *,
    revision_id: str | None = None, physical_evaluated: bool = False,
    current: bool = True, rule_versions: dict[str, str] | None = None,
) -> ValidationReport:
    """Read a verified saved snapshot without modifying or re-evaluating it.

    physical_evaluated must be supplied by a trusted caller that has evidence of
    physical evaluation. Empty default lists alone do not prove that it ran.
    No review argument is exposed: qualified applicability is still deferred.
    """
    finite_tree(cem)
    finite_tree(pdm)
    if (cem.project_id, cem.panel_id) != (pdm.project_id, pdm.panel_id):
        raise DesignError('VALIDATION_IDENTITY_MISMATCH', 'Validation snapshots have different owners.')
    versions = rule_versions or {}
    results = []

    def add(rule_id, domain, object_id, object_kind, status, message, *, version=None,
            severity='CRITICAL', applicability='APPLICABLE', rationale=None,
            evidence=(), actual=None, required=None, unit=None, discriminator='', purpose='ENGINEERING',
            evidence_current=True):
        key = json.dumps([domain, object_kind, object_id, rule_id, discriminator], separators=(',', ':'))
        rule = ValidationRule(id='CHECK-'+sha256(key.encode()).hexdigest(), object_id=object_id,
            object_kind=object_kind, domain=domain, rule_id=rule_id,
            rule_version=version or versions.get(rule_id, 'prototype-validation/1'),
            severity=severity, applicability=applicability, applicability_rationale=rationale, purpose=purpose)
        results.append(ValidationResult(rule=rule, status=status, message=message, current=current and evidence_current,
            evidence=tuple(evidence), actual_value=actual, required_value=required, unit=unit))

    # The academic-scope inventory is deliberately present even when objects or
    # evaluators are absent. It supplies no qualified method/applicability approval.
    for family, domain, message in (
        ('C01', 'ELECTRICAL', 'Complete identity/projection and lineage evaluation is not recorded.'),
        ('C02', 'ELECTRICAL', 'Supply domains, device boundaries and expected feeder paths need reviewed evidence.'),
        ('C03', 'ELECTRICAL', 'Conductor selection and shared termination capacity need reviewed evidence.'),
        ('C04', 'GEOMETRY', 'Engineering envelopes and bend applicability need reviewed cable/method evidence.'),
        ('C05', 'ELECTRICAL', 'Duct fill and segregation engineering applicability remain unreviewed.'),
        ('C06', 'ELECTRICAL', 'Assembly bonding inventory and actual cabinet earth terminals remain unresolved.'),
        ('C07', 'PHYSICAL', 'Saved prototype physical limits have no qualified applicability approval.'),
        ('C08', 'THERMAL_SCREEN', 'Protection, sizing and thermal methods require independent engineering review.'),
        ('C09', 'ELECTRICAL', 'Complete engineering evidence/output compatibility review is not recorded.'),
    ):
        # Applicability of these engineering families is unknown until review;
        # they must not prevent a bounded geometry preview being described.
        add(family, domain, cem.panel_id, 'PANEL', 'UNRESOLVED', message,
            version='academic-db-inventory/1', applicability='UNKNOWN')

    if not cem.requirements:
        add('REQUIREMENTS', 'REQUIREMENT', cem.panel_id, 'PANEL', 'UNRESOLVED', 'No requirements evaluation is recorded.')
    for item in cem.requirements:
        status = 'FAIL' if item.state == RequirementState.CONFLICTING else (
            'PASS' if item.state == RequirementState.VALIDATED else 'UNRESOLVED')
        add('REQUIREMENT_STATE', 'REQUIREMENT', item.id, 'REQUIREMENT', status,
            item.message or f'Requirement state is {item.state.value}; assumed/confirmed values are not engineering validation.')
    for calculation in cem.calculations:
        add('CALCULATION_METHOD', 'ELECTRICAL', calculation.id, 'CALCULATION',
            'FAIL' if calculation.status == 'FAIL' else 'UNRESOLVED',
            'Prototype calculation; method and reference values have no qualified approval.',
            actual=calculation.value, unit=calculation.unit, evidence=(calculation.status,))
    for constraint in cem.constraints:
        add(constraint.id, 'ELECTRICAL', cem.panel_id, 'PANEL', 'PASS' if constraint.passed else 'FAIL',
            constraint.name, severity=constraint.severity, actual=constraint.actual_value,
            required=constraint.limit_value, unit=constraint.unit)
    for item in cem.compliance:
        add(item.rule_id, 'ELECTRICAL', cem.panel_id, 'PANEL', 'PASS' if item.passed else 'FAIL',
            item.details or item.rule_name, discriminator='compliance')

    _, identity_errors = NetlistEngine().validate_netlist(cem.nets, cem.components)
    collections = (cem.components, cem.connections, pdm.components, pdm.routes)
    if any(len({item.id for item in items}) != len(items) for items in collections):
        identity_errors.append('Duplicate object identities.')
    if cem.connections != [connection for net in cem.nets for connection in net.connections]:
        identity_errors.append('Flat and nested CEM connections differ.')
    if {item.id for item in cem.components} != {item.cem_component_id for item in pdm.components}:
        identity_errors.append('CEM and PDM component references differ.')
    connections = {connection.id: connection for connection in cem.connections}
    if {route.conductor_id for route in pdm.routes} != set(connections) or len(pdm.routes) != len(connections):
        identity_errors.append('Route-to-conductor inventory differs.')
    for route in pdm.routes:
        connection = connections.get(route.conductor_id)
        if connection and any(getattr(route, field) != getattr(connection, field) for field in (
            'net_id', 'from_component', 'from_terminal', 'to_component', 'to_terminal', 'wire_class')):
            identity_errors.append(f'Route {route.id} differs from its conductor endpoints/net/class.')
    add('SNAPSHOT_REFERENCES', 'ELECTRICAL', cem.panel_id, 'PANEL',
        'FAIL' if identity_errors else 'PASS' if cem.components and cem.connections else 'UNRESOLVED',
        '; '.join(identity_errors) or 'Bounded CEM/PDM reference checks; complete engineering scope remains unresolved.')

    physical = [v for v in pdm.validation_results if v.type != 'THERMAL']
    add('PHYSICAL_FEASIBILITY', 'PHYSICAL', pdm.id, 'PDM',
        'FAIL' if physical else 'PASS' if physical_evaluated else 'UNRESOLVED',
        'Saved physical evaluation under the prototype policy; warnings also block generation.',
        version=pdm.validation_policy.version, purpose='PROTOTYPE')
    for index, violation in enumerate(pdm.validation_results):
        add(violation.type, 'THERMAL_SCREEN' if violation.type == 'THERMAL' else 'PHYSICAL',
            violation.object_a, 'PHYSICAL_OBJECT', 'FAIL', violation.message,
            version=versions.get(violation.type, pdm.validation_policy.version),
            severity=violation.severity, evidence=(violation.object_b,) if violation.object_b else (),
            actual=violation.actual_value, required=violation.required_value,
            unit=violation.unit, discriminator=str(index), purpose='PROTOTYPE')
    # Same density screen as ValidationEngine, explicitly not temperature-rise evidence.
    density = pdm.total_heat_loss_watts / max(1.0, pdm.enclosure_width * pdm.enclosure_height * pdm.enclosure_depth / 1_000_000)
    add('THERMAL_DENSITY_SCREEN', 'THERMAL_SCREEN', pdm.enclosure_id, 'ENCLOSURE',
        'FAIL' if density > pdm.validation_policy.thermal_density_limit_w_per_l + 1e-9 else (
            'PASS' if physical_evaluated else 'UNRESOLVED'),
        'Prototype heat-density screen only; not a temperature-rise or standards assessment.',
        version=pdm.validation_policy.version, actual=density,
        required=pdm.validation_policy.thermal_density_limit_w_per_l, unit='W/L', purpose='PROTOTYPE')

    connection_ids = {connection.id for connection in cem.connections}
    for route in pdm.routes:
        geometry = route.geometry
        geometry_matches = geometry is not None and geometry.route_id == route.id
        add('GEOMETRY_PREVIEW', 'GEOMETRY', route.id, 'ROUTE',
            'FAIL' if geometry and (not geometry_matches or geometry.status == 'FAIL') else (
                'PASS' if geometry_matches and geometry.status == 'PASS' else 'UNRESOLVED'),
            'Saved sampled envelope preview; engineering subchecks remain separate.',
            version=geometry.backend if geometry else 'missing-geometry/1', purpose='PROTOTYPE')
        add('CONDUCTOR_REFERENCE', 'ELECTRICAL', route.id, 'ROUTE',
            'PASS' if route.conductor_id in connection_ids else 'UNRESOLVED',
            'Route conductor reference must identify an existing CEM connection.')
        raw_checks = list(route.validation_checks)
        for check in geometry.checks if geometry else ():
            if check not in raw_checks:
                raw_checks.append(check)
        by_type = {}
        for index, check in enumerate(raw_checks):
            by_type.setdefault(check.get('type') or f'UNKNOWN_CHECK_{index}', []).append(check)
        expected_types = {'SWEPT_COMPONENT_BOUNDARY', 'MANUFACTURER_BEND_RADIUS',
                          'WIRE_SEPARATION', 'CONDUCTOR_DIMENSIONS'}
        if 'PANEL_ROOT' in {route.from_component, route.to_component}:
            expected_types.add('CABINET_EARTH_TERMINAL')
        for kind in sorted(expected_types | by_type.keys()):
            checks = by_type.get(kind, [])
            statuses = {check.get('status') for check in checks}
            check_versions = {check.get('rule_version', geometry.backend if geometry else 'missing-geometry/1')
                              for check in checks}
            unknown_applicability = any(check.get('applicability') == 'UNKNOWN' for check in checks)
            rationale = checks[0].get('applicability_rationale') if checks else None
            status = 'FAIL' if 'FAIL' in statuses or len(statuses) > 1 else (
                next(iter(statuses)) if statuses else 'UNRESOLVED')
            if status not in {'PASS', 'FAIL', 'UNRESOLVED', 'NOT_APPLICABLE'} or (
                status == 'NOT_APPLICABLE' and not (isinstance(rationale, str) and rationale.strip())
            ):
                status = 'UNRESOLVED'
            if status != 'FAIL' and (unknown_applicability or len(check_versions) > 1):
                status = 'UNRESOLVED'
            add(kind, 'GEOMETRY' if kind == 'SWEPT_COMPONENT_BOUNDARY' else 'ELECTRICAL',
                route.id, 'ROUTE', status,
                '; '.join(str(check.get('message', '')) for check in checks) or 'Expected route evaluation is missing.',
                version=next(iter(check_versions)) if len(check_versions) == 1 else (
                    geometry.backend if geometry else 'missing-geometry/1'),
                severity=next((level for level in ('CRITICAL', 'WARNING', 'INFO') if any(
                    check.get('severity', 'CRITICAL') == level for check in checks)), 'CRITICAL'),
                applicability='UNKNOWN' if unknown_applicability else (
                    'NOT_APPLICABLE' if status == 'NOT_APPLICABLE' else 'APPLICABLE'),
                rationale=rationale, evidence=tuple(str(check['id']) for check in checks if check.get('id')),
                purpose='PROTOTYPE' if kind == 'SWEPT_COMPONENT_BOUNDARY' else 'ENGINEERING',
                evidence_current=all(check.get('current', True) is True for check in checks))
    if not pdm.routes:
        add('GEOMETRY_PREVIEW', 'GEOMETRY', pdm.id, 'PDM', 'UNRESOLVED',
            'No route geometry inventory is recorded; absence does not prove inapplicability.', purpose='PROTOTYPE')

    return aggregate_validation(project_id=cem.project_id, panel_id=cem.panel_id, revision_id=revision_id,
        expected=[result.rule for result in results], results=results,
        physical_evaluated=physical_evaluated, physical_violation_count=len(pdm.validation_results))
