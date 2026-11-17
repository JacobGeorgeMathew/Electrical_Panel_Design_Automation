"""Runtime execution, preview/acceptance boundaries, Save and stale fences."""
from uuid import uuid4

from sqlalchemy import select, func

from app.models.document_api import DocumentSave
from app.models.operations import OperationPreviewRequest, HistoryRequest
from app.persistence import models as m
from app.persistence.operations import OperationBatchRepository
from app.services.document_service import DocumentService
from tests.test_postgres import checked, create


def request_for(base):
    return dict(document_id=base.document.document_id, expected_version=base.document.lock_version,
                expected_document_sequence=base.document.document_sequence)


def test_recompute_runtime_cache_move_save_history_and_stale(api, postgres_database, monkeypatch):
    key = create(api)['id']
    design = f'/api/projects/{key}/design'
    service = DocumentService(postgres_database)
    base = service.load(key)
    # Fresh input-only documents execute all stages through the scheduler.
    fresh = checked(api.post(design+'/recompute', json=request_for(base)))
    assert fresh['scheduled_stages'][0] == 'requirements'
    assert {r['stage_id'] for r in fresh['stage_executions']} == set(fresh['scheduled_stages'])
    assert service.load(key) == base
    accepted = checked(api.post(design+'/generation-proposal/accept', json=fresh['batch'],
                               headers={'Idempotency-Key': 'first-recompute'}))
    base = service.load(key)
    assert not base.document.dirty_stages
    assert base.snapshots.cem and base.snapshots.pdm
    assert api.get(f'/api/projects/{key}/revisions').json() == []

    # Actual MoveComponent retains local terminal anchors using the shared
    # operation handler. The rightmost DIN device has spare space to its right.
    part = max((c for c in base.snapshots.pdm.components if c.rail_id), key=lambda c: c.position.x+c.width)
    position = part.position.model_dump()
    position['x'] += 1
    batch = OperationPreviewRequest.model_validate(dict(batch_id=str(uuid4()), document_id=base.document.document_id,
        base_sequence=base.document.document_sequence, expected_version=base.document.lock_version,
        base_revision_id=base.document.base_revision_id,
        operations=[dict(type='MoveComponent', operation_id=str(uuid4()), origin=dict(kind='MANUAL', actor_id='test'),
            target=dict(cem_component_id=part.cem_component_id, pdm_component_id=part.id),
            parameters=dict(position_mm=position), preconditions=dict(snapshot_sha256=base.document.models.pdm.sha256))]))
    service.commit_operations(key, batch, 'move-before-recompute')
    moved = service.load(key)
    assert moved.document.dirty_stages == ['routes', 'physical_validation', 'cad']
    from app.services.calculation_engine import CalculationEngine
    from app.services.netlist_engine import NetlistEngine
    from app.services.orchestrator import DesignOrchestrator
    def forbidden(*args, **kwargs):
        raise AssertionError('Unrelated full/electrical execution')
    with monkeypatch.context() as patch:
        patch.setattr(CalculationEngine, 'calculate_db_parameters', forbidden)
        patch.setattr(NetlistEngine, 'generate_netlist', forbidden)
        patch.setattr(DesignOrchestrator, 'generate_design', forbidden)
        # Save is deliberately independent, including all stage/cache metadata.
        with postgres_database.sessions() as session:
            count = session.scalar(select(func.count()).select_from(m.stage_results))
        service.save(key, DocumentSave(**request_for(moved), requirements=moved.snapshots.requirements,
                                      configuration=moved.document.configuration))
        with postgres_database.sessions() as session:
            assert session.scalar(select(func.count()).select_from(m.stage_results)) == count
        response = checked(api.post(design+'/recompute', json=request_for(moved)))
        assert [r['stage_id'] for r in response['stage_executions']] == ['routes', 'physical_validation', 'cad']
        assert all(r['executions'] == 1 for r in response['stage_executions'])
        repeated = checked(api.post(design+'/recompute', json=request_for(moved)))
        assert all(r['status'] == 'CACHED' and r['executions'] == 0 for r in repeated['stage_executions'])
    assert service.load(key) == moved
    receipt = checked(api.post(design+'/generation-proposal/accept', json=response['batch'],
                              headers={'Idempotency-Key': 'accept-moved-recompute'}))
    assert checked(api.post(design+'/generation-proposal/accept', json=response['batch'],
                           headers={'Idempotency-Key': 'accept-moved-recompute'})) == receipt
    saved = service.load(key)
    assert not saved.document.dirty_stages
    assert saved.snapshots.cem == moved.snapshots.cem
    assert saved.document.generation_intent == moved.document.generation_intent
    assert next(c for c in saved.snapshots.pdm.components if c.id == part.id).position.model_dump() == position
    assert api.post(design+'/recompute', json=request_for(moved)).status_code == 409
    assert api.post(design+'/generation-proposal/accept', json=repeated['batch'],
                    headers={'Idempotency-Key': 'stale-candidate'}).status_code == 409
    history = service.operation_history(key)
    assert len(history.undo_batch_ids) == 3
    undo = HistoryRequest(batch_id=uuid4(), operation_id=uuid4(), document_id=history.document_id,
        base_sequence=history.document_sequence, expected_version=history.lock_version,
        base_revision_id=saved.document.base_revision_id, before_content_sha256=history.content_sha256,
        action='UNDO', target_batch_id=response['batch']['batch_id'], origin=dict(kind='MANUAL', actor_id='test'))
    service.apply_history(key, undo, 'undo-recompute')
    assert service.load(key).snapshots == moved.snapshots
    assert api.get(f'/api/projects/{key}/revisions').json() == []


def test_propagate_is_nonexecuting_requirement_preview(api, postgres_database, monkeypatch):
    key = create(api)['id']
    service = DocumentService(postgres_database)
    base = service.load(key)
    # New projects intentionally start with an empty working input snapshot;
    # populate it through Save before previewing an existing requirement.
    from app.services.project_service import ProjectService
    application = ProjectService(postgres_database)
    project, template, *_ = application._inputs(key)
    base = service.save(key, DocumentSave(**request_for(base),
        requirements=application.validate(template, key, project['requirements'])))
    from app.services.orchestrator import DesignOrchestrator
    def forbidden(*args, **kwargs):
        raise AssertionError('Preview or Save executed generation')
    monkeypatch.setattr(DesignOrchestrator, 'generate_design', forbidden)
    response = checked(api.post(f'/api/projects/{key}/design/propagate-change', json=dict(
        modified_field='num_feeders', new_value=8, expected_version=base.document.lock_version)))
    assert response['status'] == 'PREVIEW' and not response['persisted']
    assert response['batch']['operations'][0]['type'] == 'UpdateRequirement'
    assert service.load(key) == base
    assert api.get(f'/api/projects/{key}/revisions').json() == []
    OperationBatchRepository(postgres_database).commit(key, OperationPreviewRequest.model_validate(response['batch']), 'apply-preview')
    applied = service.load(key)
    assert next(r.value for r in applied.snapshots.requirements.items if r.id == 'num_feeders') == 8
    assert applied.snapshots.cem is None
