from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def default_state_path() -> Path:
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
        try:
            data: Any = json.loads(self.path.read_text())
        except FileNotFoundError:
            return set()
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncStateError(f"Could not read sync state: {self.path}") from exc
        values = data.get("renpho_synced_ids", []) if isinstance(data, dict) else []
        return {str(value) for value in values}

    def mark_synced(self, source_id: str) -> None:
        self._update("renpho_synced_ids", source_id, hashed=False)

    def activity_synced(self, activity_id: str) -> bool:
        return self._activity_hash(activity_id) in self._values("garmin_activity_hashes")

    def mark_activity_synced(self, activity_id: str) -> None:
        self._update("garmin_activity_hashes", activity_id, hashed=True)

    def _values(self, key: str) -> set[str]:
        try:
            data: Any = json.loads(self.path.read_text())
        except FileNotFoundError:
            return set()
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncStateError(f"Could not read sync state: {self.path}") from exc
        values = data.get(key, []) if isinstance(data, dict) else []
        return {str(value) for value in values}

    def _update(self, key: str, source_id: str, *, hashed: bool) -> None:
        try:
            data: Any = json.loads(self.path.read_text())
        except FileNotFoundError:
            data = {}
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncStateError(f"Could not read sync state: {self.path}") from exc
        if not isinstance(data, dict):
            data = {}
        values = {str(value) for value in data.get(key, [])}
        values.add(self._activity_hash(source_id) if hashed else source_id)
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

    @staticmethod
    def _activity_hash(activity_id: str) -> str:
        return hashlib.sha256(f"garmin-activity:{activity_id}".encode()).hexdigest()
