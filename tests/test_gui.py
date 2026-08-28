import re
from concurrent.futures import Future
from datetime import datetime
from threading import Event
from time import sleep
from typing import Any

import pytest

import garmin_sync.web_api as web_api
from garmin_sync.activities import (
    ActivitySyncCandidate,
    ActivitySyncPreview,
    GarminActivity,
    RenphoActivityTemplate,
)
from garmin_sync.body_report import ReportDocument
from garmin_sync.gui import JobManager, create_app
from garmin_sync.models import BERLIN, BodyComposition
from garmin_sync.renpho import GirthValue, RenphoGirthMeasurement, RenphoMeasurement
from garmin_sync.renpho_report import normalize_report
from garmin_sync.service import (
    LatestRenphoReport,
    OperationResult,
    RenphoHistory,
    RenphoPreview,
    ResultStatus,
    WeeklyReportResult,
)
from garmin_sync.weekly_pdf import render_weekly_report_pdf
from garmin_sync.weekly_report import build_report


class FakeService:
    def get_report_progress(self, job_id: str | None = None) -> dict[str, object]:
        return {"stage": "Complete", "completed": 5, "total": 5}

    def status(self) -> OperationResult:
        return OperationResult(ResultStatus.SUCCESS, "Подключено: Test User")

    def add_pressure(self, measurement: Any) -> OperationResult:
        return OperationResult(ResultStatus.SUCCESS, f"saved {measurement.notes}")

    def preview_renpho(self, mode: str) -> Any:
        raise RuntimeError("not used")

    def sync_renpho(self, preview: Any) -> list[OperationResult]:
        return []

    def preview_activities(self, period: str) -> ActivitySyncPreview:
        activity = GarminActivity(
            "42",
            "running",
            "<Morning Run>",
            datetime(2026, 8, 15, 8, 0, tzinfo=BERLIN),
            1800,
            300,
        )
        return ActivitySyncPreview(
            period,
            (ActivitySyncCandidate(activity, RenphoActivityTemplate(52, "Running")),),
            (),
            0,
            0,
        )

    def sync_activities(self, preview: Any) -> list[Any]:
        return []

    def latest_report(self) -> LatestRenphoReport:
        measurement = RenphoMeasurement(
            "latest", BodyComposition(datetime(2026, 8, 15, 8, 0, tzinfo=BERLIN), 89.5)
        )
        return LatestRenphoReport(
            measurement, ReportDocument(b"%PDF-1.4 fake", "Rendered from RENPHO data")
        )

    def renpho_history(self) -> RenphoHistory:
        measured_at = datetime(2026, 8, 15, 8, 0, tzinfo=BERLIN)
        measurement = RenphoMeasurement(
            "history",
            BodyComposition(measured_at, 89.5),
            normalize_report(
                {"weight": 89.5, "bodyfat": 18.2, "whr": 0.84}, measured_at
            ),
        )
        girth = RenphoGirthMeasurement(
            measured_at,
            (
                GirthValue("Waist", 91.2, "cm"),
                GirthValue("Left arm", 35.1, "cm"),
            ),
        )
        return RenphoHistory((measurement,), (girth,))

    def build_weekly_report(
        self, *, include_routes: bool = False, map_tiles_enabled: bool = False
    ) -> WeeklyReportResult:
        report = build_report(
            start_date=datetime(2026, 8, 9).date(),
            end_date=datetime(2026, 8, 15).date(),
            garmin={},
            renpho=[],
            available=[],
            unavailable=["sleep"],
        )
        return WeeklyReportResult(ResultStatus.PARTIAL, report, render_weekly_report_pdf(report))


def test_terminal_job_state_preserves_safe_business_outcomes() -> None:
    assert web_api._terminal_state(OperationResult(ResultStatus.SUCCESS, "ok")) == "verified"
    assert (
        web_api._terminal_state(OperationResult(ResultStatus.CONFLICT, "duplicate"))
        == "conflict"
    )
    assert web_api._terminal_state(OperationResult(ResultStatus.UNCERTAIN, "check")) == "uncertain"
    assert (
        web_api._terminal_state(OperationResult(ResultStatus.RATE_LIMITED, "wait"))
        == "rate_limited"
    )


