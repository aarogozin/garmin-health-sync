from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .state import default_state_path


class SyncBusyError(RuntimeError):
    """Another process is currently performing a synchronization write."""


def default_lock_path() -> Path:
    return default_state_path().with_name("sync.lock")


@contextmanager
def write_lock(path: Path | None = None) -> Iterator[None]:
    """Hold a nonblocking cross-process lock for a complete duplicate-check/upload operation."""
    target = path or default_lock_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(target, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SyncBusyError("Another Garmin Health Sync operation is already running") from exc
        yield
    finally:
        os.close(descriptor)
