"""Storage qualification only; no document API or publication implementation."""
from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4

from alembic import command
import pytest
from sqlalchemy import create_engine, func, insert, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.models.document import DocumentSnapshots, ResolvedDocument, snapshot_sha256
from app.persistence import models as m
from app.persistence.assets import content_hash
from app.persistence.database import Database
from app.persistence.manage import alembic_config, initialize
from app.persistence.schema_tools import signature, verify_baseline

HEAD = '0008_jobs'
NEW_TABLES = {'design_documents', 'design_document_snapshots',
              'revision_output_manifests', 'revision_output_snapshots',
              'operation_batches', 'document_operations', 'stage_results', 'document_stage_states', 'jobs'}
FIXTURE = Path(__file__).resolve().parents[2] / 'frontend/src/types/fixtures/document-v1.json'


@contextmanager
def isolated_database(settings):
    """Only a freshly allocated, fixture-owned database can be modified here."""
    name = 'panel_integration_test_' + uuid4().hex
    admin = create_engine(settings.url.set(database='postgres'),
                          isolation_level='AUTOCOMMIT', hide_parameters=True)
    database = None
    created = False
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
        created = True
        database = Database(replace(settings, url=settings.url.set(database=name)))
        yield database
    finally:
        if database is not None:
            database.close()
        if created:
            with admin.connect() as conn:
                conn.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
                assert not conn.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'), {'name': name})
        admin.dispose()


def row_images(engine, tables):
    """Compare PostgreSQL's text bytes for every pre-existing row, not just counts."""
    with engine.connect() as conn:
        return {table: sorted(row[0].encode('utf-8') for row in conn.exec_driver_sql(
            f'SELECT row_to_json(record)::text FROM "{table}" AS record')) for table in sorted(tables)}


def test_fresh_and_0004_upgrade_match_without_rewriting_history(postgres_database):
    with isolated_database(postgres_database.settings) as fresh, isolated_database(postgres_database.settings) as upgrade:
        fresh_cfg = alembic_config(fresh.settings.url)
        upgrade_cfg = alembic_config(upgrade.settings.url)
        initialize(fresh)
        # The baseline manifest must remain the frozen 0001 signature.
        command.upgrade(upgrade_cfg, '0001_baseline')
        verify_baseline(upgrade.engine)
        command.upgrade(upgrade_cfg, '0004_projects')
        assert not upgrade.ready()
        project, revision = uuid4(), uuid4()
        cem = {'project_id': str(project), 'panel_id': 'Legacy-Panel', 'label': 'DB café',
               'components': [{'id': 'QF001', 'x': 125.5}]}
        pdm = {'project_id': str(project), 'mounting_plate_x': 25, 'components': []}
        manifest = {'engine_version': 'legacy-preserved', 'opaque': {'exact': '001.00'}}
        revision_hash = content_hash({'cem': content_hash(cem), 'pdm': content_hash(pdm), 'manifest': manifest})
        with upgrade.engine.begin() as conn:
            conn.execute(insert(m.projects).values(id=project, name='Legacy unchanged', lock_version=8,
                recovery_version=3, workspace={'editorTransforms': {'QF001': {'x': 125.5}}},
                recovery={'unfinished': 'keep me'}))
            conn.execute(insert(m.project_revisions).values(id=revision, project_id=project, revision_no=1,
                status='PUBLISHED', schema_version=1, model_manifest=manifest, content_sha256=revision_hash))
            for table, snapshot in ((m.cem_snapshots, cem), (m.pdm_snapshots, pdm)):
                conn.execute(insert(table).values(project_revision_id=revision, schema_version=1,
                    snapshot=snapshot, sha256=content_hash(snapshot)))
            conn.execute(m.projects.update().where(m.projects.c.id == project).values(current_revision_id=revision))
        old_tables = set(inspect(upgrade.engine).get_table_names()) - {'alembic_version'}
        before = row_images(upgrade.engine, old_tables)
        command.upgrade(upgrade_cfg, 'head')
        assert row_images(upgrade.engine, old_tables) == before
        assert signature(fresh.engine) == signature(upgrade.engine)
        assert set(inspect(upgrade.engine).get_table_names()) - old_tables - {'alembic_version'} == NEW_TABLES
        with upgrade.engine.connect() as conn:
            assert conn.scalar(text('SELECT version_num FROM alembic_version')) == HEAD
            assert conn.scalar(select(m.project_revisions.c.content_sha256).where(m.project_revisions.c.id == revision)) == revision_hash
            for name in NEW_TABLES:
                assert conn.scalar(select(func.count()).select_from(m.metadata.tables[name])) == 0
        assert fresh.ready() and upgrade.ready()
        command.check(fresh_cfg)
        command.check(upgrade_cfg)
        # Reapplying head neither changes old data nor invents legacy outputs.
        command.upgrade(upgrade_cfg, 'head')
        assert row_images(upgrade.engine, old_tables) == before


