"""Historical reads are independent of installed generators and model defaults."""
from copy import deepcopy

import pytest
from sqlalchemy import delete, select, update

from app.persistence import models as m
from app.persistence.assets import canonical_json, content_hash
from app.persistence.repositories import identifier
from app.persistence.repositories import PersistenceError
from app.services.project_service import ProjectService
from app.services.revision_reader import RevisionReader
from tests.test_postgres import checked, create


def disable_generators(monkeypatch):
    from app.services import project_service, panel_assembly
    from app.services.cad_engine import CADEngine
    from app.services.schematic_engine import SchematicEngine
    from app.persistence import assets

    def forbidden(*args, **kwargs):
        raise AssertionError('Historical read invoked an installed generator')

    for target, name in [(SchematicEngine, 'generate_schematic_data'),
                         (CADEngine, 'generate_parametric_geometry'),
                         (CADEngine, 'export_freecad_script'),
                         (project_service, 'assembly_bom'), (panel_assembly, 'assembly_bom'),
                         (project_service, 'primitive_glb'), (assets, 'primitive_glb'),
                         (ProjectService, 'generate_files')]:
        monkeypatch.setattr(target, name, forbidden)
    monkeypatch.setattr(project_service, 'ENGINE_VERSION', 'unavailable-future-engine')


def test_historical_reads_use_exact_snapshots_and_original_artifacts(api, postgres_database, monkeypatch):
    service = ProjectService(postgres_database)
    project = create(api)
    first = service.generate(project['id'], {'num_feeders': 4}, project['lock_version'])
    second = service.generate(project['id'], {'num_feeders': 5}, first['lock_version'])
    assert not any(second[k] for k in ('is_non_current', 'is_input_stale', 'is_version_incompatible'))
    root = '/api/projects/'+project['id']
    originals = {a['id']: api.get(a['url']).content for a in first['artifacts']}
    disable_generators(monkeypatch)
    frozen = checked(api.get(root+'/revisions/'+first['revision_id']))
    assert frozen['is_non_current'] and frozen['is_input_stale'] and frozen['is_version_incompatible']
    assert frozen['output_status'] == 'COMPLETE' and not frozen['missing_outputs']
    assert frozen['output_manifest_sha256'] == first['output_manifest_sha256']
    assert frozen['snapshot_sha256'] == first['snapshot_sha256']
    for field in ('cem', 'pdm', 'schematic', 'cad', 'bom', 'validation_errors'):
        assert canonical_json(frozen[field]) == canonical_json(first[field])
    for artifact in frozen['artifacts']:
        assert api.get(artifact['url']).content == originals[artifact['id']]
    params = {'revision_id': first['revision_id']}
    assert checked(api.get(root+'/schematic', params=params)) == first['schematic']
    assert checked(api.get(root+'/cad', params=params)) == first['cad']
    script = checked(api.get(root+'/cad/freecad-script', params=params))
    original_script = next(originals[a['id']] for a in first['artifacts'] if a['file_format'] == 'PY')
    assert script['script'].encode('utf-8') == original_script
    current = checked(api.get(root+'/design'))
    assert not current['is_non_current'] and not current['is_input_stale']
    assert current['is_version_incompatible']
    assert current['revision_id'] == second['revision_id']
    # Export is also a read; it must not reconstruct the history.
    assert len(checked(api.get(root+'/export'))['revisions']) == 2
    checked(api.patch(root, json={'expected_version': second['lock_version'],
                                 'requirements': {'num_feeders': 4}}))
    historical = checked(api.get(root+'/revisions/'+first['revision_id']))
    current = checked(api.get(root+'/design'))
    assert historical['is_non_current'] and not historical['is_input_stale']
    assert not current['is_non_current'] and current['is_input_stale']


