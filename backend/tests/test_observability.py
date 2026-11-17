import io
import json
import logging
from uuid import uuid4

from fastapi import Body
from tests.local_client import LocalClient as TestClient
import pytest

from app.main import create_app
from app.observability import (DiagnosticFormatter, DiagnosticSettings, bind,
    correlation, emit, span, configure, public)
from app.services.design_errors import DesignError
from app.jobs.worker import run_bounded, WorkerFailure

HOSTILE = 'postgresql://alice:credential-123@host/db password=hunter2 /home/private/source.py C:\\private\\source.py'


def child_context():
    return correlation()


def child_failure():
    raise RuntimeError(HOSTILE)


def test_real_spawn_receives_correlation_and_failure_is_safe(diagnostics):
    ids = dict(request_id=str(uuid4()), document_id=str(uuid4()),
               job_id=str(uuid4()), stage_id='placement')
    with bind(**ids):
        assert run_bounded(child_context) == ids
        with pytest.raises(WorkerFailure):
            run_bounded(child_failure)
    rows = [json.loads(line) for line in diagnostics.getvalue().splitlines()]
    failed = next(r for r in rows if r.get('status') == 'failed')
    assert failed['job_id'] == ids['job_id'] and failed['stage_id'] == 'placement'
    assert failed['code'] == 'WORKER_FAILED'
    assert 'credential-123' not in diagnostics.getvalue()


@pytest.fixture
def diagnostics():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(DiagnosticFormatter())
    logger = logging.getLogger('panel.execution')
    old = logger.level
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    yield stream
    logger.removeHandler(handler)
    logger.setLevel(old)


def test_failed_execution_correlates_and_drops_payload(diagnostics):
    ids = {k: str(uuid4()) for k in ('request_id', 'project_id', 'document_id', 'operation_id', 'job_id')}
    with bind(**ids), pytest.raises(DesignError):
        with span('stage', stage_id='placement'):
            emit('diagnostic', credentials=HOSTILE, requirement='private customer requirement')
            raise DesignError('PLACEMENT_FAILED', HOSTILE, {'requirements': 'private customer requirement'})
    rows = [json.loads(line) for line in diagnostics.getvalue().splitlines()]
    failed = rows[-1]
    assert {key: failed[key] for key in ids} == ids
    assert failed['stage_id'] == 'placement'
    assert failed['code'] == 'PLACEMENT_FAILED' and failed['elapsed_ms'] >= 0
    assert 'credential-123' not in diagnostics.getvalue()
    assert 'private customer' not in diagnostics.getvalue()
    assert correlation() == {}


def test_normal_diagnostics_never_format_messages_exceptions_or_extras():
    record = logging.LogRecord('sqlalchemy.engine', logging.ERROR, '/private/file', 1,
        '%s SELECT * FROM secret WHERE password=:password', (HOSTILE,), None)
    record.exc_text = HOSTILE
    record.stack_info = HOSTILE
    record.parameters = {'password': HOSTILE}
    assert json.loads(DiagnosticFormatter().format(record))['event'] == 'diagnostic'
    assert 'private' not in DiagnosticFormatter().format(record)
    assert 'credential-123' not in DiagnosticFormatter().format(record)
    record.name = 'panel.execution'
    record.diagnostic = HOSTILE
    assert 'credential-123' not in DiagnosticFormatter().format(record)
    assert 'hunter2' not in json.dumps(public({HOSTILE: 'value', 'reason': "[parameters: {'password': 'hunter2'}]"}))