def stored_document(project_id):
    payload = json.loads(FIXTURE.read_text(encoding='utf-8'))
    payload['document'].update(project_id=str(project_id), document_id='document-' + uuid4().hex,
                               document_sequence=0, lock_version=1)
    for kind, snapshot in payload['snapshots'].items():
        if snapshot is not None:
            snapshot['project_id'] = str(project_id)
    snapshots = DocumentSnapshots.model_validate(payload['snapshots'])
    for kind in payload['snapshots']:
        payload['document']['models'][kind]['sha256'] = snapshot_sha256(getattr(snapshots, kind))
    resolved = ResolvedDocument.model_validate(payload)
    document = resolved.document.model_dump(mode='json')
    # The source engineering digest excludes independent clocks and pointers.
    digest = content_hash({key: document[key] for key in
        ('configuration', 'models', 'pins', 'provenance', 'enclosure_interfaces', 'dirty_stages')})
    return dict(id=document['document_id'], project_id=project_id, panel_id=document['panel_id'],
                schema_version=document['schema_version'], document_sequence=0,
                document=document, content_sha256=digest), resolved


def test_document_and_complete_output_storage_round_trip(postgres_database):
    project, revision = uuid4(), uuid4()
    values, resolved = stored_document(project)
    document_id = values['id']
    outputs = {kind.upper(): snapshot for kind, snapshot in resolved.snapshots.model_dump(mode='json').items()}
    outputs.update(DOCUMENT=values['document'], BOM=[{'component_id': 'QF001', 'quantity': 1}],
                   CAD={'descriptors': [], 'artifacts': []}, VALIDATION={'status': 'UNRESOLVED'},
                   INPUTS_AND_PINS={'configuration': {}, 'pins': values['document']['pins']})
    manifest = dict(schema_version='1.0.0', revision_id=str(revision),
        source_document_id=document_id, source_document_sequence=0,
        outputs={key.lower(): {'schema_version': 1, 'sha256': content_hash(value)} for key, value in outputs.items()})
    with postgres_database.engine.begin() as conn:
        conn.execute(insert(m.projects).values(id=project, name='Document storage fixture'))
        conn.execute(insert(m.design_documents).values(**values))
        for kind, snapshot in resolved.snapshots.model_dump(mode='json').items():
            conn.execute(insert(m.design_document_snapshots).values(document_id=document_id,
                model_kind=kind.upper(), schema_version=1, sha256=content_hash(snapshot), snapshot=snapshot))
        conn.execute(insert(m.project_revisions).values(id=revision, project_id=project, revision_no=1, status='DRAFT'))
        conn.execute(insert(m.revision_output_manifests).values(project_revision_id=revision, project_id=project,
            source_document_id=document_id, source_document_sequence=0, source_document_sha256=values['content_sha256'],
            manifest=manifest, sha256=content_hash(manifest)))
        for kind, snapshot in outputs.items():
            conn.execute(insert(m.revision_output_snapshots).values(project_revision_id=revision,
                output_kind=kind, schema_version=1, snapshot=snapshot, sha256=content_hash(snapshot)))
    # A new connection reopens the stored contract without engines or adapters.
    with postgres_database.engine.connect() as conn:
        document = conn.scalar(select(m.design_documents.c.document).where(m.design_documents.c.id == document_id))
        rows = conn.execute(select(m.design_document_snapshots).where(
            m.design_document_snapshots.c.document_id == document_id)).mappings().all()
        snapshots = {row['model_kind'].lower(): row['snapshot'] for row in rows}
        assert ResolvedDocument.model_validate(dict(document=document, snapshots=snapshots)) == resolved
        for row in rows:
            assert content_hash(row['snapshot']) == row['sha256']
        saved = conn.execute(select(m.revision_output_manifests).where(
            m.revision_output_manifests.c.project_revision_id == revision)).mappings().one()
        assert saved['manifest'] == manifest and content_hash(saved['manifest']) == saved['sha256']
        frozen = conn.execute(select(m.revision_output_snapshots).where(
            m.revision_output_snapshots.c.project_revision_id == revision)).mappings().all()
        assert {row['output_kind']: row['snapshot'] for row in frozen} == outputs
        assert all(row['sha256'] == content_hash(row['snapshot']) for row in frozen)


