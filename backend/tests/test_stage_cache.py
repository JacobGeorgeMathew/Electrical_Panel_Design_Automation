"""Signature consumption, explicit cache reuse, hostile storage and document clocks."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from sqlalchemy import event, func, select, update

from app.models.document import GeneratorPin, PinnedVersions
from app.models.pdm import EnclosureSpec
from app.persistence import models as m
from app.persistence.assets import content_hash
from app.persistence.audit import audit_assets
from app.persistence.documents import DocumentRepository
from app.persistence.repositories import PersistenceError
from app.services.stages import artifacts as a, electrical as e, physical as p
from app.services.stages.cache import (
    ADAPTERS, ManagedAsset, StageCache, StageSignature, make_signature,
)
from tests.design_baseline_support import CASES, engine
from tests.integrity_support import privileged_connection
from tests.test_design_document_storage import row_images
from tests.test_electrical_stages import execute, supplied
from tests.test_operation_persistence import persisted_base, load
from tests.test_physical_stages import supplied as physical_supplied


def pins():
    return PinnedVersions(engine_version='fixture-engine-1',
        generator=GeneratorPin(name='panelstudio-primitives', version='3'),
        catalog_manifest_sha256='a' * 64, validation_policy_version='policy-1',
        catalog_versions=dict(archetype='fixture-db-1', rules='fixture-rules-1',
            components='fixture-components-1', enclosures='fixture-enclosures-1', hardware='fixture-hardware-1'))


@pytest.fixture(scope='module')
def material():
    case = CASES['feasible'][0]
    req, catalog = supplied(case)
    requirements, calculations, selection, connectivity, schematic = execute(req, catalog)
    full = engine(case).generate_design(case['project_id'], persist_requirements=False)
    enclosure, hardware = physical_supplied(case, full)
    pdm = p.PhysicalSnapshot.capture(full['pdm'])
    zoning = p.ZoningOutput(enclosure=e.Snapshot[EnclosureSpec].capture(next(
            row for row in enclosure.catalog.rows.read() if row.id == pdm.read().enclosure_id)),
        layout=enclosure.layout, hardware=hardware)
    placed = p.PlacementOutput(pdm=pdm, zoning=zoning)
    common = dict(context=req.context, cem=enclosure.cem, pdm=pdm)
    calls = dict(
        requirements=req,
        calculations=e.CalculationsInput(context=req.context, requirements=requirements),
        selection=e.SelectionInput(context=req.context, requirements=requirements,
            calculations=calculations, catalog=catalog),
        connectivity=e.ConnectivityInput(context=req.context, requirements=requirements, selection=selection),
        schematic=e.SchematicInput(context=req.context, selection=selection, connectivity=connectivity),
        enclosure=enclosure,
        zoning=p.ZoningInput(enclosure=zoning.enclosure, layout=zoning.layout, hardware=hardware),
        placement=p.PlacementInput(context=req.context, cem=enclosure.cem, zoning=zoning),
        ducts=p.DuctsInput(placement=placed),
        routes=p.RoutesInput(**common, layout=enclosure.layout),
        local_geometry=p.GeometryInput(**common),
        physical_validation=p.PhysicalValidationInput(**common),
        bom=a.BOMInput(**common),
        cad=a.CADInput(**common, schematic=schematic.schematic, generator_version='3',
            model_versions=e.Snapshot[dict[str, str]].capture({})),
    )
    return calls, pins(), pdm.read().validation_policy, req.context


def replace_pin(inputs, old, new):
    def walk(value):
        if isinstance(value, dict):
            return {key: walk(child) for key, child in value.items()}
        if isinstance(value, list):
            return [walk(child) for child in value]
        return new if value == old else value
    return type(inputs).model_validate(walk(inputs.model_dump(mode='json')))


@pytest.mark.parametrize('key,consumers', [
    ('rules', set(ADAPTERS)),
    ('archetype', set(ADAPTERS)),
    ('components', set(ADAPTERS) - {'requirements', 'calculations'}),
    ('enclosures', {'enclosure', 'zoning', 'placement', 'ducts', 'routes', 'local_geometry',
                    'physical_validation', 'bom', 'cad'}),
    ('hardware', {'enclosure', 'zoning', 'placement', 'ducts', 'routes', 'local_geometry',
                  'physical_validation', 'bom', 'cad'}),
])
def test_exact_version_consumption_matrix(material, key, consumers):
    calls, versions, policy, context = material
    changed = versions.model_copy(deep=True)
    old = changed.catalog_versions[key]
    changed.catalog_versions[key] = old + '-next'
    # An aggregate manifest change must not erase selective cache eligibility.
    changed.catalog_manifest_sha256 = 'b' * 64
    for name, inputs in calls.items():
        before = make_signature(name, inputs, versions, policy, context)
        after = make_signature(name, replace_pin(inputs, old, old + '-next'), changed, policy, context)
        assert (before.key != after.key) == (name in consumers), name


def test_policy_model_generator_engine_and_unknown_pin_dependencies(material):
    calls, versions, policy, context = material
    physical = {'enclosure', 'zoning', 'placement', 'ducts', 'routes', 'local_geometry',
                'physical_validation', 'bom', 'cad'}
    for name, inputs in calls.items():
        before = make_signature(name, inputs, versions, policy, context)
        changed = versions.model_copy(deep=True)
        changed.validation_policy_version = 'policy-next'
        assert (before.key != make_signature(name, inputs, changed, policy, context).key) == (name in physical)
        changed = versions.model_copy(deep=True)
        changed.model_versions['model-1'] = 'version-2'
        model_input = inputs.model_copy(update={'model_versions': e.Snapshot[dict[str, str]].capture(
            changed.model_versions)}) if name == 'cad' else inputs
        assert (before.key != make_signature(name, model_input, changed, policy, context).key) == (name == 'cad')
        changed = versions.model_copy(deep=True)
        changed.generator.version = '4'
        generator_input = inputs.model_copy(update={'generator_version': '4'}) if name == 'cad' else inputs
        assert (before.key != make_signature(name, generator_input, changed, policy, context).key) == (name == 'cad')
        changed = versions.model_copy(deep=True)
        changed.catalog_versions['future_catalog'] = 'exact-1'
        assert before.key != make_signature(name, inputs, changed, policy, context).key
        changed.engine_version = 'next-engine'
        changed_context = context.model_copy(update={'engine_version': 'next-engine'})
        assert before.key != make_signature(name, replace_pin(inputs, versions.engine_version,
            changed.engine_version), changed, policy, changed_context).key


def test_policy_content_not_just_label_and_consumed_payloads(material):
    calls, versions, policy, context = material
    # Same label, different real limit. No electrical signature changes.
    # Choose a real policy field rather than depending on future policy additions.
    field = next(key for key, value in policy.model_dump().items() if isinstance(value, (int, float)))
    changed = type(policy).model_validate({**policy.model_dump(), field: getattr(policy, field) + 1})
    for name in ('requirements', 'calculations', 'enclosure', 'zoning', 'placement'):
        before = make_signature(name, calls[name], versions, policy, context)
        assert (before.key != make_signature(name, calls[name], versions, changed, context).key) == (
            name in {'enclosure', 'zoning', 'placement'})
    req = calls['requirements']
    reordered = req.model_copy(update={'answers': type(req.answers).capture(dict(reversed(
        list(req.answers.read().items()))))})
    assert make_signature('requirements', req, versions).key == make_signature('requirements', reordered, versions).key
    answers = req.answers.read()
    answers['num_feeders'] += 1
    altered = req.model_copy(update={'answers': type(req.answers).capture(answers)})
    assert make_signature('requirements', req, versions).key != make_signature('requirements', altered, versions).key
    selection = calls['selection']
    catalog = selection.catalog.model_copy(update={'rows': type(selection.catalog.rows).capture(
        list(reversed(selection.catalog.rows.read())))})
    assert make_signature('selection', selection, versions).key != make_signature('selection',
        selection.model_copy(update={'catalog': catalog}), versions).key


def test_signatures_check_schemas_pins_context_and_boundary_types(material):
    calls, versions, policy, context = material
    signatures = [make_signature(name, inputs, versions, policy, context) for name, inputs in calls.items()]
    assert len({signature.key for signature in signatures}) == len(ADAPTERS)
    for signature in signatures:
        assert StageSignature.model_validate_json(signature.model_dump_json()).key == signature.key
        assert signature.manifest['input_schema'] and signature.manifest['output_schema']
        signature.manifest['inputs'].clear()  # returns a detached copy
        assert signature.manifest['inputs']
    with pytest.raises(ValueError, match='Input type'):
        make_signature('requirements', calls['selection'], versions)
    with pytest.raises(ValueError, match='version pins differ'):
        make_signature('requirements', calls['requirements'], versions.model_copy(update={
            'catalog_versions': {**versions.catalog_versions, 'rules': 'different'}}))
    with pytest.raises(ValueError, match='policy content'):
        make_signature('routes', calls['routes'], versions)
    with pytest.raises(ValueError, match='context'):
        make_signature('zoning', calls['zoning'], versions)
    foreign = calls['calculations'].model_copy(update={
        'context': context.model_copy(update={'project_id': 'different-project'})})
    with pytest.raises(ValueError, match='Snapshot ownership'):
        make_signature('calculations', foreign, versions)


def test_schema_algorithm_drift_is_rejected_before_database_access(material, tmp_path, monkeypatch):
    from app.services.stages import cache as module
    from app.services.stages.contracts import StageRegistry
    calls, versions, policy, context = material
    signature = make_signature('requirements', calls['requirements'], versions)
    def forbidden():
        raise AssertionError('Incompatible signatures must fail before database access')
    cache = StageCache(SimpleNamespace(settings=SimpleNamespace(asset_root=tmp_path), sessions=forbidden))
    manifest = signature.manifest
    manifest['output_schema'] = '0' * 64
    from app.persistence.assets import canonical_json
    with pytest.raises(ValueError, match='Incompatible'):
        cache.lookup(StageSignature(manifest_json=canonical_json(manifest).decode()))
    registry = module.STAGE_REGISTRY
    stages = tuple(stage.model_copy(update={'algorithm_version': 'db-requirements-next'})
        if stage.id == 'requirements' else stage for stage in registry.stages)
    monkeypatch.setattr(module, 'STAGE_REGISTRY', StageRegistry(stages=stages))
    with pytest.raises(ValueError, match='Incompatible'):
        cache.lookup(signature)


def database_request(database):
    project_id, base = persisted_base(database)
    req, _ = supplied(CASES['feasible'][0])
    context = req.context.model_copy(update={'project_id': project_id, 'panel_id': base.document.panel_id})
    req = req.model_copy(update={'context': context})
    return base, req, make_signature('requirements', req, pins())


def counts(database):
    with database.sessions() as session:
        return tuple(session.scalar(select(func.count()).select_from(table)) for table in (
            m.stage_results, m.document_stage_states))


def test_explicit_cache_roundtrip_versions_and_no_history_mutation(postgres_database):
    db = postgres_database
    base, inputs, signature = database_request(db)
    cache = StageCache(db)
    untouched = set(m.metadata.tables) - {'stage_results', 'document_stage_states'}
    before = row_images(db.engine, untouched)
    initial_counts = counts(db)
    assert cache.lookup(signature).integrity == 'MISSING'
    assert counts(db) == initial_counts
    state = cache.observe(base.document.document_id, 0, signature)
    assert (state.status, state.input_version, state.output_version) == ('DIRTY', 1, 0)
    # Execution is explicit and detached; a cache service never calls the engine.
    output = ADAPTERS['requirements'].execute(inputs)
    state = cache.record_success(base.document.document_id, 0, signature, output)
    assert (state.status, state.input_version, state.output_version) == ('VALID', 1, 1)
    hit = cache.lookup(signature)
    assert hit.output == output and hit.integrity == 'VALID'
    hit.output.validated_requirements.read().items.clear()
    assert cache.lookup(signature).output == output
    state = cache.observe(base.document.document_id, 0, signature)
    assert state.status == 'VALID'
    state = cache.accept_cached(base.document.document_id, 0, signature)
    assert (state.input_version, state.output_version) == (1, 1)
    assert row_images(db.engine, untouched) == before


def test_dirty_blocked_failed_states_and_content_versions(postgres_database):
    db = postgres_database
    base, inputs, signature = database_request(db)
    cache = StageCache(db)
    output = ADAPTERS['requirements'].execute(inputs)
    cache.record_success(base.document.document_id, 0, signature, output)
    blocked = cache.observe(base.document.document_id, 0, signature, ('calculations',))
    assert blocked.status == 'BLOCKED' and blocked.blocked_by == ('calculations',)
    # A pin bump with unchanged result still makes the document output stale.
    versions = pins()
    versions.catalog_versions['rules'] = 'rules-next'
    inputs = inputs.model_copy(update={'rules': inputs.rules.model_copy(update={'rules_version': 'rules-next'})})
    newer = make_signature('requirements', inputs, versions)
    dirty = cache.observe(base.document.document_id, 0, newer)
    assert (dirty.status, dirty.input_version, dirty.output_version) == ('DIRTY', 2, 1)
    assert dirty.output_signature == signature.key and dirty.input_signature == newer.key
    failed = cache.record_failure(base.document.document_id, 0, newer, 'INVALID_REQUIREMENTS')
    assert failed.status == 'FAILED' and failed.output_version == 1
    assert cache.observe(base.document.document_id, 0, newer).status == 'FAILED'
    repaired = cache.record_success(base.document.document_id, 0, newer, ADAPTERS['requirements'].execute(inputs))
    assert repaired.status == 'VALID' and repaired.input_version == 2
    assert repaired.output_version == 1  # identical accepted output content
    assert repaired.output_signature == newer.key and repaired.failure_code is None


@pytest.mark.parametrize('damage', ['payload', 'digest', 'signature', 'typed_payload', 'schema'])
def test_corruption_is_rejected_and_only_explicit_execution_replaces_entry(postgres_database, damage):
    db = postgres_database
    base, inputs, signature = database_request(db)
    cache = StageCache(db)
    output = ADAPTERS['requirements'].execute(inputs)
    original = cache.record_success(base.document.document_id, 0, signature, output)
    with db.sessions() as session:
        row = dict(session.execute(select(m.stage_results).where(
            m.stage_results.c.id == original.result_id)).mappings().one())
    if damage == 'payload':
        changes = dict(result={'bad': 'shape'})
    elif damage == 'digest':
        changes = dict(result_sha256='0' * 64)
    elif damage == 'typed_payload':
        changes = dict(result={'bad': 'shape'}, result_sha256=content_hash(dict(output={'bad': 'shape'}, assets=[])))
    else:
        manifest = deepcopy(row['signature'])
        manifest['output_schema' if damage == 'schema' else 'engine_version'] = 'wrong'
        changes = dict(signature=manifest)
    with privileged_connection(db) as connection:
        connection.execute(update(m.stage_results).where(m.stage_results.c.id == original.result_id).values(**changes))
    before = counts(db)
    for _ in range(2):
        assert cache.lookup(signature).integrity == 'CORRUPT'
    assert counts(db) == before
    dirty = cache.observe(base.document.document_id, 0, signature)
    assert dirty.status == 'DIRTY' and dirty.integrity == 'CORRUPT'
    with pytest.raises(PersistenceError) as caught:
        cache.accept_cached(base.document.document_id, 0, signature)
    assert caught.value.code == 'STAGE_CACHE_INTEGRITY'
    assert counts(db) == before
    replacement = cache.record_success(base.document.document_id, 0, signature,
        ADAPTERS['requirements'].execute(inputs))
    assert replacement.result_id != original.result_id
    assert cache.lookup(signature).output == output
    assert cache.observe(base.document.document_id, 0, signature).status == 'VALID'
    with db.sessions() as session:
        old = dict(session.execute(select(m.stage_results).where(m.stage_results.c.id == original.result_id)).mappings().one())
    assert all(old[key] == value for key, value in changes.items())  # corrupt history retained


def test_managed_asset_hashes_missing_files_and_immutable_results(postgres_database):
    db = postgres_database
    base, inputs, signature = database_request(db)
    cache = StageCache(db)
    metadata = cache.assets.put(b'cache asset', 'json')
    audit_before = audit_assets(db)
    output = ADAPTERS['requirements'].execute(inputs)
    state = cache.record_success(base.document.document_id, 0, signature, output,
        assets=(ManagedAsset.model_validate(metadata),))
    path = cache.assets.verified_path(metadata['storage_key'], metadata['sha256'], metadata['byte_size'])
    assert cache.lookup(signature).integrity == 'VALID'
    audit_after = audit_assets(db)
    assert audit_after['referenced'] == audit_before['referenced'] + 1
    assert audit_after['unreferenced_files'] == audit_before['unreferenced_files'] - 1
    path.write_bytes(b'corrupted!')
    assert cache.lookup(signature).integrity == 'CORRUPT'
    assert audit_assets(db)['missing_or_corrupt'] == audit_after['missing_or_corrupt'] + 1
    path.unlink()
    assert cache.lookup(signature).integrity == 'CORRUPT'
    # Restore exact bytes explicitly; cache reads never write the asset store.
    cache.assets.put(b'cache asset', 'json')
    assert cache.lookup(signature).integrity == 'VALID'
    with pytest.raises(PersistenceError, match='Published content'):
        with db.sessions.begin() as session:
            session.execute(update(m.stage_results).where(m.stage_results.c.id == state.result_id).values(result={}))


def test_document_sequence_fence_and_unrelated_document_changes(postgres_database):
    db = postgres_database
    base, inputs, signature = database_request(db)
    cache = StageCache(db)
    output = ADAPTERS['requirements'].execute(inputs)
    cache.record_success(base.document.document_id, 0, signature, output)
    current = load(db, base.document.project_id)
    current.document.document_sequence = 1
    current.document.provenance.actor_id = 'another-editor'
    with db.sessions.begin() as session:
        DocumentRepository(session).store(current)
    before = counts(db)
    for action in (
        lambda: cache.record_success(base.document.document_id, 0, signature, output),
        lambda: cache.record_failure(base.document.document_id, 0, signature, 'STALE'),
        lambda: cache.observe(base.document.document_id, 0, signature),
        lambda: cache.accept_cached(base.document.document_id, 0, signature),
    ):
        with pytest.raises(PersistenceError) as caught:
            action()
        assert caught.value.code == 'STAGE_INPUT_CONFLICT'
        assert counts(db) == before
    # Provenance/sequence do not participate in consumed engineering inputs.
    state = cache.observe(base.document.document_id, 1, signature)
    assert (state.status, state.input_version, state.output_version) == ('VALID', 1, 1)
    assert state.document_sequence == 1


def test_old_signature_cannot_complete_over_new_inputs_at_same_document_sequence(postgres_database):
    db = postgres_database
    base, inputs, signature = database_request(db)
    cache = StageCache(db)
    output = ADAPTERS['requirements'].execute(inputs)
    cache.record_success(base.document.document_id, 0, signature, output)
    changed = inputs.model_copy(update={'rules': inputs.rules.model_copy(update={'rules_version': 'rules-next'})})
    versions = pins()
    versions.catalog_versions['rules'] = 'rules-next'
    newer = make_signature('requirements', changed, versions)
    cache.observe(base.document.document_id, 0, newer)
    before = counts(db)
    for action in (
        lambda: cache.record_success(base.document.document_id, 0, signature, output),
        lambda: cache.record_failure(base.document.document_id, 0, signature, 'FAILED'),
        lambda: cache.accept_cached(base.document.document_id, 0, signature),
    ):
        with pytest.raises(PersistenceError) as caught:
            action()
        assert caught.value.code == 'STAGE_INPUT_CONFLICT'
        assert counts(db) == before
    cache.observe(base.document.document_id, 0, newer, ('calculations',))
    with pytest.raises(PersistenceError) as caught:
        cache.record_success(base.document.document_id, 0, newer, output)
    assert caught.value.code == 'STAGE_BLOCKED'
    # Returning to the exact original inputs can retain the verified prior output.
    state = cache.observe(base.document.document_id, 0, signature)
    assert state.status == 'VALID' and state.input_version == 3 and state.output_version == 1


def test_result_and_state_publication_roll_back_together(postgres_database):
    db = postgres_database
    base, inputs, signature = database_request(db)
    cache = StageCache(db)
    before = counts(db)
    def fail_state(connection, clause, *args):
        if getattr(getattr(clause, 'table', None), 'name', None) == 'document_stage_states':
            raise RuntimeError('injected state write failure')
    event.listen(db.engine, 'before_execute', fail_state)
    try:
        with pytest.raises(RuntimeError, match='injected'):
            cache.record_success(base.document.document_id, 0, signature,
                ADAPTERS['requirements'].execute(inputs))
    finally:
        event.remove(db.engine, 'before_execute', fail_state)
    assert counts(db) == before
    assert cache.lookup(signature).integrity == 'MISSING'


def test_reads_and_observation_never_invoke_execution(postgres_database, monkeypatch):
    from app.services.stages import cache as module
    db = postgres_database
    base, inputs, signature = database_request(db)
    cache = StageCache(db)
    output = ADAPTERS['requirements'].execute(inputs)
    def forbidden(*args, **kwargs):
        raise AssertionError('Cache inspection executed engineering')
    monkeypatch.setattr(module, 'ADAPTERS', {name: replace(binding, execute=forbidden)
        for name, binding in ADAPTERS.items()})
    assert cache.lookup(signature).integrity == 'MISSING'
    assert cache.observe(base.document.document_id, 0, signature).status == 'DIRTY'
    with pytest.raises(PersistenceError):
        cache.accept_cached(base.document.document_id, 0, signature)
    cache.record_success(base.document.document_id, 0, signature, output)
    assert cache.lookup(signature).output == output
    assert cache.observe(base.document.document_id, 0, signature).status == 'VALID'
    assert cache.accept_cached(base.document.document_id, 0, signature).status == 'VALID'
