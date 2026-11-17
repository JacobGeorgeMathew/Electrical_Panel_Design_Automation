"""Software aggregation evidence, not independent electrical method approval."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import get_service, get_session
from app.main import create_app
from app.models.cem import CanonicalEngineeringModel
from app.models.pdm import PhysicalDesignModel, ValidationViolation
from app.models.validation import ValidationReport, ValidationResult, ValidationRule
from app.services.design_errors import DesignError
from app.services.validation_report import aggregate_validation, build_validation_report
from tests.design_baseline_support import CASES, engine


def observation(id='check-1', status='PASS', **changes):
    rule = dict(id=id, object_id='route-1', object_kind='ROUTE', domain='GEOMETRY',
                purpose='PROTOTYPE', rule_id='ENVELOPE', rule_version='fixture/1')
    rule.update(changes)
    return ValidationResult(rule=ValidationRule(**rule), status=status, message='Synthetic fixture only.')


def aggregate(results, **kwargs):
    return aggregate_validation(project_id='project-1', panel_id='panel-1',
        expected=kwargs.pop('expected', [result.rule for result in results]), results=results,
        physical_evaluated=True, engineering_policy_review_reference=kwargs.pop('review', 'synthetic-policy-review'),
        **kwargs)


@pytest.mark.parametrize('statuses,expected', [
    (['PASS', 'PASS'], 'PASS'), (['PASS', 'FAIL', 'UNRESOLVED'], 'FAIL'),
    (['PASS', 'UNRESOLVED'], 'UNRESOLVED'),
    (['PASS', 'NOT_APPLICABLE'], 'PASS'), (['NOT_APPLICABLE'], 'NOT_APPLICABLE'),
    ([], 'UNRESOLVED'),
])
def test_required_aggregation_matrix(statuses, expected):
    results = [observation(str(index), status,
        **({'applicability': 'NOT_APPLICABLE', 'applicability_rationale': 'Synthetic reviewed scope exclusion.'}
           if status == 'NOT_APPLICABLE' else {})) for index, status in enumerate(statuses)]
    report = aggregate(results)
    assert report.required_status == expected
    assert report.engineering_release_eligible == (expected in {'PASS', 'NOT_APPLICABLE'})


@pytest.mark.parametrize('severity', ['CRITICAL', 'WARNING', 'INFO'])
@pytest.mark.parametrize('status', ['FAIL', 'UNRESOLVED'])
def test_required_fail_or_unresolved_blocks_at_every_severity(status, severity):
    report = aggregate([observation(), observation('engineering', status, domain='ELECTRICAL',
                       purpose='ENGINEERING', severity=severity)])
    assert report.geometric_feasible and report.prototype_preview_available
    assert not report.engineering_release_eligible
    assert 'engineering' in report.blocking_check_ids


def test_missing_stale_unapproved_optional_and_physical_warning_matrix():
    result = observation()
    missing = aggregate([result], expected=[result.rule, observation('missing').rule])
    assert missing.required_status == 'UNRESOLVED' and len(missing.checks) == 2
    stale = aggregate([result.model_copy(update={'current': False})])
    assert stale.required_status == 'UNRESOLVED' and not stale.engineering_release_eligible
    assert aggregate([observation(applicability='UNKNOWN', status='UNRESOLVED')]).required_status == 'UNRESOLVED'
    unapproved = aggregate([result], review=None)
    assert unapproved.required_status == 'PASS' and unapproved.engineering_status == 'UNRESOLVED'
    assert not unapproved.engineering_release_eligible
    optional = aggregate([result, observation('optional', 'FAIL', required=False, domain='ELECTRICAL')])
    assert optional.required_status == 'PASS' and optional.engineering_release_eligible
    assert optional.checks[1].status == 'FAIL'
    assert any(group.status == 'FAIL' and group.check_ids == ('optional',) for group in optional.groups)
    warning = aggregate([result], physical_violation_count=1)
    assert warning.required_status == 'PASS' and not warning.physical_generation_eligible
    assert not warning.engineering_release_eligible and not warning.prototype_preview_available


@pytest.mark.parametrize('rationale', [None, '', '  '])
def test_not_applicable_requires_nonblank_rationale(rationale):
    with pytest.raises(ValidationError, match='rationale'):
        observation(status='NOT_APPLICABLE', applicability='NOT_APPLICABLE', applicability_rationale=rationale)


def test_false_na_unknown_applicability_and_units_are_rejected():
    with pytest.raises(ValidationError):
        observation(status='NOT_APPLICABLE')
    with pytest.raises(ValidationError):
        observation(applicability='UNKNOWN')
    with pytest.raises(ValidationError, match='unit'):
        ValidationResult(rule=observation().rule, status='PASS', message='Missing units', actual_value=1)
    for value in (float('inf'), float('nan'), 'nan'):
        with pytest.raises(ValidationError):
            ValidationResult(rule=observation().rule, status='PASS', message='Nonfinite', actual_value=value, unit='mm')


def test_rule_version_requiredness_and_applicability_cannot_be_downgraded():
    expected = observation().rule
    for changes in ({'rule_version': 'old'}, {'required': False}, {'severity': 'INFO'},
                    {'applicability': 'NOT_APPLICABLE', 'applicability_rationale': 'Untrusted exclusion'}):
        status = 'NOT_APPLICABLE' if 'applicability' in changes else 'PASS'
        report = aggregate([observation(status=status, **changes)], expected=[expected])
        assert report.required_status == 'UNRESOLVED' and not report.engineering_release_eligible
        assert report.checks[0].rule == expected
    report = aggregate([observation(status='FAIL', rule_version='old')], expected=[expected])
    assert report.required_status == 'FAIL'
    with pytest.raises(ValueError):
        aggregate([observation('extra')], expected=[expected])
    with pytest.raises(ValueError, match='Duplicate ID'):
        aggregate([observation(), observation()])


def test_missing_exclusion_evidence_stays_unresolved():
    rule = observation(status='NOT_APPLICABLE', applicability='NOT_APPLICABLE',
                       applicability_rationale='Synthetic scope exclusion').rule
    report = aggregate([], expected=[rule])
    assert report.required_status == 'UNRESOLVED'
    assert report.checks[0].rule.applicability == 'UNKNOWN'


@pytest.fixture(scope='module')
def package():
    return engine(CASES['feasible'][0]).generate_design(CASES['feasible'][0]['project_id'], persist_requirements=False)


def snapshot_report(package, **kwargs):
    return build_validation_report(CanonicalEngineeringModel.model_validate(package['cem']),
        PhysicalDesignModel.model_validate(package['pdm']), physical_evaluated=True, **kwargs)


def test_preview_pass_never_masks_route_engineering_obligations_or_mutates_snapshot(package):
    original = deepcopy(package)
    report = snapshot_report(package)
    assert report.geometric_feasible and report.prototype_preview_available
    assert report.physical_generation_eligible and not report.engineering_release_eligible
    assert report.required_status == 'UNRESOLVED'
    for kind in ('MANUFACTURER_BEND_RADIUS', 'WIRE_SEPARATION', 'CONDUCTOR_DIMENSIONS', 'CABINET_EARTH_TERMINAL'):
        checks = [result for result in report.checks if result.rule.rule_id == kind]
        assert checks and all(result.status == 'UNRESOLVED' for result in checks)
    assert {f'C{index:02d}' for index in range(1, 10)} <= {result.rule.rule_id for result in report.checks}
    assert set(result.rule.domain for result in report.checks) == {
        'REQUIREMENT', 'ELECTRICAL', 'PHYSICAL', 'THERMAL_SCREEN', 'GEOMETRY'}
    assert package == original
    assert not snapshot_report(package, current=False).engineering_release_eligible


def test_absent_checks_and_unjustified_na_are_not_pass(package):
    changed = deepcopy(package)
    route = changed['pdm']['routes'][0]
    route['validation_checks'] = []
    route['geometry']['checks'] = [dict(type='MANUFACTURER_BEND_RADIUS', status='NOT_APPLICABLE', message='Straight line')]
    report = snapshot_report(changed)
    kinds = {result.rule.rule_id: result.status for result in report.checks if result.rule.object_id == route['id']}
    for kind in ('MANUFACTURER_BEND_RADIUS', 'WIRE_SEPARATION', 'CONDUCTOR_DIMENSIONS', 'SWEPT_COMPONENT_BOUNDARY'):
        assert kinds[kind] == 'UNRESOLVED'
    assert not report.engineering_release_eligible


def test_conflicting_route_observations_fail_and_cannot_be_hidden_by_preview(package):
    changed = deepcopy(package)
    route = changed['pdm']['routes'][0]
    route['validation_checks'].append(dict(type='WIRE_SEPARATION', status='FAIL', message='Known conflict.'))
    report = snapshot_report(changed)
    assert report.required_status == 'FAIL'
    assert report.prototype_preview_available and not report.engineering_release_eligible


def test_saved_route_version_severity_unknown_applicability_and_freshness_are_retained(package):
    changed = deepcopy(package)
    route = changed['pdm']['routes'][0]
    metadata = dict(rule_version='saved-bend-rule/2', severity='WARNING', current=False,
                    applicability='UNKNOWN', status='PASS')
    for checks in (route['validation_checks'], route['geometry']['checks']):
        next(check for check in checks if check['type'] == 'MANUFACTURER_BEND_RADIUS').update(metadata)
    report = snapshot_report(changed)
    check = next(check for check in report.checks if check.rule.object_id == route['id']
                 and check.rule.rule_id == 'MANUFACTURER_BEND_RADIUS')
    assert check.rule.rule_version == 'saved-bend-rule/2'
    assert check.rule.severity == 'WARNING' and check.rule.applicability == 'UNKNOWN'
    assert check.status == 'UNRESOLVED' and not check.current
    assert not report.engineering_release_eligible


def test_grouping_preserves_object_version_severity_and_applicability():
    results = [observation('a'), observation('b', object_id='route-2'),
               observation('c', rule_version='fixture/2'), observation('d', severity='WARNING'),
               observation('e', status='UNRESOLVED', applicability='UNKNOWN')]
    report = aggregate(results)
    assert len(report.groups) == 5
    assert {id for group in report.groups for id in group.check_ids} == {result.rule.id for result in results}
    assert aggregate(list(reversed(results))).model_dump() == report.model_dump()


def test_physical_warning_thermal_failure_and_bad_references_remain_blocking(package):
    changed = deepcopy(package)
    changed['pdm']['validation_results'].append(ValidationViolation(type='DUCT_CAPACITY', severity='WARNING',
        object_a='DUCT-1', required_value=40, actual_value=41, unit='%', message='Prototype limit exceeded.').model_dump())
    report = snapshot_report(changed)
    assert not report.physical_generation_eligible and not report.prototype_preview_available
    assert report.required_status == 'FAIL'
    changed = deepcopy(package)
    changed['pdm']['total_heat_loss_watts'] = 1e9
    report = snapshot_report(changed)
    assert any(check.rule.rule_id == 'THERMAL_DENSITY_SCREEN' and check.status == 'FAIL' for check in report.checks)
    assert not report.physical_generation_eligible and not report.prototype_preview_available
    assert not report.engineering_release_eligible
    changed = deepcopy(package)
    changed['pdm']['routes'][0]['net_id'] = 'absent-net'
    assert snapshot_report(changed).required_status == 'FAIL'
    changed['pdm']['panel_id'] = 'different-panel'
    with pytest.raises(DesignError, match='different owners'):
        snapshot_report(changed)


def test_no_evaluation_or_empty_model_is_not_vacuously_eligible(package):
    report = build_validation_report(CanonicalEngineeringModel.model_validate(package['cem']),
                                    PhysicalDesignModel.model_validate(package['pdm']))
    assert not report.physical_generation_eligible and not report.prototype_preview_available
    cem = CanonicalEngineeringModel(project_id='p', panel_id='panel')
    pdm = PhysicalDesignModel(id='pdm', project_id='p', panel_id='panel', enclosure_id='enc',
        enclosure_width=100, enclosure_height=100, enclosure_depth=100, ip_rating='IP54')
    report = build_validation_report(cem, pdm, physical_evaluated=True)
    assert report.required_status == 'UNRESOLVED' and not report.prototype_preview_available


def test_shared_typescript_fixture_roundtrip_and_derived_fields():
    path = Path(__file__).resolve().parents[2] / 'frontend/src/types/fixtures/validation-report-v1.json'
    fixture = json.loads(path.read_text())
    report = ValidationReport.model_validate(fixture)
    assert report.model_dump(mode='json') == fixture
    assert ValidationReport.model_validate_json(report.model_dump_json()) == report
    fixture.update(engineering_release_eligible=True, engineering_status='PASS', blocking_check_ids=[])
    report = ValidationReport.model_validate(fixture)
    assert not report.engineering_release_eligible and report.engineering_status == 'UNRESOLVED'
    assert report.blocking_check_ids == ('check-bend',)


def test_validation_endpoint_openapi_and_read_only_saved_results(package):
    design = deepcopy(package)
    design.update(revision_id='11111111-1111-1111-1111-111111111111',
                  manifest={}, output_status='COMPLETE', is_stale=False)
    original = deepcopy(design)
    app = create_app()
    app.dependency_overrides[get_service] = lambda: SimpleNamespace(load_revision=lambda key: design)

    class Session:
        def execute(self, query):
            return SimpleNamespace(mappings=lambda: iter([{'status': 'PASS', 'legacy': True}]))

    app.dependency_overrides[get_session] = lambda: Session()
    response = TestClient(app).get('/api/projects/project-1/validation')
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['violations'] == design['validation_errors']
    assert body['results'] == [{'status': 'PASS', 'legacy': True}]
    assert body['aggregate']['prototype_preview_available']
    assert not body['aggregate']['engineering_release_eligible']
    assert design == original
    schema = app.openapi()['components']['schemas']
    assert schema['ProjectValidationResponse']['properties']['aggregate']['$ref'].endswith('/ValidationReport')
    assert schema['ValidationRule']['properties']['applicability']['enum'] == ['APPLICABLE', 'UNKNOWN', 'NOT_APPLICABLE']
    assert schema['ValidationResult']['additionalProperties'] is False
