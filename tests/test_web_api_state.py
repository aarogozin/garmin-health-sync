from concurrent.futures import Future
from datetime import date, timedelta
from threading import Event
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from flask import Flask

from garmin_sync import web_api
from garmin_sync.service import OperationResult, ResultStatus, WeeklyReportResult
from garmin_sync.weekly_report import build_report


class ImmediateJobs:
    """Complete stub operations synchronously without contacting a provider."""

    def __init__(self) -> None:
        self.jobs: dict[str, Any] = {}
        self.busy = False

    def submit(self, operation: Any) -> str:
        job_id = f"{len(self.jobs):032d}"
        future: Future[Any] = Future()
        try:
            future.set_result(operation())
        except Exception as exc:
            future.set_exception(exc)
        self.jobs[job_id] = SimpleNamespace(future=future, started=Event())
        return job_id


def state() -> web_api.WebApiState:
    return web_api.WebApiState(
        service=SimpleNamespace(garmin=Mock(), renpho=Mock()),
        jobs=ImmediateJobs(), csrf_token="test", latest_renpho=[], latest_error=[],
        weekly_reports={}, latest_weekly_id=[], previews={}, events=[], garmin_status=[],
        token_store=Mock(delete=Mock(return_value=True)),
        renpho_store=Mock(delete=Mock(return_value=True)),
    )


def report(days: int) -> WeeklyReportResult:
    end = date(2026, 8, 15)
    model = build_report(
        start_date=end - timedelta(days=days - 1), end_date=end,
        garmin={}, renpho=[], available=[], unavailable=[],
    )
    return WeeklyReportResult(ResultStatus.SUCCESS, model, b"%PDF-fake")


def test_expired_mfa_finishes_instead_of_waiting_forever() -> None:
    current = state()
    broker = web_api.MfaBroker()
    broker.requested.set()
    job_id = current.jobs.submit(
        lambda: OperationResult(ResultStatus.ERROR, "Garmin MFA timed out after five minutes")
    )
    current.mfa[job_id] = broker
    payload = web_api._job_payload(job_id, current, include_result=True)
    assert payload["state"] == "error"
    assert "timed out" in payload["result"]["message"]
    assert job_id not in current.mfa


def test_dashboard_refresh_keeps_weekly_identity_and_earlier_report_links() -> None:
    current = state()
    weekly = web_api._consume_result(report(7), current, kind="weekly-report")
    assert isinstance(weekly, dict)
    for days in (1, 30, 7):
        job_id = current.jobs.submit(lambda days=days: report(days))
        current.job_kinds[job_id] = f"dashboard-{days}-days"
        web_api._job_payload(job_id, current, include_result=True)
        assert current.latest_weekly_id == [weekly["id"]]
        assert weekly["id"] in current.weekly_reports
        assert all(item[0] in current.weekly_reports for item in current.dashboard_reports.values())


def test_failed_source_status_replaces_connected_bootstrap() -> None:
    current = state()
    current.garmin_status = [OperationResult(ResultStatus.SUCCESS, "Connected: A")]
    current.service.status = lambda: OperationResult(ResultStatus.AUTH_REQUIRED, "Session expired")
    app = Flask(__name__)
    web_api.register_api(app, current)
    client = app.test_client()
    client.post("/api/v1/sources/status")
    source = client.get("/api/v1/bootstrap").json["data"]["sources"]["garmin"]
    assert source["connected"] is False
    assert source["detail"] == "Session expired"


def test_queued_write_cannot_run_after_the_account_changes() -> None:
    current = state()
    queued: list[Any] = []
    current.jobs = SimpleNamespace(
        submit=lambda operation: queued.append(operation) or "queued-job", busy=False
    )
    current.service.add_pressure = Mock()
    app = Flask(__name__)
    web_api.register_api(app, current)
    response = app.test_client().post("/api/v1/pressure", json={
        "measured_at": "2026-08-15T08:00", "systolic": 120, "diastolic": 80, "pulse": 60,
    })
    assert response.status_code == 202
    current.account_generation += 1
    try:
        queued[0]()
    except RuntimeError as exc:
        assert "Account changed" in str(exc)
    else:
        raise AssertionError("The queued write should have been rejected")
    current.service.add_pressure.assert_not_called()


def test_renpho_login_invalidates_cached_account_and_marks_connected(monkeypatch: Any) -> None:
    current = state()
    current.previews["old-account"] = Mock()
    current.weekly_reports["old-account"] = report(7)
    monkeypatch.setattr(web_api, "RenphoCloud", Mock())
    app = Flask(__name__)
    web_api.register_api(app, current)
    client = app.test_client()
    response = client.post(
        "/api/v1/auth/renpho/login", json={"email": "new@example.test", "password": "test"}
    )
    job_id = response.json["data"]["job_id"]
    assert client.get(f"/api/v1/jobs/{job_id}").json["data"]["state"] == "verified"
    current.service.renpho.clear_session.assert_called_once()
    assert not current.previews and not current.weekly_reports
    assert client.get("/api/v1/bootstrap").json["data"]["sources"]["renpho"]["connected"]


def test_logout_resets_provider_and_snapshots_but_rejects_active_work() -> None:
    for source in ("garmin", "renpho"):
        current = state()
        current.weekly_reports["old"] = report(7)
        old_job = current.jobs.submit(lambda: report(7))
        current.job_generations[old_job] = 0
        current.renpho_authenticated = True
        app = Flask(__name__)
        web_api.register_api(app, current)
        client = app.test_client()
        current.jobs.busy = True
        assert client.post(f"/api/v1/auth/{source}/logout").status_code == 409
        getattr(current.service, source).clear_session.assert_not_called()
        current.jobs.busy = False
        assert client.post(f"/api/v1/auth/{source}/logout").status_code == 200
        getattr(current.service, source).clear_session.assert_called_once()
        assert not current.weekly_reports
        old_result = web_api._job_payload(old_job, current, include_result=True)
        assert old_result["error"]["code"] == "account_changed"
        assert not current.weekly_reports