def test_storage_rejects_invalid_versions_shapes_and_cross_project_links(postgres_database):
    from tests.integrity_support import privileged_connection
    project, other_project, revision, other_revision = (uuid4() for _ in range(4))
    values, _ = stored_document(project)
    other_values, _ = stored_document(other_project)
    manifest = dict(project_revision_id=revision, project_id=project, source_document_id=values['id'],
        source_document_sequence=0, source_document_sha256='a' * 64, manifest={}, sha256='b' * 64)
    snapshot = dict(document_id=values['id'], model_kind='CEM', schema_version=1, sha256='c' * 64, snapshot={})
    output = dict(project_revision_id=revision, output_kind='BOM', schema_version=1, sha256='d' * 64, snapshot=[])
    # Exercise database constraints independently of the runtime mutation guard.
    with privileged_connection(postgres_database) as conn:
        conn.execute(insert(m.projects), [{'id': project, 'name': 'Storage constraints'},
                                         {'id': other_project, 'name': 'Other project'}])
        conn.execute(insert(m.project_revisions), [dict(id=revision, project_id=project, revision_no=1, status='DRAFT'),
            dict(id=other_revision, project_id=other_project, revision_no=1, status='DRAFT')])
        # Each rejection rolls back its own savepoint, leaving the valid fixture usable.
        def rejected(table, data):
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(insert(table).values(**data))

        for invalid in ({'document_sequence': -1}, {'content_sha256': 'bad'}, {'document': []},
                        {'schema_version': ''}, {'document': {}}, {'base_revision_id': other_revision}):
            rejected(m.design_documents, {**values, **invalid})
        conn.execute(insert(m.design_documents).values(**values, base_revision_id=revision))
        conn.execute(insert(m.design_documents).values(**other_values))
        duplicate, _ = stored_document(project)
        rejected(m.design_documents, duplicate)
        for invalid in ({'schema_version': 0}, {'sha256': 'bad'}, {'snapshot': []},
                        {'model_kind': 'UNKNOWN'}, {'document_id': 'missing'}):
            rejected(m.design_document_snapshots, {**snapshot, **invalid})
        conn.execute(insert(m.design_document_snapshots).values(**snapshot))
        rejected(m.design_document_snapshots, snapshot)
        for invalid in ({'source_document_sequence': -1}, {'sha256': 'bad'}, {'source_document_sha256': 'bad'},
                        {'manifest': []}, {'schema_version': ''}, {'project_id': other_project},
                        {'source_document_id': other_values['id']}, {'project_revision_id': other_revision}):
            rejected(m.revision_output_manifests, {**manifest, **invalid})
        rejected(m.revision_output_snapshots, output)  # No manifest yet.
        conn.execute(insert(m.revision_output_manifests).values(**manifest))
        rejected(m.revision_output_manifests, manifest)
        for invalid in ({'schema_version': 0}, {'sha256': 'bad'}, {'snapshot': None},
                        {'snapshot': 'scalar'}, {'output_kind': 'UNKNOWN'}):
            rejected(m.revision_output_snapshots, {**output, **invalid})
        conn.execute(insert(m.revision_output_snapshots).values(**output))
        rejected(m.revision_output_snapshots, output)
        for table, condition in ((m.projects, m.projects.c.id == project),
                                 (m.project_revisions, m.project_revisions.c.id == revision),
                                 (m.design_documents, m.design_documents.c.id == values['id']),
                                 (m.revision_output_manifests, m.revision_output_manifests.c.project_revision_id == revision)):
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(table.delete().where(condition))
