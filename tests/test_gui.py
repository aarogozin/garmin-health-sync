from concurrent.futures import Future
from datetime import datetime
from threading import Event
from typing import Any

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


def test_gui_index_and_security_headers() -> None:
    app = create_app(FakeService(), "test-token")  # type: ignore[arg-type]
    response = app.test_client().get("/", headers={"Host": "127.0.0.1"})
    assert response.status_code == 200
    assert "Add blood pressure" in response.text
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "img-src 'self' https://tile.openstreetmap.org" in response.headers[
        "Content-Security-Policy"
    ]
    assert "Show OpenStreetMap background" in response.text
    assert "View body measurements" in response.text
    assert "waist, chest, arms, thighs, calves" in response.text
    assert "Garmin → RENPHO activities" in response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
    assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response.headers["Permissions-Policy"] == "camera=(), geolocation=(), microphone=()"


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
