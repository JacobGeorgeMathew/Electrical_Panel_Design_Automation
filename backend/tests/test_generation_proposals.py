"""Generation uses shared fences/history and never replaces protected intent."""
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from app.models.document import SnapshotReference, GenerationIntent, snapshot_sha256
from app.models.operations import OperationPreviewRequest, HistoryRequest
from app.persistence import models as m
from app.persistence.operations import OperationBatchRepository, _prepare
from app.persistence.repositories import PersistenceError
from app.services import generation_proposals as proposals
from app.services.document_service import DocumentService
from app.services.operations.engineering import EngineeringChoices
from app.services.operations.registry import preview_operations
from tests.test_document_contract import document_fixture as legacy_document_fixture
from tests.test_operation_persistence import persisted_base as legacy_persisted_base, load, history
from tests.test_operations import request_for


def document_fixture():
    base = legacy_document_fixture()
    base.document.generation_intent = GenerationIntent()
    return base


def persisted_base(database):
    from app.persistence.documents import DocumentRepository
    key, base = legacy_persisted_base(database)
    base.document.generation_intent = GenerationIntent()
    with database.sessions.begin() as session:
        DocumentRepository(session).store(base)
    return key, base


def generated(base):
    result = deepcopy(base)
    result.snapshots.pdm.components[0].position.x += 1
    result.snapshots.pdm.components[0].terminals[0]['x'] += 1
    result.document.models.pdm = SnapshotReference(sha256=snapshot_sha256(result.snapshots.pdm))
    return result


def batch(base, candidate):
    doc = base.document
    proposal_id = str(uuid4())
    return OperationPreviewRequest.model_validate(dict(batch_id=proposal_id, document_id=doc.document_id,
        base_sequence=doc.document_sequence, expected_version=doc.lock_version, base_revision_id=doc.base_revision_id,
        operations=[dict(type='ApplyGeneration', operation_id=str(uuid4()), proposal_status='PROPOSED',
            origin=dict(kind='AUTOMATIC', actor_id='test', proposal_id=proposal_id), target=dict(panel_id=doc.panel_id),
            preconditions=dict(snapshot_sha256=doc.models.requirements.sha256,
                model_sha256={k: getattr(doc.models, k).sha256 if getattr(doc.models, k) else None for k in proposals.KINDS}),
            parameters=dict(candidate_sha256=proposals.digest(candidate), overrides={}))]))


def test_preview_detached_and_explicit_acceptance():
    base = document_fixture()
    before = deepcopy(base)
    candidate = generated(base)
    request = batch(base, candidate)
    choices = EngineeringChoices(generation=candidate)
    preview = preview_operations(base, request, choices)
    assert base == before and preview.persisted is False
    assert preview.candidate.document.document_sequence == base.document.document_sequence
    assert preview.changes[0].model == 'pdm'
    with pytest.raises(PersistenceError, match='separate explicit acceptance'):
        _prepare(base, request, choices)
    prepared = _prepare(base, request, choices, accept_generation=True)
    assert prepared.after.document.document_sequence == base.document.document_sequence + 1
    assert prepared.after.document.provenance.proposal_id == str(request.batch_id)


@pytest.mark.parametrize('fence', ['expected_version', 'base_sequence', 'base_revision_id', 'document_id', 'snapshot', 'models', 'digest'])
def test_generation_shared_fences(fence):
    base = document_fixture()
    candidate = generated(base)
    request = batch(base, candidate)
    op = request.operations[0]
    if fence in ('expected_version', 'base_sequence'):
        setattr(request, fence, getattr(request, fence) + 1)
    elif fence in ('base_revision_id', 'document_id'):
        setattr(request, fence, 'other')
    elif fence == 'snapshot':
        op.preconditions.snapshot_sha256 = '0' * 64
    elif fence == 'models':
        op.preconditions.model_sha256['pdm'] = None
    else:
        op.parameters.candidate_sha256 = '0' * 64
    with pytest.raises(PersistenceError):
        _prepare(base, request, EngineeringChoices(generation=candidate), accept_generation=True)


