from dataclasses import dataclass
from typing import Protocol


@dataclass
class DispatchResult:
    exit_code: int | None
    error: str | None = None
    interrupted: bool = False


class Dispatcher(Protocol):
    def run(self, prompt: str, selection: dict, root, lock_fd=None) -> DispatchResult: ...