def make_legacy(db, rid):
    """Construct a pre-bundle fixture; application code never edits history."""
    rid = identifier(rid)
    with db.sessions.begin() as session:
        revision = session.execute(select(m.project_revisions).where(m.project_revisions.c.id == rid)).mappings().one()
        manifest = deepcopy(revision['model_manifest'])
        manifest.pop('output_manifest_sha256')
        hashes = [session.scalar(select(table.c.sha256).where(table.c.project_revision_id == rid))
                  for table in (m.cem_snapshots, m.pdm_snapshots)]
        session.execute(delete(m.revision_output_snapshots).where(m.revision_output_snapshots.c.project_revision_id == rid))
        session.execute(delete(m.revision_output_manifests).where(m.revision_output_manifests.c.project_revision_id == rid))
        session.execute(update(m.project_revisions).where(m.project_revisions.c.id == rid).values(
            model_manifest=manifest, content_sha256=content_hash(dict(cem=hashes[0], pdm=hashes[1], manifest=manifest))))


def test_legacy_reads_never_invent_outputs_and_conversion_is_explicit(api, postgres_database, monkeypatch):
    service = ProjectService(postgres_database)
    project = create(api)
    first = service.generate(project['id'], {'num_feeders': 4}, project['lock_version'])
    make_legacy(postgres_database, first['revision_id'])
    root = '/api/projects/'+project['id']
    with monkeypatch.context() as context:
        disable_generators(context)
        legacy = checked(api.get(root+'/revisions/'+first['revision_id']))
        assert legacy['output_status'] == 'MISSING_OUTPUTS'
        assert {'SCHEMATIC', 'BOM', 'CAD', 'VALIDATION'} <= set(legacy['missing_outputs'])
        assert legacy['schematic'] is legacy['cad'] is legacy['bom'] is None
        assert legacy['compatibility_conversion_available']
        assert legacy['cem'] == first['cem'] and legacy['pdm'] == first['pdm']
        assert api.get(root+'/schematic').status_code == 409
        assert api.get(root+'/cad').status_code == 409
        # The original script is still usable even without a complete bundle.
        assert checked(api.get(root+'/cad/freecad-script'))['script']
        assert api.post(root+'/revisions/'+first['revision_id']+'/restore', json={
            'expected_version': first['lock_version']}).status_code == 409
    converted = checked(api.post(root+'/revisions/'+first['revision_id']+'/compatibility-conversion',
        json={'expected_version': first['lock_version']}), 201)
    assert converted['output_status'] == 'COMPLETE' and converted['revision_id'] != first['revision_id']
    assert converted['manifest']['compatibility_converted_from_revision_id'] == first['revision_id']
    reread = checked(api.get(root+'/revisions/'+first['revision_id']))
    assert reread['snapshot_sha256'] == legacy['snapshot_sha256']
    assert reread['missing_outputs'] == legacy['missing_outputs']
    assert len(checked(api.get(root+'/revisions'))) == 2


def test_missing_anchored_manifest_is_corruption(api, postgres_database):
    service = ProjectService(postgres_database)
    project = create(api)
    design = service.generate(project['id'], {'num_feeders': 4}, project['lock_version'])
    with postgres_database.sessions.begin() as session:
        session.execute(delete(m.revision_output_snapshots).where(
            m.revision_output_snapshots.c.project_revision_id == identifier(design['revision_id'])))
        session.execute(delete(m.revision_output_manifests).where(
            m.revision_output_manifests.c.project_revision_id == identifier(design['revision_id'])))
    response = api.get('/api/projects/'+project['id']+'/design')
    assert response.status_code == 409
    assert 'REVISION_OUTPUT_INTEGRITY' in response.text


def test_revision_status_contract_openapi():
    from app.main import create_app
    schema = create_app().openapi()['components']['schemas']['DesignPackage']
    assert {'is_non_current', 'is_input_stale', 'is_version_incompatible', 'missing_outputs',
            'output_manifest_sha256', 'compatibility_conversion_available'} <= set(schema['required'])
    assert schema['properties']['output_status']['enum'] == ['COMPLETE', 'MISSING_OUTPUTS']
    assert {'type': 'null'} in schema['properties']['bom']['anyOf']


def test_complete_publication_without_script_does_not_substitute_later_jobs(monkeypatch):
    # No database is available: looking for subsequent jobs would fail this test.
    reader = RevisionReader(None, None, 'test')
    monkeypatch.setattr(reader, 'read', lambda *args: {
        'output_manifest': {'artifacts': []}, 'revision_id': 'frozen'})
    with pytest.raises(PersistenceError) as caught:
        reader.freecad_script('project', 'frozen')
    assert caught.value.code == 'REVISION_OUTPUT_MISSING'
