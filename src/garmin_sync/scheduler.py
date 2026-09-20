"""Safe scheduler selection for native development and Docker-first macOS runtime."""

from __future__ import annotations

import os
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import requests

from . import schedule


@dataclass(frozen=True, slots=True)
class ScheduleStatus:
    supported: bool
    installed: bool
    loaded: bool
    legacy: bool
    detail: str = ""


class SchedulerError(RuntimeError):
    pass


class Scheduler:
    """Route fixed scheduling actions to the host bridge or native macOS adapter."""

    def __init__(self) -> None:
        self.url = os.environ.get("GARMIN_SYNC_HOST_BRIDGE_URL", "").rstrip("/")
        self.token = os.environ.get("GARMIN_SYNC_HOST_BRIDGE_TOKEN", "")

    def status(self) -> ScheduleStatus:
        """Return an actionable unavailable state when the Docker host helper is offline."""
        if self.url and self.token:
            try:
                payload = self._request("GET", "/schedule/status")
            except SchedulerError as exc:
                return ScheduleStatus(False, False, False, False, str(exc))
            return ScheduleStatus(
                bool(payload.get("supported")),
                bool(payload.get("installed")),
                bool(payload.get("loaded")),
                bool(payload.get("legacy")),
                "Managed by the Docker macOS helper",
            )
        if sys.platform == "darwin":
            installed = schedule.plist_path().exists()
            return ScheduleStatus(
                True,
                installed,
                schedule.is_loaded() if installed else False,
                schedule.is_legacy() if installed else False,
                "Managed by the native macOS runtime",
            )
        return ScheduleStatus(False, False, False, False, "Start with ./health-sync start")

    def install(self, *, hour: int, minute: int) -> None:
        """Install or replace the fixed daily job, with wall-clock hour/minute validation."""
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise SchedulerError("Hour must be 0-23 and minute must be 0-59")
        if self.url and self.token:
            self._request("POST", "/schedule/install", {"hour": hour, "minute": minute})
            return
        if sys.platform == "darwin":
            try:
                schedule.install(hour=hour, minute=minute)
            except (schedule.ScheduleError, OSError) as exc:
                raise SchedulerError("Could not install the macOS schedule") from exc
            return
        raise SchedulerError("Start the Docker runtime through ./health-sync start")

    def run_now(self) -> None:
        """Ask launchd to start its installed job; do not run arbitrary commands."""
        if self.url and self.token:
            self._request("POST", "/schedule/run")
            return
        if sys.platform == "darwin":
            try:
                schedule.run_now()
            except (schedule.ScheduleError, OSError) as exc:
                raise SchedulerError("Could not start the macOS schedule") from exc
            return
        raise SchedulerError("Start the Docker runtime through ./health-sync start")

    def uninstall(self) -> bool:
        """Remove only this application's job, returning whether one was installed."""
        if self.url and self.token:
            return bool(self._request("POST", "/schedule/remove").get("removed"))
        if sys.platform == "darwin":
            try:
                return schedule.uninstall()
            except (schedule.ScheduleError, OSError) as exc:
                raise SchedulerError("Could not remove the macOS schedule") from exc
        raise SchedulerError("Start the Docker runtime through ./health-sync start")

    def open_archive(self, path: str) -> None:
        """Open the configured host workspace; Docker never forwards a client-supplied path."""
        if self.url and self.token:
            self._request("POST", "/archive/open")
            return
        if sys.platform == "darwin":
            result = subprocess.run(
                ["/usr/bin/open", path],  # nosec B603
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return
        raise SchedulerError("Could not open the local Markdown archive")

    def _request(
        self, method: str, path: str, body: dict[str, int] | None = None
    ) -> dict[str, Any]:
        """Send one bounded-time bridge request without redirects or automatic retries."""
        target = urlsplit(self.url)
        if (
            target.scheme != "http"
            or target.hostname not in {"host.docker.internal", "127.0.0.1", "localhost"}
            or target.username is not None
            or target.password is not None
            or target.path
            or target.query
            or target.fragment
        ):
            raise SchedulerError(
                "Restart through ./health-sync start to configure the local helper"
            )
        try:
            response = requests.request(
                method,
                f"{self.url}{path}",
                json=body,
                headers={"X-Garmin-Health-Sync-Token": self.token},
                timeout=(2, 5),
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise SchedulerError(
                "Restart through ./health-sync start to enable macOS scheduling"
            ) from exc
        if response.status_code != 200:
            raise SchedulerError("The local macOS scheduling helper rejected the request")
        try:
            value = response.json()
        except ValueError as exc:
            raise SchedulerError(
                "The local macOS scheduling helper returned an invalid response"
            ) from exc
        if not isinstance(value, dict):
            raise SchedulerError("The local macOS scheduling helper returned an invalid response")
        return value
