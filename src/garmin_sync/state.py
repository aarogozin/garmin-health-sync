from __future__ import annotations

import contextlib
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
        values = self.synced_ids()
        values.add(source_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"renpho_synced_ids": sorted(values)}, indent=2) + "\n"
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
