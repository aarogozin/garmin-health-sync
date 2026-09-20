from __future__ import annotations

import os
import plistlib
import subprocess  # nosec B404
import sys
from pathlib import Path

LABEL = "com.local.garmin-health-sync.renpho"
LAUNCHCTL = "/bin/launchctl"


class ScheduleError(RuntimeError):
    pass


def plist_path() -> Path:
    """Return the native development LaunchAgent path, separate from the Docker helper."""
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def log_path() -> Path:
    """Return the native schedule's operational log path."""
    return Path.home() / "Library" / "Logs" / "GarminHealthSync" / "renpho-sync.log"


def install(*, hour: int, minute: int) -> Path:
    """Write a private plist bound to the current Python interpreter and load it in launchd."""
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ScheduleError("Hour must be 0-23 and minute must be 0-59")

    target = plist_path()
    output = log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [
            sys.executable,
            "-m",
            "garmin_sync.cli",
            "sync",
            "daily",
        ],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(output),
        "StandardErrorPath": str(output),
        "ProcessType": "Background",
    }
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(plistlib.dumps(payload, sort_keys=True))
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)

    domain = f"gui/{os.getuid()}"
    subprocess.run(
        [LAUNCHCTL, "bootout", domain, str(target)],  # nosec B603
        check=False,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [LAUNCHCTL, "bootstrap", domain, str(target)],  # nosec B603
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ScheduleError(_launchctl_error(result.stderr))
    return target


def uninstall() -> bool:
    """Unload and remove only the native Garmin Health Sync LaunchAgent."""
    target = plist_path()
    if not target.exists():
        return False
    subprocess.run(
        [LAUNCHCTL, "bootout", f"gui/{os.getuid()}", str(target)],  # nosec B603
        check=False,
        capture_output=True,
        text=True,
    )
    target.unlink()
    return True


def is_loaded() -> bool:
    """Inspect launchd without running the scheduled synchronization."""
    result = subprocess.run(
        [LAUNCHCTL, "print", f"gui/{os.getuid()}/{LABEL}"],  # nosec B603
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def is_legacy() -> bool:
    """Recognize the old weight-only command so the user can update its schedule."""
    try:
        payload = plistlib.loads(plist_path().read_bytes())
    except (FileNotFoundError, OSError, plistlib.InvalidFileException):
        return False
    if not isinstance(payload, dict):
        return False
    arguments = payload.get("ProgramArguments", [])
    return isinstance(arguments, list) and arguments[-4:] == [
        "renpho",
        "sync",
        "--latest",
        "--yes",
    ]


def run_now() -> None:
    """Trigger the installed native job using its fixed launchd label."""
    result = subprocess.run(
        [LAUNCHCTL, "kickstart", f"gui/{os.getuid()}/{LABEL}"],  # nosec B603
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ScheduleError(_launchctl_error(result.stderr))


def _launchctl_error(stderr: str) -> str:
    """Hide host command output, which can contain private paths or environment details."""
    return "Could not configure the macOS schedule; check that the user session is logged in"
