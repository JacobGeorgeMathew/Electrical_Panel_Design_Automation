"""Independent DB MVP path; rejected publication is never a successful release."""
import json
from uuid import uuid4

import pytest

from app.models.document_api import DocumentSave
from app.models.operations import HistoryRequest, OperationPreviewRequest
from app.persistence.assets import content_hash
from app.services.document_service import DocumentService
from tests.design_baseline_support import CASES
from tests.test_postgres import checked
from tests.test_recompute_api import request_for


@pytest.mark.parametrize('case', CASES['feasible'], ids=lambda c: c['id'])
def test_mvp_move_recompute_blocked_publish_reopen_package(api, postgres_database, monkeypatch, case):
    project = checked(api.post('/api/projects', json=dict(name='MVP '+case['id'],
        requirements={**CASES['requirements'], 'num_feeders': case['num_feeders']})), 201)
    key = project['id']
    root = f'/api/projects/{key}'
    service = DocumentService(postgres_database)
    base = service.load(key)
    values = {**CASES['requirements'], 'num_feeders': case['num_feeders']}
    requirements = checked(api.post(root+'/requirements/validate', json=values))
    base = service.save(key, DocumentSave(**request_for(base), requirements=requirements,
        configuration=base.document.configuration))
    initial = checked(api.post(root+'/design/recompute', json=request_for(base)))
    checked(api.post(root+'/design/generation-proposal/accept', json=initial['batch'],
        headers={'Idempotency-Key': 'mvp-initial'}))
    base = service.load(key)
    assert len(base.snapshots.pdm.components) == case['num_feeders']*2+5
    assert len(base.snapshots.pdm.routes) == case['num_feeders']*3+8
    part = max((c for c in base.snapshots.pdm.components if c.rail_id), key=lambda c: c.position.x+c.width)
    position = part.position.model_dump()
    position['x'] += 1
    operation = OperationPreviewRequest.model_validate(dict(batch_id=str(uuid4()),
        document_id=base.document.document_id, base_sequence=base.document.document_sequence,
        expected_version=base.document.lock_version, base_revision_id=base.document.base_revision_id,
        operations=[dict(operation_id=str(uuid4()), type='MoveComponent',
            origin=dict(kind='MANUAL', actor_id='mvp-acceptance'),
            preconditions=dict(snapshot_sha256=base.document.models.pdm.sha256),
            target=dict(cem_component_id=part.cem_component_id, pdm_component_id=part.id),
            parameters=dict(position_mm=position))]))
    service.commit_operations(key, operation, 'mvp-move')
    moved = service.load(key)
    assert moved.document.models.cem == base.document.models.cem
    assert moved.document.dirty_stages == ['routes', 'physical_validation', 'cad']
    from app.services.calculation_engine import CalculationEngine
    from app.services.netlist_engine import NetlistEngine
    def forbidden(*args, **kwargs):
        raise AssertionError('Movement must not recalculate electrical intent')
    with monkeypatch.context() as patch:
        patch.setattr(CalculationEngine, 'calculate_db_parameters', forbidden)
        patch.setattr(NetlistEngine, 'generate_netlist', forbidden)
        computed = checked(api.post(root+'/design/recompute', json=request_for(moved)))
    assert computed['scheduled_stages'] == ['routes', 'physical_validation', 'cad']
    assert [(r['stage_id'], r['executions']) for r in computed['stage_executions']] == [
        ('routes', 1), ('physical_validation', 1), ('cad', 1)]
    assert service.load(key) == moved
    receipt = checked(api.post(root+'/design/generation-proposal/accept', json=computed['batch'],
        headers={'Idempotency-Key': 'mvp-recompute'}))
    saved = service.load(key)
    assert not saved.document.dirty_stages
    assert saved.snapshots.pdm.validation_results == []
    assert saved.document.models.cem == moved.document.models.cem
    assert next(c.position.model_dump() for c in saved.snapshots.pdm.components if c.id == part.id) == position
    service.save(key, DocumentSave(**request_for(saved), requirements=saved.snapshots.requirements,
        configuration=saved.document.configuration))
    assert DocumentService(postgres_database).load(key) == saved
    checked(api.post(root+'/open'))
    assert checked(api.get(f'/api/v1/projects/{key}/document')) == json.loads(saved.model_dump_json())
    report = checked(api.get(root+'/validation/working'))
    assert report['aggregate']['required_status'] == 'UNRESOLVED'
    rejected = api.post(root+'/design/publish', json=dict(**request_for(saved),
        report_signature=report['report_signature']))
    assert rejected.status_code == 409
    assert rejected.json()['error']['code'].startswith('PUBLISH_')
    assert service.load(key) == saved
    assert checked(api.get(root+'/revisions')) == []
    package = checked(api.get(root+'/export'))
    assert package['working_document'] == saved.model_dump(mode='json')
    assert package['sha256'] == content_hash({k: v for k, v in package.items() if k != 'sha256'})
    # Durable undo/redo after reopening restores exact snapshots, not a mesh overlay.
    for action, expected in [('UNDO', moved), ('REDO', saved)]:
        history = service.operation_history(key)
        request = HistoryRequest(batch_id=uuid4(), operation_id=uuid4(),
            document_id=history.document_id, base_sequence=history.document_sequence,
            expected_version=history.lock_version, base_revision_id=saved.document.base_revision_id,
            before_content_sha256=history.content_sha256, action=action,
            target_batch_id=computed['batch']['batch_id'], origin=dict(kind='MANUAL', actor_id='mvp-acceptance'))
        service.apply_history(key, request, 'mvp-'+action)
        assert service.load(key).snapshots == expected.snapshots
    print('MVP_ACCEPTANCE '+json.dumps(dict(case=case['id'], project_id=key,
        document_id=saved.document.document_id, content_sha256=saved.content_sha256,
        components=len(saved.snapshots.pdm.components), routes=len(saved.snapshots.pdm.routes),
        models={k: v.sha256 for k, v in saved.document.models if v is not None},
        moved_component=part.cem_component_id, position_mm=position,
        stage_executions=computed['stage_executions'], unrelated_electrical_calls=0,
        package_sha256=package['sha256'], report_signature=report['report_signature'],
        publish_status=rejected.status_code, publish_code=rejected.json()['error']['code'],
        revision_count=0, receipt_id=str(receipt.get('batch_id')))), flush=True)
