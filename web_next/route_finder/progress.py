from __future__ import annotations

from typing import Protocol


class ProgressCallback(Protocol):
    def update(self, message: str) -> None: ...

    def done(self, message: str, found: int = 0) -> None: ...


class NullProgress:
    def update(self, message: str) -> None:
        pass

    def done(self, message: str, found: int = 0) -> None:
        pass
