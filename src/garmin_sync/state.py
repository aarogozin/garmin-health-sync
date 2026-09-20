from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def default_state_path() -> Path:
    """Keep the duplicate-protection ledger in configured container or native application data."""
    if data_dir := os.environ.get("GARMIN_SYNC_DATA_DIR"):
        return Path(data_dir) / "state.json"
    return Path.home() / "Library" / "Application Support" / "garmin-health-sync" / "state.json"


class SyncStateError(RuntimeError):
    """The local duplicate-protection ledger could not be used."""


class SyncState:
    """Recoverable local ledger preventing duplicate RENPHO uploads."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_path()

    def synced_ids(self) -> set[str]:
        """Load confirmed RENPHO source IDs; a missing ledger represents a fresh installation."""
        try:
            data: Any = json.loads(self.path.read_text())
        except FileNotFoundError:
            return set()
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncStateError(f"Could not read sync state: {self.path}") from exc
        values = data.get("renpho_synced_ids", []) if isinstance(data, dict) else []
        return {str(value) for value in values}

    def mark_synced(self, source_id: str) -> None:
        """Atomically record a verified upload; callers serialize updates with the write lock."""
        self._update("renpho_synced_ids", source_id)

    def _update(self, key: str, source_id: str) -> None:
        try:
            data: Any = json.loads(self.path.read_text())
        except FileNotFoundError:
            data = {}
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncStateError(f"Could not read sync state: {self.path}") from exc
        if not isinstance(data, dict):
            data = {}
        values = {str(value) for value in data.get(key, [])}
        values.add(source_id)
        data[key] = sorted(values)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
        fd, temporary = tempfile.mkstemp(prefix="state-", suffix=".json", dir=self.path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(payload)
            os.replace(temporary, self.path)
        except Exception as exc:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise SyncStateError(f"Could not update sync state: {self.path}") from exc
