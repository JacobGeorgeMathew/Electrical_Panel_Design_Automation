"""Bounded diagnostics: identifiers and outcomes only, never workload payloads.

Opaque non-UUID identifiers are hashed, preserving correlation without allowing
labels/requirements to become a logging channel. Raw log messages, args, extras,
tracebacks, SQL and exception text are deliberately excluded by the formatter.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import time
from uuid import UUID, uuid4

CONTEXT = ContextVar('execution_context', default={})
IDS = {'request_id', 'project_id', 'document_id', 'operation_id', 'batch_id',
       'job_id', 'parent_job_id', 'stage_id'}
STAGES = {'requirements', 'calculations', 'selection', 'connectivity', 'schematic',
          'enclosure', 'zoning', 'placement', 'ducts', 'routes', 'physical_validation', 'bom', 'cad'}
EVENTS = {'request', 'operation', 'stage', 'job', 'job_enqueued', 'job_failed',
          'job_succeeded', 'worker', 'runner_unavailable', 'diagnostic', 'public_error'}
logger = logging.getLogger('panel.execution')


def identity(value):
    if value is None:
        return None
    raw = str(value)
    try:
        return str(UUID(raw))
    except ValueError:
        return 'sha256:' + hashlib.sha256(raw.encode()).hexdigest()[:32]


def safe_code(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', value) else 'EXECUTION_FAILED'


def correlation():
    return dict(CONTEXT.get())


@contextmanager
def bind(**values):
    values = {k: (v if k == 'stage_id' and v in STAGES else identity(v))
              for k, v in values.items() if k in IDS and v is not None}
    token = CONTEXT.set({**CONTEXT.get(), **values})
    try:
        yield
    finally:
        CONTEXT.reset(token)


def emit(event, *, status=None, elapsed_ms=None, code=None, **ids):
    with bind(**ids):
        record = {'event': event if event in EVENTS else 'diagnostic', **correlation()}
    if status in {'started', 'succeeded', 'failed', 'cached', 'retained', 'rejected'}:
        record['status'] = status
    if elapsed_ms is not None:
        record['elapsed_ms'] = round(max(0, min(float(elapsed_ms), 86400000)), 3)
    if code is not None:
        record['code'] = safe_code(code)
    logger.info('execution', extra={'diagnostic': record})


@contextmanager
def span(event, **ids):
    with bind(**ids):
        started = time.perf_counter()
        outcome = {}
        emit(event, status='started')
        try:
            yield outcome
        except BaseException as exc:
            emit(event, status='failed', elapsed_ms=(time.perf_counter()-started)*1000,
                 code=getattr(exc, 'code', None) or 'EXECUTION_FAILED')
            raise
        else:
            emit(event, status=outcome.get('status', 'succeeded'), elapsed_ms=(time.perf_counter()-started)*1000)


def traced(event, fields):
    def decorate(call):
        @wraps(call)
        def run(*args, **kwargs):
            with span(event, **fields(*args, **kwargs)) as outcome:
                result = call(*args, **kwargs)
                # Runners intentionally catch workload failures after recording
                # durable failure. Their normal return must not imply job success.
                if event == 'job' and (result is None or result is False):
                    outcome['status'] = 'failed'
                return result
        return run
    return decorate


def operation_fields(self, key, request, *args, **kwargs):
    return dict(project_id=key, document_id=request.document_id,
                batch_id=getattr(request, 'batch_id', None))


# Public engineering errors retain useful structural detail, but never raw
# validation input/context, requirement answers, SQL, credentials or host paths.
SENSITIVE = re.compile(r'password|passwd|secret|token|authorization|cookie|credential|dsn|database_url|sql|parameters|requirements?|answers?|^input$|^ctx$|^value$', re.I)
SECRET_TEXT = re.compile(
    r'(?i)(?:[a-z][a-z0-9+.-]*://[^\s]+|'
    r'(?:bearer\s+)[^\s,;]+|'
    r'(?:password|passwd|secret|token|api[_-]?key|authorization)[\"\']?\s*[=:]\s*[\"\']?[^\s,;]+|'
    r'\b(?:select\s+.+?\s+from|insert\s+into|update\s+.+?\s+set)\b[^\n]*|'
    r'(?:[a-z]:[\\/]|/(?=[a-zA-Z0-9_.-]+/))[^\s\'\"<>]+)')


def public(value, depth=0):
    if depth > 12:
        return '[redacted]'
    if isinstance(value, dict):
        return {SECRET_TEXT.sub('[redacted]', str(k)[:128]): '[redacted]' if SENSITIVE.search(str(k)) else public(v, depth+1)
                for k, v in list(value.items())[:200]}
    if isinstance(value, (list, tuple)):
        return [public(v, depth+1) for v in value[:200]]
    if isinstance(value, str):
        return SECRET_TEXT.sub('[redacted]', value[:4096])
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return '[redacted]'


class DiagnosticFormatter(logging.Formatter):
    def format(self, record):
        # Do not trust third-party extras, getMessage(), exc_info or stack_info.
        data = getattr(record, 'diagnostic', {}) if record.name == 'panel.execution' else {}
        if not isinstance(data, dict):
            data = {}
        result = {'time': round(record.created, 3), 'level': record.levelname if record.levelname in
                  {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'} else 'INFO',
                  'event': data.get('event') if data.get('event') in EVENTS else 'diagnostic'}
        for key in IDS:
            if key in data:
                value = data[key]
                result[key] = value if (key == 'stage_id' and isinstance(value, str) and value in STAGES) or re.fullmatch(
                    r'sha256:[0-9a-f]{32}|[0-9a-f-]{36}', str(value)) else identity(value)
        if data.get('status') in {'started', 'succeeded', 'failed', 'cached', 'retained', 'rejected'}:
            result['status'] = data['status']
        if isinstance(data.get('elapsed_ms'), (float, int)):
            result['elapsed_ms'] = round(max(0, min(data['elapsed_ms'], 86400000)), 3)
        if 'code' in data:
            result['code'] = safe_code(data['code'])
        return json.dumps(result, ensure_ascii=True, allow_nan=False)


@dataclass(frozen=True)
class DiagnosticSettings:
    max_bytes: int = 2 * 1024**2
    backups: int = 3

    def __post_init__(self):
        if not 1024 <= self.max_bytes <= 16 * 1024**2 or not 1 <= self.backups <= 10:
            raise ValueError('Invalid bounded diagnostic retention settings.')

    @classmethod
    def load(cls):
        try:
            return cls(int(os.getenv('PANEL_DIAGNOSTIC_MAX_BYTES', str(2*1024**2))),
                       int(os.getenv('PANEL_DIAGNOSTIC_BACKUPS', '3')))
        except ValueError:
            raise ValueError('Invalid bounded diagnostic retention settings.') from None


class PrivateRotatingHandler(RotatingFileHandler):
    def handleError(self, record):
        # logging's default handler error can print the original raw record.
        # A diagnostic I/O failure must never turn into a secret-bearing fallback.
        pass

    def _open(self):
        descriptor = os.open(self.baseFilename, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.chmod(self.baseFilename, 0o600)
        return os.fdopen(descriptor, self.mode, encoding=self.encoding)


def configure():
    settings = DiagnosticSettings.load()
    directory = Path(os.getenv('PANEL_DATA_DIR', str(Path.home()/'.panelstudio'))) / 'diagnostics'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    path = directory/'execution.jsonl'
    # Exclusive local owner access even with a permissive process umask.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.close(descriptor)
    os.chmod(path, 0o600)
    handler = PrivateRotatingHandler(path, maxBytes=settings.max_bytes,
                                  backupCount=settings.backups, encoding='utf-8')
    handler.setFormatter(DiagnosticFormatter())
    root = logging.getLogger()
    old = root.handlers[:]
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in ('uvicorn', 'uvicorn.error', 'uvicorn.access', 'sqlalchemy.engine'):
        target = logging.getLogger(name)
        target.handlers.clear()
        target.propagate = True
    return handler, old


class RequestDiagnostics:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        request_id = str(uuid4())  # Never trust client-provided correlation headers.
        started = time.perf_counter()
        status = 500
        response_started = False
        async def reply(message):
            nonlocal status, response_started
            if message['type'] == 'http.response.start':
                response_started = True
                status = message['status']
                message['headers'].append((b'x-request-id', request_id.encode()))
            await send(message)
        with bind(request_id=request_id):
            try:
                await self.app(scope, receive, reply)
            except Exception:
                if response_started:
                    raise
                from fastapi.responses import JSONResponse
                emit('public_error', code='INTERNAL_ERROR')
                await JSONResponse(status_code=500, content={'error': {
                    'code': 'INTERNAL_ERROR', 'message': 'The operation could not complete. Your saved data is retained.'}},
                    headers={'Cache-Control': 'no-store'})(scope, receive, reply)
            finally:
                params = scope.get('path_params', {})
                emit('request', status='failed' if status >= 400 else 'succeeded',
                     elapsed_ms=(time.perf_counter()-started)*1000,
                     project_id=params.get('project_id'), document_id=params.get('document_id'),
                     job_id=params.get('job_id'), operation_id=params.get('operation_id'))
