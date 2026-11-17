"""Execute trusted server callables in killable, resource-bounded processes.

This is a resource boundary, not a sandbox for user code. Never accept callable
names, Python source or native command lines from an HTTP request.
"""
from dataclasses import dataclass
import multiprocessing
import os
from pathlib import Path
import pickle
import signal
import tempfile
from threading import BoundedSemaphore
import time

from app.services.design_errors import DesignError


class WorkerFailure(DesignError):
    def __init__(self, code):
        super().__init__(code, 'Bounded workload did not complete.')


@dataclass(frozen=True)
class Budget:
    wall_seconds: float = 120
    cpu_seconds: int = 90
    memory_bytes: int = 2 * 1024**3
    output_bytes: int = 32 * 1024**2

    def __post_init__(self):
        if (not 0 < self.wall_seconds <= 3600 or not 1 <= self.cpu_seconds <= 3600
                or not 128 * 1024**2 <= self.memory_bytes <= 8 * 1024**3
                or not 1 <= self.output_bytes <= 128 * 1024**2):
            raise ValueError('Invalid worker resource budget.')


_slots = BoundedSemaphore(2)


def _child(call, args, path, budget):
    try:
        # Spawn avoids inheriting database sessions, locks and request threads.
        # Unsupported platforms fail closed rather than run without limits.
        import resource
        os.setsid()
        for key, limit in ((resource.RLIMIT_CPU, budget.cpu_seconds),
                           (resource.RLIMIT_AS, budget.memory_bytes),
                           (resource.RLIMIT_FSIZE, budget.output_bytes),
                           (resource.RLIMIT_NOFILE, 64), (resource.RLIMIT_CORE, 0)):
            resource.setrlimit(key, (limit, limit))
        try:
            value = ('ok', call(*args))
        except DesignError as exc:
            value = ('engineering', exc.as_dict())
        except Exception:
            value = ('failed', None)
        with open(path, 'wb') as stream:
            pickle.dump(value, stream, protocol=5)
    except BaseException:
        os._exit(1)


def run_bounded(call, *args, budget=None, cancelled=lambda: False):
    """No database transaction may surround this call; callbacks use short ones.

    Poll cancellation/lease ownership while running. All exit paths kill the
    process group (including trusted native descendants) and reap the child.
    """
    budget = budget or Budget()
    if not _slots.acquire(blocking=False):
        raise WorkerFailure('WORKER_BUSY')
    process = None
    try:
        if cancelled():
            raise WorkerFailure('JOB_CANCELLED')
        if len(pickle.dumps(args, protocol=5)) > budget.output_bytes:
            raise WorkerFailure('WORKER_INPUT_LIMIT')
        with tempfile.TemporaryDirectory(prefix='panel-worker-') as directory:
            path = Path(directory) / 'result'
            process = multiprocessing.get_context('spawn').Process(
                target=_child, args=(call, args, str(path), budget))
            started = time.monotonic()
            process.start()
            while process.is_alive():
                if cancelled():
                    raise WorkerFailure('JOB_CANCELLED')
                if time.monotonic() - started >= budget.wall_seconds:
                    raise WorkerFailure('WORKER_TIMEOUT')
                process.join(timeout=.05)
            if cancelled():
                raise WorkerFailure('JOB_CANCELLED')
            if time.monotonic() - started >= budget.wall_seconds:
                raise WorkerFailure('WORKER_TIMEOUT')
            if process.exitcode != 0 or not path.is_file():
                raise WorkerFailure('WORKER_CRASHED')
            if path.stat().st_size > budget.output_bytes:
                raise WorkerFailure('WORKER_OUTPUT_LIMIT')
            # Only this trusted child can write this private temporary file.
            with path.open('rb') as stream:
                status, value = pickle.load(stream)
            if status == 'engineering':
                error = value['error']
                raise DesignError(error['code'], error['message'],
                                  errors=error.get('errors'), details=error.get('details'))
            if status != 'ok':
                raise WorkerFailure('WORKER_FAILED')
            return value
    finally:
        if process is not None and process.pid:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.is_alive():
                process.kill()
            process.join(timeout=2)
            process.close()
        _slots.release()


def export_cad(inputs):
    from app.persistence.assets import primitive_glb
    from app.models.pdm import PhysicalDesignModel
    from app.services.cad_engine import CADEngine
    if inputs['format'] == 'GLB':
        return primitive_glb(inputs['cad']['primitives'], generator_version='3')
    if inputs['format'] == 'PY':
        return CADEngine().export_freecad_script(PhysicalDesignModel(**inputs['pdm'])).encode()
    raise WorkerFailure('INVALID_JOB_INPUT')


def execute_stage(name, inputs):
    from app.services.stages.cache import ADAPTERS
    binding = ADAPTERS[name]
    return binding.execute(binding.inputs.model_validate(inputs)).model_dump(mode='json')