def test_avatar_proxy_accepts_only_valid_in_memory_image(monkeypatch: Any) -> None:
    class Response:
        is_redirect = False
        status_code = 200
        headers = {"Content-Type": "image/png"}

        @staticmethod
        def iter_content(_: int) -> list[bytes]:
            return [b"\x89PNG\r\n\x1a\nimage"]

    calls: list[str] = []
    monkeypatch.setattr(web_api.requests, "get", lambda url, **_: calls.append(url) or Response())
    cache = web_api.AvatarCache()
    content, mimetype = web_api._avatar_bytes("https://images.example.amazonaws.com/a.png", cache)
    assert content.startswith(b"\x89PNG")
    assert mimetype == "image/png"
    web_api._avatar_bytes("https://images.example.amazonaws.com/a.png", cache)
    assert len(calls) == 1
    with pytest.raises(ValueError):
        web_api._avatar_bytes("http://evil.example/avatar.png", web_api.AvatarCache())


def test_gui_index_and_security_headers() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    response = app.test_client().get("/", headers={"Host": "127.0.0.1"})
    assert response.status_code == 200
    assert "Garmin Health Sync" in response.text
    assert "/ui-assets/assets/" in response.text
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert "style-src 'self'" in response.headers["Content-Security-Policy"]
    assert "img-src 'self' data: https://tile.openstreetmap.org" in response.headers[
        "Content-Security-Policy"
    ]
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["Permissions-Policy"] == "camera=(), geolocation=(), microphone=()"
    asset_path = re.search(r'src="([^"]+\.js)"', response.text)
    assert asset_path is not None
    asset = app.test_client().get(
        asset_path.group(1), headers={"Host": "127.0.0.1"}
    )
    assert asset.status_code == 200
    assert asset.mimetype in {"application/javascript", "text/javascript"}


def test_v1_bootstrap_and_dashboard_are_structured_and_no_store() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    assert app.extensions["garmin_sync_startup_ready"].wait(timeout=2)
    client = app.test_client()
    bootstrap = client.get("/api/v1/bootstrap", headers={"Host": "127.0.0.1"})
    assert bootstrap.status_code == 200
    payload = bootstrap.get_json()
    assert payload["status"] == "success"
    assert payload["data"]["version"] == "1.0.0"
    assert payload["data"]["csrf_token"] == "test-token"
    assert payload["data"]["sources"]["garmin"]["connected"] is True
    assert bootstrap.headers["Cache-Control"] == "no-store"

    dashboard = client.get("/api/v1/dashboard", headers={"Host": "127.0.0.1"})
    assert dashboard.get_json()["data"]["latest_body"]["weight_kg"] == 89.5


def test_v1_json_mutations_require_csrf_and_validate_pressure() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    assert app.extensions["garmin_sync_startup_ready"].wait(timeout=2)
    client = app.test_client()
    body = {
        "measured_at": "2026-08-13T08:00",
        "systolic": 120,
        "diastolic": 80,
        "pulse": 60,
        "notes": "safe",
    }
    assert client.post("/api/v1/pressure/preview", json=body).status_code == 403
    invalid = client.post(
        "/api/v1/pressure/preview",
        json={**body, "systolic": 500},
        headers={"Host": "127.0.0.1", "X-CSRF-Token": "test-token"},
    )
    assert invalid.status_code == 400
    assert invalid.get_json()["status"] == "validation_error"
    valid = client.post(
        "/api/v1/pressure/preview",
        json=body,
        headers={"Host": "127.0.0.1", "X-CSRF-Token": "test-token"},
    )
    assert valid.status_code == 200
    assert valid.get_json()["data"]["measurement"]["systolic"] == 120


def test_v1_schedule_status_and_install_are_protected(monkeypatch: Any, tmp_path: Any) -> None:
    target = tmp_path / "daily.plist"
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(web_api.sys, "platform", "darwin")
    monkeypatch.setattr(web_api.schedule, "plist_path", lambda: target)
    monkeypatch.setattr(web_api.schedule, "is_loaded", lambda: target.exists())
    monkeypatch.setattr(web_api.schedule, "is_legacy", lambda: False)

    def install(*, hour: int, minute: int) -> None:
        calls.append((hour, minute))
        target.touch()

    monkeypatch.setattr(web_api.schedule, "install", install)
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    assert app.extensions["garmin_sync_startup_ready"].wait(timeout=2)
    client = app.test_client()
    status = client.get("/api/v1/schedule", headers={"Host": "127.0.0.1"})
    assert status.get_json()["data"] == {
        "supported": True,
        "installed": False,
        "loaded": False,
        "legacy": False,
    }
    missing_csrf = client.post(
        "/api/v1/schedule/install", json={"hour": 7, "minute": 15}
    )
    assert missing_csrf.status_code == 403
    result = _start_api_job(
        client, "/api/v1/schedule/install", {"hour": 7, "minute": 15}
    )
    assert result["result"]["status"] == "success"
    assert calls == [(7, 15)]


