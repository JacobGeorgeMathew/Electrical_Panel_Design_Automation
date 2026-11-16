"""Complete output hashing and per-statement publication rollback evidence."""
from copy import deepcopy
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import event, func, select

from app.persistence import models as m
from app.persistence.assets import AssetStore, content_hash
from app.persistence.repositories import PersistenceError, ProjectRepository, identifier
from app.persistence.revision_outputs import OUTPUT_KINDS, prepare_outputs, verify_outputs
from app.persistence.revisions import write_revision
from app.services.project_service import ProjectService
from tests.test_postgres import checked, create


@pytest.fixture
def bundle(tmp_path):
    """Small data isolates bundle integrity from engineering algorithms."""
    from app.models.requirements import RequirementSet
    pid = str(uuid4())
    project = dict(id=pid, database_id=pid, configuration={})
    from app.services.document_service import DocumentService
    from app.persistence.documents import document_hash
    resolved = DocumentService.empty_document(dict(id=pid, lock_version=1),
        dict(archetype_version_id=str(uuid4())))
    source = {**resolved.model_dump(mode='json'), 'content_sha256': document_hash(resolved.document)}
    pdm = dict(validation_policy={'version': 'strict-v1'}, validation_results=[], routes=[],
               mounting_plate_x=30, mounting_plate_y=40, mounting_plate_z=20, components=[])
    result = dict(cem={'components': []}, pdm=pdm, schematic={'symbols': []},
                  cad={'primitives': []}, bom=[], validation_errors=[])
    assets = AssetStore(tmp_path)
    file = {**assets.put(b'original artifact', 'glb'), 'artifact_type': 'CAD_PREVIEW',
            'file_format': 'GLB', 'generator_name': 'test', 'generator_version': '1'}
    inputs = dict(project=project, requirements=RequirementSet(project_id=pid, archetype='DB'),
                  answers={}, result=result, manifest={'engine_version': 'test'}, files=[file],
                  source=source, assets=assets, expected_version=1)
    return prepare_outputs(**inputs), assets, inputs


def stored_bundle(prepared):
    snapshots = {kind: dict(snapshot=value, schema_version=1, sha256=prepared.hashes[kind])
                 for kind, value in prepared.snapshots.items()}
    return snapshots, deepcopy(prepared.manifest['artifacts'])


@pytest.mark.parametrize('kind', sorted(OUTPUT_KINDS))
def test_every_representation_is_required_and_verified(bundle, kind):
    prepared, assets, _ = bundle
    snapshots, artifacts = stored_bundle(prepared)
    verify_outputs(prepared.manifest, prepared.sha256, snapshots, artifacts, assets)
    snapshots[kind]['snapshot'] = {'tampered': True}
    with pytest.raises(PersistenceError, match='Saved revision outputs'):
        verify_outputs(prepared.manifest, prepared.sha256, snapshots, artifacts, assets)
    del snapshots[kind]
    with pytest.raises(PersistenceError):
        verify_outputs(prepared.manifest, prepared.sha256, snapshots, artifacts, assets)


def test_artifact_bytes_metadata_and_root_are_verified(bundle):
    prepared, assets, _ = bundle
    snapshots, artifacts = stored_bundle(prepared)
    with pytest.raises(PersistenceError):
        verify_outputs(prepared.manifest, '0'*64, snapshots, artifacts, assets)
    with pytest.raises(PersistenceError):
        verify_outputs(prepared.manifest, prepared.sha256, snapshots, [], assets)
    artifacts[0]['generator_version'] = 'changed'
    with pytest.raises(PersistenceError):
        verify_outputs(prepared.manifest, prepared.sha256, snapshots, artifacts, assets)
    snapshots, artifacts = stored_bundle(prepared)
    (assets.root / artifacts[0]['storage_key']).write_bytes(b'corrupt')
    with pytest.raises(PersistenceError):
        verify_outputs(prepared.manifest, prepared.sha256, snapshots, artifacts, assets)