def test_locked_and_manual_intent_conflicts():
    base = document_fixture()
    base.document.generation_intent = GenerationIntent(locked_placements=['QF001'])
    candidate = generated(base)
    with pytest.raises(PersistenceError, match='manual intent'):
        preview_operations(base, batch(base, candidate), EngineeringChoices(generation=candidate))
    assert proposals.conflicts(base, candidate)[0]['target'] == 'QF001'
    assert not proposals.conflicts(base, base)
    manual = preview_operations(base, OperationPreviewRequest.model_validate(request_for(base))).candidate
    assert manual.document.generation_intent.locked_placements == ['QF001']
    assert manual.document.generation_intent.manual_models == ['pdm']
    assert proposals.conflicts(manual, candidate)


def test_untracked_historical_manual_snapshots_are_protected():
    base = legacy_document_fixture()
    assert proposals.conflicts(base, generated(base))[0]['target'] == 'pdm'


def test_retained_proposal_is_bound_bounded_and_expires(monkeypatch):
    class Database:
        pass

    database = Database()
    base = document_fixture()
    candidate = generated(base)
    request = batch(base, candidate)
    choices = EngineeringChoices()
    proposals.remember_proposal(database, base, request, candidate)
    assert proposals.generation_choices(database, 'unused', base, request, choices).generation == candidate
    altered = request.model_copy(deep=True)
    altered.operations[0].parameters.overrides = {'num_feeders': 9}
    with pytest.raises(PersistenceError, match='Proposal or document base changed'):
        proposals.generation_choices(database, 'unused', base, altered, choices)
    monkeypatch.setattr(proposals, 'MAX_PROPOSALS', 1)
    another = batch(base, candidate)
    proposals.remember_proposal(database, base, another, candidate)
    with pytest.raises(PersistenceError, match='expired'):
        proposals.generation_choices(database, 'unused', base, request, choices)
    now = proposals.monotonic()
    monkeypatch.setattr(proposals, 'monotonic', lambda: now + proposals.PROPOSAL_TTL_SECONDS + 1)
    with pytest.raises(PersistenceError, match='expired'):
        proposals.generation_choices(database, 'unused', base, another, choices)


def test_pipeline_binding_retains_nondefault_matching_ids_and_input_provenance():
    from app.services.schematic_engine import SchematicEngine
    base = document_fixture()
    result = dict(cem=base.snapshots.cem.model_dump(mode='json'),
        pdm=base.snapshots.pdm.model_dump(mode='json'),
        schematic=SchematicEngine().generate_schematic_data(base.snapshots.cem))
    base.snapshots.pdm.id = 'retained-layout'
    base.snapshots.cem.physical_design_id = 'retained-layout'
    base.snapshots.pdm.components[0].id = 'retained-part'
    for kind in ('cem', 'pdm'):
        setattr(base.document.models, kind, SnapshotReference(sha256=snapshot_sha256(getattr(base.snapshots, kind))))
    manifest = dict(engine_version='db-pipeline-4', generator=dict(name='panelstudio-primitives', version='3'),
        validation_policy_version='strict-v1', archetype_version_id='archetype-1', rule_set_version_id='rules-1', cad_model_versions={})
    candidate = proposals.generated_document(base, base.snapshots.requirements, result, manifest)
    assert candidate.snapshots.pdm.id == candidate.snapshots.cem.physical_design_id == 'retained-layout'
    assert candidate.snapshots.pdm.components[0].id == 'retained-part'
    assert candidate.snapshots.schematic.symbols[0].id == base.snapshots.schematic.symbols[0].id
    assert candidate.snapshots.schematic.wires[0].id == base.snapshots.schematic.wires[0].id
    assert candidate.snapshots.requirements.items == base.snapshots.requirements.items
    assert candidate.document.enclosure_interfaces == base.document.enclosure_interfaces


def test_atomic_acceptance_retry_stale_and_undo(postgres_database, monkeypatch):
    key, _ = persisted_base(postgres_database)
    base = load(postgres_database, key)
    candidate = generated(base)
    request = batch(base, candidate)
    proposals.remember_proposal(postgres_database, base, request, candidate)
    repo = OperationBatchRepository(postgres_database)
    service = DocumentService(postgres_database)
    service.preview_operations(key, request)
    assert load(postgres_database, key) == base and history(postgres_database, key) == [[], []]
    receipt = repo.accept_generation(key, request, 'accept-generation')
    assert repo.accept_generation(key, request, 'accept-generation') == receipt
    saved = load(postgres_database, key)
    assert saved.snapshots.pdm == candidate.snapshots.pdm
    assert len(history(postgres_database, key)[0]) == 1
    with pytest.raises(PersistenceError):
        repo.accept_generation(key, request, 'stale-generation')
    view = service.operation_history(key)
    undo = HistoryRequest(batch_id=uuid4(), operation_id=uuid4(), document_id=view.document_id,
        base_sequence=view.document_sequence, expected_version=view.lock_version,
        base_revision_id=saved.document.base_revision_id, before_content_sha256=view.content_sha256,
        action='UNDO', target_batch_id=request.batch_id, origin=dict(kind='MANUAL', actor_id='test'))
    service.apply_history(key, undo, 'undo-generation')
    assert load(postgres_database, key).snapshots == base.snapshots
    with postgres_database.sessions() as session:
        assert session.scalar(select(func.count()).select_from(m.project_revisions).where(m.project_revisions.c.project_id == key)) == 0