def _finish_api_job(client: Any, location: str) -> dict[str, Any]:
    for _ in range(50):
        response = client.get(location, headers={"Host": "127.0.0.1"})
        data = response.get_json()["data"]
        if data["state"] in {
            "verified",
            "already_exists",
            "conflict",
            "partial",
            "uncertain",
            "auth_required",
            "rate_limited",
            "error",
        }:
            return data
        sleep(0.01)
    raise AssertionError("job did not finish")


def _start_api_job(client: Any, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post(
        path,
        json=body or {},
        headers={"Host": "127.0.0.1", "X-CSRF-Token": "test-token"},
    )
    assert response.status_code == 202
    job_id = response.get_json()["data"]["job_id"]
    return _finish_api_job(client, f"/api/v1/jobs/{job_id}")


def test_v1_jobs_serialize_latest_history_activity_and_weekly_report() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    assert app.extensions["garmin_sync_startup_ready"].wait(timeout=2)
    client = app.test_client()

    latest = _start_api_job(client, "/api/v1/renpho/latest")
    assert latest["result"]["type"] == "renpho_latest"
    assert latest["result"]["weight_kg"] == 89.5

    history = _start_api_job(client, "/api/v1/renpho/history")
    assert history["result"]["type"] == "renpho_history"
    assert history["result"]["girth"][0]["values"][0]["label"] == "Waist"

    activities = _start_api_job(
        client, "/api/v1/activities/preview", {"period": "day"}
    )
    assert activities["result"]["type"] == "activity_preview"
    assert activities["result"]["candidates"][0]["name"] == "<Morning Run>"

    weekly = _start_api_job(client, "/api/v1/reports/weekly")
    assert weekly["result"]["type"] == "weekly_report"
    report_id = weekly["result"]["id"]
    report = client.get(
        f"/api/v1/reports/weekly/{report_id}", headers={"Host": "127.0.0.1"}
    )
    assert report.get_json()["data"]["start_date"] == "2026-08-09"
    pdf = client.post(
        f"/api/v1/reports/weekly/{report_id}/download",
        headers={"Host": "127.0.0.1", "X-CSRF-Token": "test-token"},
    )
    assert pdf.data.startswith(b"%PDF-")
    assert client.get("/api/v1/jobs", headers={"Host": "127.0.0.1"}).status_code == 200


def test_v1_jobs_serialize_previews_and_operation_results() -> None:
    class PreviewService(FakeService):
        def preview_renpho(self, mode: str) -> RenphoPreview:
            measurement = RenphoMeasurement(
                "candidate",
                BodyComposition(datetime(2026, 8, 15, 8, 0, tzinfo=BERLIN), 89.5),
            )
            return RenphoPreview(mode, (measurement,), 2)

    app = create_app(PreviewService(), "test-token")  # type: ignore[arg-type]
    assert app.extensions["garmin_sync_startup_ready"].wait(timeout=2)
    client = app.test_client()
    preview = _start_api_job(
        client, "/api/v1/renpho/sync/preview", {"mode": "latest"}
    )
    assert preview["result"]["type"] == "renpho_preview"
    assert preview["result"]["count"] == 1

    pressure = _start_api_job(
        client,
        "/api/v1/pressure",
        {
            "measured_at": "2026-08-13T08:00",
            "systolic": 120,
            "diastolic": 80,
            "pulse": 60,
            "notes": "test",
        },
    )
    assert pressure["result"]["type"] == "operation"
    assert pressure["result"]["status"] == "success"


def test_startup_readiness_waits_for_garmin_and_renpho_checks() -> None:
    class DelayedStartupService(FakeService):
        def __init__(self) -> None:
            self.gate = Event()

        def latest_report(self) -> LatestRenphoReport:
            assert self.gate.wait(timeout=2)
            return super().latest_report()

    service = DelayedStartupService()
    app = create_app(service, "test-token")  # type: ignore[arg-type]
    ready = app.extensions["garmin_sync_startup_ready"]
    assert not ready.wait(timeout=0.05)
    service.gate.set()
    assert ready.wait(timeout=2)


def test_gui_rejects_bad_host_origin_and_csrf() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    client = app.test_client()
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
    assert client.post("/status", headers={"Host": "127.0.0.1"}).status_code == 403
    assert (
        client.post(
            "/status",
            data={"csrf": "test-token"},
            headers={"Host": "127.0.0.1", "Origin": "https://evil.example"},
        ).status_code
        == 403
    )


def test_gui_rejects_malformed_host_and_origin_values() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    client = app.test_client()
    assert client.get("/", headers={"Host": "localhost:invalid"}).status_code == 400
    assert client.get("/", headers={"Host": "attacker@localhost"}).status_code == 400
    for origin in (
        "ftp://localhost",
        "http://attacker@localhost",
        "http://localhost:invalid",
        "http://localhost/path",
        "http://localhost?query=yes",
    ):
        response = client.post(
            "/status",
            data={"csrf": "test-token"},
            headers={"Host": "127.0.0.1", "Origin": origin},
        )
        assert response.status_code == 403


def test_gui_accepts_private_null_origin_only_for_same_origin_navigation() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    client = app.test_client()
    response = client.post(
        "/status",
        data={"csrf": "test-token"},
        headers={
            "Host": "127.0.0.1",
            "Origin": "null",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert response.status_code == 302

    rejected = client.post(
        "/status",
        data={"csrf": "test-token"},
        headers={
            "Host": "127.0.0.1",
            "Origin": "null",
            "Sec-Fetch-Site": "cross-site",
        },
    )
    assert rejected.status_code == 403


def test_mutating_routes_reject_get() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    client = app.test_client()
    assert client.get("/status", headers={"Host": "127.0.0.1"}).status_code == 405
    assert client.get("/pressure/submit", headers={"Host": "127.0.0.1"}).status_code == 405
    assert client.get("/activities/preview", headers={"Host": "127.0.0.1"}).status_code == 405


def test_activity_preview_is_csrf_protected_and_escaped() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    assert app.extensions["garmin_sync_startup_ready"].wait(timeout=2)
    client = app.test_client()
    assert client.post("/activities/preview", headers={"Host": "127.0.0.1"}).status_code == 403
    started = client.post(
        "/activities/preview",
        data={"csrf": "test-token", "period": "day"},
        headers={"Host": "127.0.0.1"},
    )
    result = client.get(started.headers["Location"], headers={"Host": "127.0.0.1"})
    assert "Confirm Garmin → RENPHO activity sync" in result.text
    assert "&lt;Morning Run&gt;" in result.text
    assert "<Morning Run>" not in result.text


def test_pressure_confirmation_escapes_notes() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    response = app.test_client().post(
        "/pressure/confirm",
        data={
            "csrf": "test-token",
            "measured_at": "2026-08-13T08:00",
            "systolic": "120",
            "diastolic": "80",
            "pulse": "60",
            "notes": "<script>alert(1)</script>",
        },
        headers={"Host": "127.0.0.1"},
    )
    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;" in response.text


def test_job_manager_rejects_parallel_operation() -> None:
    manager = JobManager()
    gate: Future[None] = Future()
    first = manager.submit(lambda: gate.result(timeout=2))
    assert first is not None
    assert manager.submit(lambda: None) is None
    gate.set_result(None)
    manager.jobs[first].future.result(timeout=2)


def test_latest_renpho_is_shown_and_pdf_is_protected() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    client = app.test_client()
    started = client.post(
        "/renpho/latest", data={"csrf": "test-token"}, headers={"Host": "127.0.0.1"}
    )
    assert started.status_code == 302
    result = client.get(started.headers["Location"], headers={"Host": "127.0.0.1"})
    assert "89.5 kg" in result.text

    assert client.get("/renpho/report/view", headers={"Host": "127.0.0.1"}).status_code == 405
    assert client.post("/renpho/report/view", headers={"Host": "127.0.0.1"}).status_code == 403
    pdf = client.post(
        "/renpho/report/view",
        data={"csrf": "test-token"},
        headers={"Host": "127.0.0.1"},
    )
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    assert pdf.data.startswith(b"%PDF-")
    assert pdf.headers["Content-Disposition"].startswith("inline")
    download = client.post(
        "/renpho/report/download",
        data={"csrf": "test-token"},
        headers={"Host": "127.0.0.1"},
    )
    assert download.headers["Content-Disposition"].startswith("attachment")


def test_renpho_history_shows_whr_and_body_measurements() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    client = app.test_client()
    started = client.post(
        "/renpho/history", data={"csrf": "test-token"}, headers={"Host": "127.0.0.1"}
    )
    result = client.get(started.headers["Location"], headers={"Host": "127.0.0.1"})
    assert "RENPHO body measurements" in result.text
    assert "89.5 kg" in result.text
    assert "0.84" in result.text
    assert "Waist" in result.text
    assert "91.20 cm" in result.text
    assert "Left arm" in result.text
    assert "Body diagram showing measured locations" in result.text
    assert "class=measure-line" in result.text
    assert (
        "marker-end=&#39;url(#arrowhead)&#39;" in result.text
        or "marker-end='url(#arrowhead)'" in result.text
    )
    assert "<ellipse" not in result.text
    assert "/assets/body-silhouette.svg" in result.text
    silhouette = client.get("/assets/body-silhouette.svg", headers={"Host": "127.0.0.1"})
    assert silhouette.status_code == 200
    assert silhouette.mimetype == "image/svg+xml"
    assert b"<svg" in silhouette.data


def test_slow_job_has_header_and_manual_status_fallback() -> None:
    class SlowStatusService(FakeService):
        def __init__(self) -> None:
            self.gate = Event()
            self.calls = 0

        def status(self) -> OperationResult:
            self.calls += 1
            if self.calls > 1 and not self.gate.wait(timeout=30):
                raise RuntimeError("test timed out")
            return super().status()

    service = SlowStatusService()
    app = create_app(service, "test-token")  # type: ignore[arg-type]
    assert app.extensions["garmin_sync_startup_ready"].wait(timeout=2)
    client = app.test_client()
    started = client.post(
        "/status", data={"csrf": "test-token"}, headers={"Host": "127.0.0.1"}
    )
    assert started.status_code == 302
    result = client.get(started.headers["Location"], headers={"Host": "127.0.0.1"})
    assert result.status_code == 200
    assert result.headers["Refresh"] == "1"
    assert "<progress" in result.text
    assert "% complete" in result.text
    assert f"href='{started.headers['Location']}'" in result.text
    service.gate.set()


def test_weekly_report_routes_are_protected_and_in_memory() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    client = app.test_client()
    started = client.post(
        "/weekly-report/generate",
        data={"csrf": "test-token"},
        headers={"Host": "127.0.0.1"},
    )
    result = client.get(started.headers["Location"], headers={"Host": "127.0.0.1"})
    assert "Weekly report ready" in result.text
    report_path = result.text.split("href='", 1)[1].split("'", 1)[0]
    web = client.get(report_path, headers={"Host": "127.0.0.1"})
    assert "7-day health report" in web.text
    assert "Interactive health dashboard" in web.text
    assert "script-src 'self'" in web.headers["Content-Security-Policy"]
    data = client.get(f"{report_path}/data", headers={"Host": "127.0.0.1"})
    assert data.status_code == 200
    assert data.headers["Cache-Control"] == "no-store"
    assert "charts" in data.get_json()
    script = client.get("/assets/weekly-charts.js", headers={"Host": "127.0.0.1"})
    assert "aria-pressed" in script.text
    assert "fetch('http" not in script.text and 'fetch("http' not in script.text
    assert "tile.openstreetmap.org" in script.text
    assert "© OpenStreetMap contributors" in script.text
    download_path = f"{report_path}/download"
    assert client.get(download_path, headers={"Host": "127.0.0.1"}).status_code == 405
    assert client.post(download_path, headers={"Host": "127.0.0.1"}).status_code == 403
    pdf = client.post(
        download_path,
        data={"csrf": "test-token"},
        headers={"Host": "127.0.0.1"},
    )
    assert pdf.data.startswith(b"%PDF-")
    assert "weekly-health-report-2026-08-09-to-2026-08-15.pdf" in pdf.headers[
        "Content-Disposition"
    ]


def test_report_data_and_progress_are_host_protected() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    client = app.test_client()
    missing = client.get("/weekly-report/unknown/data", headers={"Host": "127.0.0.1"})
    assert missing.status_code == 404
    external = client.get("/assets/weekly-charts.js", headers={"Host": "evil.example"})
    assert external.status_code == 400
    assert client.get("/jobs/unknown/progress", headers={"Host": "127.0.0.1"}).status_code == 404
