"""Strict JSON, confined paths, atomic writes and a single-writer lock."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

from .errors import OrchestratorError


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, ValueError) as exc:
        raise OrchestratorError(f"Cannot read JSON {path}: {exc}") from exc


def confined(root, relative):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise OrchestratorError(f"Expected a nonempty repository-relative path: {relative!r}")
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise OrchestratorError(f"Path escapes repository: {relative}")
    return path


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextlib.contextmanager
def execution_lock(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise OrchestratorError("Another orchestrator/Codex session holds the execution lock.") from exc
        yield stream.fileno()
        # Closing, rather than explicitly unlocking, keeps a child-inherited lock alive.