def test_durable_failed_stage_joins_request_operation_and_job(api, postgres_database, diagnostics, monkeypatch):
    from sqlalchemy import select
    from app.jobs.runner import StageExecutor
    from app.persistence import models as m
    from app.services.document_service import DocumentService
    from app.services.project_service import ProjectService
    from app.services.recompute import materialize
    from app.services.stages.cache import make_signature
    from tests.test_postgres import create
    api.app.state.cad_executor.shutdown()
    project = create(api)
    source = DocumentService(postgres_database).load(project['id'])
    base, inputs = materialize(ProjectService(postgres_database), source)
    signature = make_signature('requirements', inputs.requirements, base.document.pins,
                               context=inputs.requirements.context)
    def fail(*args, **kwargs):
        raise DesignError('CONTROLLED_STAGE_FAILURE', HOSTILE, {'requirements': 'customer confidential'})
    monkeypatch.setattr('app.jobs.runner.run_bounded', fail)
    ids = dict(request_id=str(uuid4()), operation_id=str(uuid4()))
    with bind(**ids), pytest.raises(DesignError):
        StageExecutor(postgres_database, source)('requirements', inputs.requirements, signature)
    with postgres_database.sessions() as session:
        job = session.execute(select(m.jobs).where(
            m.jobs.c.document_id == source.document.document_id)).mappings().one()
    assert job['state'] == 'FAILED' and 'credential-123' not in json.dumps(job['error'])
    rows = [json.loads(line) for line in diagnostics.getvalue().splitlines()]
    failed = next(row for row in rows if row['event'] == 'job_failed' and row['job_id'] == str(job['id']))
    assert all(failed[key] == value for key, value in ids.items())
    assert failed['document_id'] == source.document.document_id
    assert failed['stage_id'] == 'requirements'
    assert any(row['event'] == 'job' and row.get('status') == 'failed' and
               row.get('elapsed_ms', -1) >= 0 and row.get('job_id') == str(job['id']) for row in rows)
    assert 'customer confidential' not in diagnostics.getvalue() and 'credential-123' not in diagnostics.getvalue()


def test_public_errors_redact_and_validation_does_not_echo_input():
    app = create_app()
    @app.get('/failure')
    def failure():
        raise DesignError('TEST_FAILURE', HOSTILE, {'password': HOSTILE,
            'requirements': 'sensitive customer text', 'SQL parameters': HOSTILE}, [HOSTILE])
    @app.post('/validation')
    def validation(value: int = Body()):
        return value
    @app.get('/unexpected')
    def unexpected():
        raise RuntimeError(HOSTILE)
    with TestClient(app, raise_server_exceptions=False) as client:
        failure = client.get('/failure')
        assert failure.status_code == 422
        assert failure.headers['x-request-id']
        assert failure.json()['error']['correlation']['request_id'] == failure.headers['x-request-id']
        invalid = client.post('/validation', json={'value': HOSTILE})
        assert invalid.status_code == 422
        unexpected = client.get('/unexpected')
        assert unexpected.status_code == 500 and unexpected.headers['x-request-id']
        for response in (failure, invalid, unexpected):
            assert all(secret not in response.text for secret in
                ('credential-123', 'hunter2', '/home/private', 'C:\\private', 'sensitive customer text'))


def test_retention_is_bounded_and_private(tmp_path, monkeypatch):
    monkeypatch.setenv('PANEL_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('PANEL_DIAGNOSTIC_MAX_BYTES', '1024')
    monkeypatch.setenv('PANEL_DIAGNOSTIC_BACKUPS', '2')
    handler, previous = configure()
    try:
        for _ in range(150):
            emit('request', request_id=uuid4())
        files = list((tmp_path/'diagnostics').iterdir())
        assert len(files) == 3
        assert all(f.stat().st_size <= 1024 and f.stat().st_mode & 0o077 == 0 for f in files)
    finally:
        logging.getLogger().handlers = previous
        handler.close()
    for name, value in [('PANEL_DIAGNOSTIC_MAX_BYTES', '999999999'), ('PANEL_DIAGNOSTIC_BACKUPS', '0')]:
        monkeypatch.setenv(name, value)
        with pytest.raises(ValueError, match='bounded diagnostic'):
            DiagnosticSettings.load()