def test_preparation_detaches_values_and_preserves_legacy_digest_meaning(bundle):
    prepared, _, inputs = bundle
    inputs['result']['schematic']['symbols'].append({'id': 'late mutation'})
    inputs['manifest']['engine_version'] = 'changed'
    assert prepared.snapshots['SCHEMATIC'] == {'symbols': []}
    assert prepared.snapshots['INPUTS_AND_PINS']['pins']['engine_version'] == 'test'
    assert prepared.model_manifest['output_manifest_sha256'] == prepared.sha256
    assert prepared.revision_sha256 == content_hash(dict(cem=prepared.hashes['CEM'],
        pdm=prepared.hashes['PDM'], manifest=prepared.model_manifest))


def test_physical_warnings_still_block_publication(bundle):
    _, _, inputs = bundle
    inputs['result']['pdm']['validation_results'] = [{'severity': 'WARNING'}]
    with pytest.raises(PersistenceError, match='Physical violations'):
        prepare_outputs(**inputs)


def test_projection_transforms_preserve_separate_identity_namespaces(bundle):
    _, _, inputs = bundle
    pdm = inputs['result']['pdm']
    pdm['rails'] = [dict(id='BACKPLATE', x=1, y=2, z=3)]
    pdm['accessories'] = [dict(id='BACKPLATE', position=dict(x=4, y=5, z=6))]
    prepared = prepare_outputs(**inputs)
    assert prepared.transforms[('BACKPLATE', 'BACKPLATE')]['translation_mm'] == [30, 40, 20]
    assert prepared.transforms[('rails', 'BACKPLATE')]['translation_mm'] == [1, 2, 3]
    assert prepared.transforms[('accessories', 'BACKPLATE')]['translation_mm'] == [4, 5, 6]


def read_bundle(db, rid):
    with db.sessions() as s:
        manifest = dict(s.execute(select(m.revision_output_manifests).where(
            m.revision_output_manifests.c.project_revision_id == rid)).mappings().one())
        snapshots = {r['output_kind']: dict(r) for r in s.execute(select(m.revision_output_snapshots).where(
            m.revision_output_snapshots.c.project_revision_id == rid)).mappings()}
        files = [dict(r) for r in s.execute(select(m.generated_artifacts).where(
            m.generated_artifacts.c.project_revision_id == rid)).mappings()]
        return manifest, snapshots, files


