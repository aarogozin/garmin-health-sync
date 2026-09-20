from __future__ import annotations

from typing import Any

import pytest
import requests

from garmin_sync.scheduler import Scheduler, SchedulerError


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> object:
        return self._payload


def test_docker_helper_status_and_schedule_requests(monkeypatch: Any) -> None:
    calls: list[tuple[str, str, dict[str, int] | None, dict[str, str]]] = []

    def request(method: str, url: str, **kwargs: Any) -> _Response:
        calls.append((method, url, kwargs.get("json"), kwargs["headers"]))
        if url.endswith("/schedule/status"):
            return _Response(200, {"supported": True, "installed": True, "loaded": True})
        return _Response(200, {"installed": True})

    monkeypatch.setenv("GARMIN_SYNC_HOST_BRIDGE_URL", "http://host.docker.internal:9876")
    monkeypatch.setenv("GARMIN_SYNC_HOST_BRIDGE_TOKEN", "private-token")
    monkeypatch.setattr("garmin_sync.scheduler.requests.request", request)
    scheduler = Scheduler()

    assert scheduler.status().installed is True
    scheduler.install(hour=7, minute=30)
    assert calls[0][1].endswith("/schedule/status")
    assert calls[1][2] == {"hour": 7, "minute": 30}
    assert calls[1][3] == {"X-Garmin-Health-Sync-Token": "private-token"}


def test_docker_helper_errors_are_sanitized(monkeypatch: Any) -> None:
    monkeypatch.setenv("GARMIN_SYNC_HOST_BRIDGE_URL", "http://host.docker.internal:9876")
    monkeypatch.setenv("GARMIN_SYNC_HOST_BRIDGE_TOKEN", "private-token")
    monkeypatch.setattr(
        "garmin_sync.scheduler.requests.request",
        lambda *_args, **_kwargs: _Response(401, {"token": "no"}),
    )
    with pytest.raises(SchedulerError, match="rejected"):
        Scheduler().run_now()


def test_unreachable_bridge_returns_actionable_status(monkeypatch: Any) -> None:
    monkeypatch.setenv("GARMIN_SYNC_HOST_BRIDGE_URL", "http://host.docker.internal:9876")
    monkeypatch.setenv("GARMIN_SYNC_HOST_BRIDGE_TOKEN", "private-token")

    def offline(*args: Any, **kwargs: Any) -> None:
        raise requests.ConnectionError("sensitive host command detail")

    monkeypatch.setattr("garmin_sync.scheduler.requests.request", offline)
    status = Scheduler().status()
    assert not status.supported
    assert "./health-sync start" in status.detail
    assert "sensitive" not in status.detail


def test_bridge_rejects_external_url_before_sending_token(monkeypatch: Any) -> None:
    monkeypatch.setenv("GARMIN_SYNC_HOST_BRIDGE_URL", "https://example.com")
    monkeypatch.setenv("GARMIN_SYNC_HOST_BRIDGE_TOKEN", "private-token")
    with pytest.raises(SchedulerError, match="local helper"):
        Scheduler().run_now()
