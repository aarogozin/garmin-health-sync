from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path
from typing import Any

import pytest

from garmin_sync import schedule


def _completed(returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, "", stderr)


def test_install_writes_private_launch_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: calls.append(command) or _completed(),
    )

    target = schedule.install(hour=7, minute=30)
    payload = plistlib.loads(target.read_bytes())

    assert payload["StartCalendarInterval"] == {"Hour": 7, "Minute": 30}
    assert payload["ProgramArguments"][-4:] == ["renpho", "sync", "--latest", "--yes"]
    assert target.stat().st_mode & 0o777 == 0o600
    assert calls[0][1] == "bootout"
    assert calls[1][1] == "bootstrap"


@pytest.mark.parametrize(("hour", "minute"), [(-1, 0), (24, 0), (0, -1), (0, 60)])
def test_install_rejects_invalid_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, hour: int, minute: int
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.raises(schedule.ScheduleError):
        schedule.install(hour=hour, minute=minute)


def test_uninstall_removes_only_own_plist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _completed())
    target = schedule.plist_path()
    target.parent.mkdir(parents=True)
    target.write_text("test")

    assert schedule.uninstall() is True
    assert not target.exists()
    assert schedule.uninstall() is False


def test_is_loaded_uses_launchctl_result(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return _completed(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert schedule.is_loaded() is True