def test_each_database_write_rolls_back_and_publication_has_no_engine_work(api, postgres_database, monkeypatch, request):
    db = postgres_database
    service = ProjectService(db)
    p = create(api)
    # Use a bounded real DB engineering design, including terminals, nets, routes,
    # validation, mechanical hardware and both generated file formats.
    design = service.generate(p['id'], {'num_feeders': 4}, p['lock_version'])
    project, template, *_ = service._inputs(p['id'])
    reqs = service.validate(template, project['id'], project['requirements'])
    manifest, snapshots, files = read_bundle(db, identifier(design['revision_id']))
    verify_outputs(manifest['manifest'], manifest['sha256'], snapshots, files, service.assets)
    for kind, response_key in [('CEM', 'cem'), ('PDM', 'pdm'), ('SCHEMATIC', 'schematic'), ('BOM', 'bom'), ('CAD', 'cad')]:
        assert snapshots[kind]['snapshot'] == design[response_key]
    assert snapshots['REQUIREMENTS']['snapshot'] == reqs.model_dump(mode='json')
    assert snapshots['INPUTS_AND_PINS']['snapshot']['pins']['generator'] == design['manifest']['generator']
    files = [{key: row[key] for key in ('artifact_type', 'file_format', 'storage_backend',
              'storage_key', 'sha256', 'byte_size', 'generator_name', 'generator_version')} for row in files]
    outputs = prepare_outputs(project, reqs, project['requirements'], design, design['manifest'],
        files, project['_source_document'], service.assets, project['lock_version'])

    def forbidden(*args, **kwargs):
        raise AssertionError('Engineering/hash/file work inside publication')

    # Scoped only around writer calls. Reading APIs remain P1-T05's separate task.
    from app.persistence import assets, revision_outputs
    from app.services.cad_engine import CADEngine
    from app.services.schematic_engine import SchematicEngine
    from app.services.validation_engine import ValidationEngine
    from app.services.orchestrator import DesignOrchestrator
    from app.algorithms.duct_routing import DuctRouter

    class InjectedFailure(RuntimeError):
        pass

    counts = dict(writes=0, fail_at=None, tables=set())

    def after_write(conn, cursor, statement, parameters, context, executemany):
        if context.isinsert or context.isupdate or context.isdelete:
            counts['writes'] += 1
            counts['tables'].add(context.compiled.statement.table.name)
            if counts['writes'] == counts['fail_at']:
                raise InjectedFailure('after write '+str(counts['writes']))

    def publish():
        with monkeypatch.context() as guard:
            for target, name in [(assets, 'content_hash'), (revision_outputs, 'content_hash'),
                (AssetStore, 'put'), (AssetStore, 'verified_path'),
                (CADEngine, 'generate_parametric_geometry'), (CADEngine, 'export_freecad_script'),
                (SchematicEngine, 'generate_schematic_data'), (ValidationEngine, 'validate_pdm'),
                (DesignOrchestrator, 'generate_design'), (DuctRouter, 'route_layout')]:
                guard.setattr(target, name, forbidden)
            with db.sessions.begin() as s:
                result = write_revision(s, project, template, reqs, project['requirements'], design,
                    design['manifest'], files, project['lock_version'], outputs=outputs)
                # Baseline records every write, including the final current pointer.
                if counts['fail_at'] is None:
                    raise InjectedFailure('baseline rollback')
                return result

    # Compare all table cardinalities plus exact project/draft/source/prior bundle
    # values after every failure. No partial projection/artifact row can survive.
    def state():
        with db.sessions() as s:
            table_counts = tuple(s.execute(select(*[
                select(func.count()).select_from(table).scalar_subquery().label(name)
                for name, table in sorted(m.metadata.tables.items())])).one())
            row = ProjectRepository(s).row(p['id'])
            drafts = [dict(r) for r in s.execute(select(m.project_requirements).where(
                m.project_requirements.c.project_id == row['id']).order_by(m.project_requirements.c.id)).mappings()]
            source = [dict(r) for r in s.execute(select(m.design_documents).where(
                m.design_documents.c.project_id == row['id'])).mappings()]
        return table_counts, row, drafts, source, read_bundle(db, identifier(design['revision_id']))

    before = state()
    event.listen(db.engine, 'after_cursor_execute', after_write)
    try:
        with pytest.raises(InjectedFailure):
            publish()
        total = counts['writes']
        request.node.user_properties.append(('publication_writes_injected', str(total)))
        assert {'projects', 'revision_output_manifests', 'revision_output_snapshots', 'generated_artifacts',
                'cem_snapshots', 'pdm_snapshots', 'pdm_routes', 'validation_results'} <= counts['tables']
        for index in range(1, total + 1):
            counts.update(writes=0, fail_at=index)
            with pytest.raises(InjectedFailure):
                publish()
            assert state() == before, 'partial publication after write '+str(index)
        counts.update(writes=0, fail_at=total+1)
        saved = publish()
    finally:
        event.remove(db.engine, 'after_cursor_execute', after_write)
    assert saved['revision_no'] == 2
    with db.sessions() as s:
        assert str(ProjectRepository(s).row(p['id'])['current_revision_id']) == saved['revision_id']
    manifest, snapshots, files = read_bundle(db, identifier(saved['revision_id']))
    verify_outputs(manifest['manifest'], manifest['sha256'], snapshots, files, service.assets)
    print(f'Failure injection verified after every one of {total} publication writes.')