def test_failed_generation_write_rolls_back_whole_batch(postgres_database, monkeypatch):
    from app.persistence.documents import DocumentRepository
    key, _ = persisted_base(postgres_database)
    base = load(postgres_database, key)
    request = batch(base, generated(base))
    proposals.remember_proposal(postgres_database, base, request, generated(base))
    original = DocumentRepository.store

    def fail_after_store(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('Injected storage failure')

    monkeypatch.setattr(DocumentRepository, 'store', fail_after_store)
    with pytest.raises(RuntimeError, match='Injected storage failure'):
        OperationBatchRepository(postgres_database).accept_generation(key, request, 'failed-generation')
    assert load(postgres_database, key) == base
    assert history(postgres_database, key) == [[], []]


def test_real_pipeline_proposal_and_accept(api, postgres_database, monkeypatch):
    project = api.post('/api/projects', json=dict(name='Generation proposal')).json()
    key = project['id']
    path = f'/api/projects/{key}/design/generation-proposal'
    base = DocumentService(postgres_database).load(key)
    preview = api.post(path, json={'num_feeders': 5})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body['status'] == 'REVIEW_REQUIRED'
    assert DocumentService(postgres_database).load(key) == base
    assert api.get(f'/api/projects/{key}/revisions').json() == []
    from app.services.orchestrator import DesignOrchestrator
    with monkeypatch.context() as patch:
        def forbidden(*args, **kwargs):
            raise AssertionError('Acceptance must use the exact reviewed server candidate')
        patch.setattr(DesignOrchestrator, 'generate_design', forbidden)
        response = api.post(path + '/accept', json=body['batch'], headers={'Idempotency-Key': 'real-generation'})
    assert response.status_code == 200, response.text
    assert response.json()['document_sequence'] == base.document.document_sequence + 1
    saved = DocumentService(postgres_database).load(key)
    assert saved.snapshots.cem and saved.snapshots.pdm and saved.snapshots.schematic
    assert saved.document.panel_id == base.document.panel_id
    assert api.get(f'/api/projects/{key}/revisions').json() == []
    # Repeated pipeline execution retains matching logical/physical identities.
    next_proposal = api.post(path, json={})
    assert next_proposal.status_code == 200, next_proposal.text
    next_candidate = next_proposal.json()['preview']['candidate']
    assert [c['id'] for c in next_candidate['snapshots']['pdm']['components']] == [c.id for c in saved.snapshots.pdm.components]
    assert [s['id'] for s in next_candidate['snapshots']['schematic']['symbols']] == [s.id for s in saved.snapshots.schematic.symbols]
    assert api.post(f'/api/projects/{key}/design/generate').status_code == 409

    # Imported locks survive ordinary Save and reject removal by generation.
    from app.persistence.documents import DocumentRepository
    from app.models.document_api import DocumentSave
    last_feeder = sorted(c.id for c in saved.snapshots.cem.components if c.category == 'MCB')[-1]
    saved.document.generation_intent = GenerationIntent(locked_placements=[last_feeder])
    with postgres_database.sessions.begin() as session:
        DocumentRepository(session).store(saved)
    changed = DocumentService(postgres_database).save(key, DocumentSave(
        document_id=saved.document.document_id, expected_version=saved.document.lock_version,
        expected_document_sequence=saved.document.document_sequence, requirements=saved.snapshots.requirements,
        configuration={'enclosure_parameters': {}}))
    assert changed.document.generation_intent.locked_placements == [last_feeder]
    blocked = api.post(path, json={'num_feeders': 4})
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()['status'] == 'CONFLICT' and blocked.json()['batch'] is None
    assert any(c['target'] == last_feeder for c in blocked.json()['conflicts'])
    assert DocumentService(postgres_database).load(key) == changed