def test_project_and_document_fences_reject_prepared_outputs(api, postgres_database):
    service = ProjectService(postgres_database)
    p = create(api)
    design = service.generate(p['id'], {'num_feeders': 4}, p['lock_version'])
    project, template, *_ = service._inputs(p['id'])
    reqs = service.validate(template, project['id'], project['requirements'])
    files = service.generate_files(design)
    outputs = prepare_outputs(project, reqs, project['requirements'], design, design['manifest'],
        files, project['_source_document'], service.assets, project['lock_version'])
    for prepared, expected_code in [
        (replace(outputs, manifest={**outputs.manifest, 'source_document': {
            **outputs.manifest['source_document'], 'sequence': 999}}), 'DOCUMENT_CONFLICT'),
        (outputs, 'REVISION_CONFLICT')]:
        if expected_code == 'REVISION_CONFLICT':
            checked(api.patch('/api/projects/'+p['id'], json={
                'expected_version': project['lock_version'], 'name': 'Concurrent save'}))
        with pytest.raises(PersistenceError) as caught:
            with postgres_database.sessions.begin() as s:
                write_revision(s, project, template, reqs, project['requirements'], design, design['manifest'],
                    files, project['lock_version'], outputs=prepared)
        assert caught.value.code == expected_code
    assert len(checked(api.get('/api/projects/'+p['id']+'/revisions'))) == 1


def test_generate_restore_and_import_prepare_before_database_writes(api, postgres_database, monkeypatch):
    from app.models.api import ProjectImport
    from app.services.project_lifecycle import ProjectLifecycle
    from app.services.cad_engine import CADEngine
    from app.services.schematic_engine import SchematicEngine
    from app.services.validation_engine import ValidationEngine
    from app.services import project_service, project_lifecycle
    from app.persistence import revision_outputs

    service = ProjectService(postgres_database)
    p = create(api)
    writing = set()

    def track(conn, cursor, statement, parameters, context, executemany):
        if context.isinsert or context.isupdate or context.isdelete:
            writing.add(conn)

    def clear(conn):
        writing.discard(conn)

    def wrap(original):
        def outside(*args, **kwargs):
            assert not writing, 'Output preparation during database writes'
            return original(*args, **kwargs)
        return outside

    for target, name in [(AssetStore, 'put'), (AssetStore, 'verified_path'),
        (CADEngine, 'generate_parametric_geometry'), (CADEngine, 'export_freecad_script'),
        (SchematicEngine, 'generate_schematic_data'), (ValidationEngine, 'validate_pdm'),
        (project_service, 'content_hash'), (project_lifecycle, 'content_hash'),
        (revision_outputs, 'content_hash')]:
        monkeypatch.setattr(target, name, wrap(getattr(target, name)))
    event.listen(postgres_database.engine, 'after_cursor_execute', track)
    event.listen(postgres_database.engine, 'commit', clear)
    event.listen(postgres_database.engine, 'rollback', clear)
    try:
        design = service.generate(p['id'], {'num_feeders': 4}, p['lock_version'])
        restored = service.restore(p['id'], design['revision_id'], design['lock_version'])
        assert restored['revision_no'] == 2
        lifecycle = ProjectLifecycle(service)
        package = lifecycle.export(p['id'])
        imported = lifecycle.import_project(ProjectImport(**package))
        for key in (p['id'], imported['id']):
            with postgres_database.sessions() as s:
                revisions = ProjectRepository(s).revisions(key)
            assert len(revisions) == 2
            for revision in revisions:
                manifest, snapshots, files = read_bundle(postgres_database, identifier(revision['id']))
                verify_outputs(manifest['manifest'], manifest['sha256'], snapshots, files, service.assets)
    finally:
        event.remove(postgres_database.engine, 'after_cursor_execute', track)
        event.remove(postgres_database.engine, 'commit', clear)
        event.remove(postgres_database.engine, 'rollback', clear)
