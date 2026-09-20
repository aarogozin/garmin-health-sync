from __future__ import annotations

import os
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from time import monotonic
from typing import Any, cast
from urllib.parse import urljoin, urlparse

import requests
from flask import Blueprint, Response, jsonify, request
from pydantic import ValidationError as PydanticValidationError

from . import __version__
from .api_models import (
    ArchiveBackfillRequest,
    DashboardRefreshRequest,
    GarminLoginRequest,
    HealthContextRequest,
    MfaRequest,
    PressureRequest,
    RenphoLoginRequest,
    ScheduleRequest,
    SyncPreviewRequest,
    WeeklyReportRequest,
)
from .archive import ArchiveStatus, render_weekly_markdown
from .garmin import GarminProfile
from .models import BERLIN, BloodPressure, ValidationError, parse_local_datetime
from .renpho import RenphoCloud, SuppliedCredentials
from .scheduler import Scheduler, SchedulerError
from .secrets import RenphoStore, TokenStore
from .service import (
    HealthContextResult,
    LatestRenphoReport,
    OperationResult,
    RenphoHistory,
    RenphoPreview,
    ResultStatus,
    WeeklyReportResult,
)
from .weekly_report import chart_payload


@dataclass(slots=True)
class MfaBroker:
    requested: threading.Event = field(default_factory=threading.Event)
    supplied: threading.Event = field(default_factory=threading.Event)
    code: str | None = None

    def prompt(self) -> str:
        self.requested.set()
        if not self.supplied.wait(timeout=300):
            raise RuntimeError("Garmin MFA timed out after five minutes")
        if self.code is None:
            raise RuntimeError("Garmin MFA was cancelled")
        return self.code


@dataclass(slots=True)
class StoredPreview:
    value: RenphoPreview
    expires_at: float
    state: str = "available"


@dataclass(slots=True)
class AvatarCache:
    content: bytes | None = None
    mimetype: str | None = None
    expires_at: float = 0


@dataclass(slots=True)
class WebApiState:
    service: Any
    jobs: Any
    csrf_token: str
    latest_renpho: list[LatestRenphoReport]
    latest_error: list[str]
    weekly_reports: dict[str, WeeklyReportResult]
    latest_weekly_id: list[str]
    previews: dict[str, StoredPreview]
    events: list[str]
    garmin_status: list[OperationResult]
    garmin_profile: list[GarminProfile] = field(default_factory=list)
    avatar: AvatarCache = field(default_factory=AvatarCache)
    dashboard_reports: dict[int, tuple[str, WeeklyReportResult]] = field(default_factory=dict)
    health_contexts: dict[str, HealthContextResult] = field(default_factory=dict)
    latest_health_context_ids: dict[str, str] = field(default_factory=dict)
    token_store: TokenStore | None = None
    renpho_store: RenphoStore | None = None
    completed_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    mfa: dict[str, MfaBroker] = field(default_factory=dict)
    job_kinds: dict[str, str] = field(default_factory=dict)
    renpho_authenticated: bool = False
    account_generation: int = 0
    job_generations: dict[str, int] = field(default_factory=dict)


def register_api(app: Any, state: WebApiState) -> None:
    """Expose the local UI contract over the shared service and in-memory job state."""
    api = Blueprint("api_v1", __name__, url_prefix="/api/v1")

    def envelope(
        status: str,
        data: dict[str, Any] | list[Any] | None = None,
        *,
        code: int = 200,
        error: str | None = None,
    ) -> Response:
        payload: dict[str, Any] = {"status": status, "data": data}
        if error is not None:
            payload["error"] = {"code": status, "message": error}
        response = jsonify(payload)
        response.status_code = code
        return response

    def parse(model: type[Any]) -> Any:
        return model.model_validate(request.get_json(silent=False))

    def start(operation: Any, *, kind: str) -> Response:
        generation = state.account_generation

        def run_for_account() -> Any:
            if generation != state.account_generation and kind not in _LOGIN_KINDS:
                raise RuntimeError("Account changed; start this operation again")
            return operation()

        job_id = state.jobs.submit(run_for_account)
        state.job_kinds[job_id] = kind
        state.job_generations[job_id] = generation
        state.events.append(f"{kind}: started")
        return envelope("queued", {"job_id": job_id, "kind": kind}, code=202)

    def _claim_preview(
        previews: dict[str, StoredPreview], preview_id: str
    ) -> RenphoPreview | Response:
        stored = previews.get(preview_id)
        if stored is None:
            return envelope("not_found", code=404, error="Sync preview is unavailable")
        if stored.expires_at <= monotonic():
            previews.pop(preview_id, None)
            return envelope(
                "expired", code=410, error="Sync preview expired; generate a new preview"
            )
        if stored.state != "available":
            return envelope("conflict", code=409, error="This sync preview was already used")
        stored.state = "claimed"
        return stored.value

    def _status_with_profile() -> OperationResult:
        result = cast(OperationResult, state.service.status())
        state.garmin_status[:] = [result]
        if result.status == ResultStatus.SUCCESS:
            try:
                profile = state.service.garmin.profile()
            except Exception:
                state.garmin_profile.clear()
            else:
                state.garmin_profile[:] = [profile]
                state.avatar = AvatarCache()
        else:
            state.garmin_profile.clear()
            state.avatar = AvatarCache()
        return result

    def clear_snapshots() -> None:
        """Invalidate account-dependent reports and write previews after a source changes."""
        state.account_generation += 1
        state.latest_renpho.clear()
        state.latest_error.clear()
        state.weekly_reports.clear()
        state.latest_weekly_id.clear()
        state.dashboard_reports.clear()
        state.health_contexts.clear()
        state.latest_health_context_ids.clear()
        state.previews.clear()

    @api.errorhandler(PydanticValidationError)
    def invalid_payload(exc: PydanticValidationError) -> Response:
        first = exc.errors(include_url=False)[0]
        message = str(first.get("msg", "Invalid request"))
        return envelope("validation_error", code=400, error=message)

    @api.get("/bootstrap")
    def bootstrap() -> Response:
        garmin = state.garmin_status[-1] if state.garmin_status else None
        profile = state.garmin_profile[-1] if state.garmin_profile else None
        return envelope(
            "success",
            {
                "version": __version__,
                "csrf_token": state.csrf_token,
                "timezone": "Europe/Berlin",
                "busy": state.jobs.busy,
                "sources": {
                    "garmin": _source_status(garmin),
                    "renpho": {
                        "connected": state.renpho_authenticated or bool(state.latest_renpho),
                        "label": "RENPHO",
                        "detail": (
                            "Latest measurement loaded"
                            if state.latest_renpho
                            else "RENPHO connected; refresh the latest measurement"
                            if state.renpho_authenticated
                            else state.latest_error[-1]
                            if state.latest_error
                            else "Not connected"
                        ),
                    },
                },
                "profile": {
                    "display_name": profile.display_name,
                    "initials": profile.initials,
                    "avatar_available": bool(profile.avatar_url),
                }
                if profile is not None
                else None,
                "capabilities": {
                    "gui_auth": state.token_store is not None,
                    "renpho_auth": state.renpho_store is not None,
                    "weekly_report": True,
                    "body_measurements": True,
                    "local_archive": True,
                    "ai_health_context": True,
                },
                "latest_weekly_report_id": (
                    state.latest_weekly_id[-1] if state.latest_weekly_id else None
                ),
                "latest_health_context_ids": dict(state.latest_health_context_ids),
            },
        )

    @api.get("/dashboard")
    def dashboard() -> Response:
        period = request.args.get("period_days", "7")
        if period not in {"1", "7", "30"}:
            return envelope("validation_error", code=400, error="period_days must be 1, 7 or 30")
        latest = _latest_payload(state.latest_renpho[-1]) if state.latest_renpho else None
        selected = state.dashboard_reports.get(int(period))
        report_id, report = selected if selected is not None else (None, None)
        if report is None and period == "7" and state.latest_weekly_id:
            report_id = state.latest_weekly_id[-1]
            report = state.weekly_reports.get(report_id)
        return envelope(
            "success",
            {
                "latest_body": latest,
                "report": _report_payload(report_id, report) if report and report_id else None,
                "events": list(reversed(state.events[-20:])),
            },
        )

    @api.post("/dashboard/refresh")
    def dashboard_refresh() -> Response:
        payload = parse(DashboardRefreshRequest)
        return start(
            lambda: state.service.build_comprehensive_report(
                period=payload.period_days,
                lifestyle_context=max(30, payload.period_days),
            ),
            kind=f"dashboard-{payload.period_days}-days",
        )

    @api.get("/profile/avatar")
    def profile_avatar() -> Response:
        profile = state.garmin_profile[-1] if state.garmin_profile else None
        if profile is None or not profile.avatar_url:
            return envelope("not_found", code=404, error="Garmin avatar is unavailable")
        try:
            content, mimetype = _avatar_bytes(profile.avatar_url, state.avatar)
        except ValueError:
            return envelope("not_found", code=404, error="Garmin avatar is unavailable")
        return Response(content, mimetype=mimetype)

    @api.post("/sources/status")
    def refresh_status() -> Response:
        return start(lambda: _status_with_profile(), kind="source-status")

    @api.get("/schedule")
    def schedule_status() -> Response:
        status = Scheduler().status()
        return envelope(
            "success",
            {
                "supported": status.supported,
                "installed": status.installed,
                "loaded": status.loaded,
                "legacy": status.legacy,
                "detail": status.detail,
            },
        )

    @api.get("/archive")
    def archive_status() -> Response:
        return envelope("success", _archive_payload(state.service.archive_status()))

    @api.post("/archive/setup")
    def archive_setup() -> Response:
        return start(state.service.archive_initialize, kind="archive-setup")

    @api.post("/archive/refresh")
    def archive_refresh() -> Response:
        return start(state.service.archive_refresh, kind="archive-refresh")

    @api.post("/archive/backfill")
    def archive_backfill() -> Response:
        payload = parse(ArchiveBackfillRequest)
        return start(lambda: state.service.archive_backfill(payload.days), kind="archive-backfill")

    @api.post("/archive/open")
    def archive_open() -> Response:
        status = state.service.archive_status()
        if not status.exists:
            return envelope("not_found", code=404, error="Set up the local archive first")
        try:
            Scheduler().open_archive(str(status.root))
        except SchedulerError as exc:
            return envelope("unavailable", code=501, error=str(exc))
        return envelope("success", {"opened": True})

    @api.post("/schedule/install")
    def schedule_install() -> Response:
        payload = parse(ScheduleRequest)

        def install_daily() -> OperationResult:
            try:
                Scheduler().install(hour=payload.hour, minute=payload.minute)
                return OperationResult(ResultStatus.SUCCESS, "Daily Docker sync scheduled")
            except SchedulerError as exc:
                return OperationResult(ResultStatus.ERROR, str(exc))

        return start(install_daily, kind="schedule-install")

    @api.post("/schedule/run")
    def schedule_run() -> Response:
        def run_schedule() -> OperationResult:
            try:
                Scheduler().run_now()
                return OperationResult(ResultStatus.SUCCESS, "Scheduled sync started")
            except SchedulerError as exc:
                return OperationResult(ResultStatus.ERROR, str(exc))

        return start(run_schedule, kind="schedule-run")

    @api.post("/schedule/uninstall")
    def schedule_uninstall() -> Response:
        def remove_schedule() -> OperationResult:
            try:
                removed = Scheduler().uninstall()
                message = "Daily schedule removed" if removed else "No schedule was installed"
                return OperationResult(ResultStatus.SUCCESS, message)
            except SchedulerError as exc:
                return OperationResult(ResultStatus.ERROR, str(exc))

        return start(remove_schedule, kind="schedule-uninstall")

    @api.post("/auth/garmin/login")
    def garmin_login() -> Response:
        if state.token_store is None:
            return envelope("unavailable", code=501, error="GUI authentication is unavailable")
        payload = parse(GarminLoginRequest)
        broker = MfaBroker()

        def login() -> OperationResult:
            try:
                name = state.service.garmin.login(payload.email, payload.password, broker.prompt)
                clear_snapshots()
                state.garmin_profile.clear()
                state.avatar = AvatarCache()
                result = OperationResult(ResultStatus.SUCCESS, f"Connected: {name}")
                state.garmin_status[:] = [result]
                return result
            except Exception as exc:
                return OperationResult(ResultStatus.ERROR, _safe_error(exc))

        response = start(login, kind="garmin-login")
        body = response.get_json(silent=True) or {}
        job_id = (body.get("data") or {}).get("job_id")
        if isinstance(job_id, str):
            state.mfa[job_id] = broker
        return response

    @api.post("/auth/garmin/mfa")
    def garmin_mfa() -> Response:
        payload = parse(MfaRequest)
        broker = state.mfa.get(payload.job_id)
        if broker is None or not broker.requested.is_set() or broker.supplied.is_set():
            return envelope("conflict", code=409, error="This MFA challenge is not active")
        broker.code = payload.code
        broker.supplied.set()
        return envelope("success", {"job_id": payload.job_id})

    @api.post("/auth/garmin/logout")
    def garmin_logout() -> Response:
        if state.token_store is None:
            return envelope("unavailable", error="GUI authentication is unavailable")
        if state.jobs.busy:
            return envelope("conflict", code=409, error="Wait for active operations to finish")
        removed = state.token_store.delete()
        state.service.garmin.clear_session()
        clear_snapshots()
        state.garmin_profile.clear()
        state.avatar = AvatarCache()
        state.garmin_status[:] = [
            OperationResult(ResultStatus.AUTH_REQUIRED, "No saved Garmin session")
        ]
        return envelope("success", {"removed": removed})

    @api.post("/auth/renpho/login")
    def renpho_login() -> Response:
        renpho_store = state.renpho_store
        if renpho_store is None:
            return envelope("unavailable", code=501, error="RENPHO setup is unavailable")
        payload = parse(RenphoLoginRequest)

        def login() -> OperationResult:
            try:
                RenphoCloud(SuppliedCredentials(payload.email, payload.password)).authenticate()
                renpho_store.save(payload.email, payload.password)
                state.service.renpho.clear_session()
                clear_snapshots()
                state.renpho_authenticated = True
                return OperationResult(ResultStatus.SUCCESS, "RENPHO connected")
            except Exception as exc:
                return OperationResult(ResultStatus.ERROR, _safe_error(exc))

        return start(login, kind="renpho-login")

    @api.post("/auth/renpho/logout")
    def renpho_logout() -> Response:
        if state.renpho_store is None:
            return envelope("unavailable", error="RENPHO setup is unavailable")
        if state.jobs.busy:
            return envelope("conflict", code=409, error="Wait for active operations to finish")
        removed = state.renpho_store.delete()
        state.service.renpho.clear_session()
        clear_snapshots()
        state.renpho_authenticated = False
        return envelope("success", {"removed": removed})

    @api.post("/pressure/preview")
    def pressure_preview() -> Response:
        measurement = _pressure(parse(PressureRequest))
        return envelope(
            "success",
            {"measurement": _pressure_payload(measurement), "summary": measurement.summary()},
        )

    @api.post("/pressure")
    def pressure_submit() -> Response:
        measurement = _pressure(parse(PressureRequest))
        return start(lambda: state.service.add_pressure(measurement), kind="blood-pressure")

    @api.post("/renpho/latest")
    def renpho_latest() -> Response:
        return start(state.service.latest_report, kind="renpho-latest")

    @api.post("/renpho/history")
    def renpho_history() -> Response:
        return start(state.service.renpho_history, kind="renpho-history")

    @api.post("/renpho/sync/preview")
    def renpho_sync_preview() -> Response:
        payload = parse(SyncPreviewRequest)
        return start(lambda: state.service.preview_renpho(payload.mode), kind="renpho-preview")

    @api.post("/renpho/sync/<preview_id>")
    def renpho_sync(preview_id: str) -> Response:
        preview = _claim_preview(state.previews, preview_id)
        if isinstance(preview, Response):
            return preview
        response = start(lambda: state.service.sync_renpho(preview), kind="renpho-sync")
        if response.status_code == 202:
            state.previews[preview_id].state = "consumed"
        else:
            state.previews[preview_id].state = "available"
        return response

    @api.post("/reports/weekly")
    def weekly_generate() -> Response:
        payload = parse(WeeklyReportRequest)
        include_routes = payload.include_routes or payload.map_tiles_enabled

        def build_and_archive() -> WeeklyReportResult:
            result = cast(
                WeeklyReportResult,
                state.service.build_weekly_report(
                    include_routes=include_routes,
                    map_tiles_enabled=payload.map_tiles_enabled,
                ),
            )
            archive_operation = getattr(state.service, "archive_report", None)
            if callable(archive_operation):
                archive_operation(result)
            return result

        return start(
            build_and_archive,
            kind="weekly-report",
        )

    @api.get("/reports/weekly/<report_id>")
    def weekly_data(report_id: str) -> Response:
        result = state.weekly_reports.get(report_id)
        if result is None:
            return envelope("not_found", code=404, error="Report is unavailable")
        return envelope("success", _report_payload(report_id, result))

    @api.post("/reports/weekly/<report_id>/download")
    def weekly_download(report_id: str) -> Response:
        result = state.weekly_reports.get(report_id)
        if result is None:
            return envelope("not_found", code=404, error="Report is unavailable")
        report = result.report
        filename = f"weekly-health-report-{_download_stamp(report.generated_at)}.pdf"
        response = Response(result.pdf, mimetype="application/pdf")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @api.post("/reports/weekly/<report_id>/markdown")
    def weekly_markdown_download(report_id: str) -> Response:
        result = state.weekly_reports.get(report_id)
        if result is None:
            return envelope("not_found", code=404, error="Report is unavailable")
        report = result.report
        filename = f"weekly-health-report-{_download_stamp(report.generated_at)}.md"
        response = Response(render_weekly_markdown(report), mimetype="text/markdown")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @api.post("/ai-context/generate")
    def ai_context_generate() -> Response:
        payload = cast(HealthContextRequest, parse(HealthContextRequest))
        return start(
            lambda: state.service.build_health_context(payload.period),
            kind="ai-health-context",
        )

    @api.get("/ai-context/<context_id>")
    def ai_context_metadata(context_id: str) -> Response:
        result = state.health_contexts.get(context_id)
        if result is None:
            return envelope("not_found", code=404, error="AI health context is unavailable")
        return envelope("success", _health_context_payload(context_id, result))

    @api.post("/ai-context/<context_id>/json")
    def ai_context_json(context_id: str) -> Response:
        result = state.health_contexts.get(context_id)
        if result is None:
            return envelope("not_found", code=404, error="AI health context is unavailable")
        filename = (
            f"health-context-{result.context.period.kind}-"
            f"{_download_stamp(result.context.generated_at)}.json"
        )
        response = Response(result.json_content, mimetype="application/json")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @api.post("/ai-context/<context_id>/markdown")
    def ai_context_markdown(context_id: str) -> Response:
        result = state.health_contexts.get(context_id)
        if result is None:
            return envelope("not_found", code=404, error="AI health context is unavailable")
        filename = (
            f"health-context-{result.context.period.kind}-"
            f"{_download_stamp(result.context.generated_at)}.md"
        )
        response = Response(result.markdown, mimetype="text/markdown")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @api.post("/reports/renpho/download")
    def renpho_download() -> Response:
        if not state.latest_renpho:
            return envelope("not_found", code=404, error="RENPHO report is unavailable")
        latest = state.latest_renpho[-1]
        day = latest.measurement.body.measured_at.date()
        response = Response(latest.document.content, mimetype="application/pdf")
        response.headers["Content-Disposition"] = (
            f'attachment; filename="renpho-body-composition-{day}.pdf"'
        )
        return response

    @api.get("/jobs")
    def jobs_list() -> Response:
        return envelope(
            "success",
            [
                _job_payload(job_id, state, include_result=False)
                for job_id in reversed(list(state.jobs.jobs)[-20:])
            ],
        )

    @api.get("/jobs/<job_id>")
    def job(job_id: str) -> Response:
        if job_id not in state.jobs.jobs:
            return envelope("not_found", code=404, error="Job not found")
        return envelope("success", _job_payload(job_id, state, include_result=True))

    app.register_blueprint(api)


def _source_status(result: OperationResult | None) -> dict[str, Any]:
    return {
        "connected": result is not None and result.status == ResultStatus.SUCCESS,
        "label": "Garmin Connect",
        "detail": result.message if result is not None else "Checking connection",
    }


def _pressure(payload: PressureRequest) -> BloodPressure:
    measured = payload.measured_at
    if measured.tzinfo is None:
        measured = parse_local_datetime(measured.isoformat())
    else:
        measured = measured.astimezone(BERLIN)
    return BloodPressure(
        measured_at=measured,
        systolic=payload.systolic,
        diastolic=payload.diastolic,
        pulse=payload.pulse,
        notes=payload.notes.strip(),
    )


def _pressure_payload(value: BloodPressure) -> dict[str, Any]:
    return {
        "measured_at": value.measured_at.isoformat(),
        "systolic": value.systolic,
        "diastolic": value.diastolic,
        "pulse": value.pulse,
        "notes": value.notes,
    }


def _latest_payload(value: LatestRenphoReport) -> dict[str, Any]:
    body = value.measurement.body
    return {
        "measured_at": body.measured_at.isoformat(),
        "summary": [{"label": key, "value": item} for key, item in body.summary()],
        "weight_kg": body.weight,
        "report_source": value.document.source,
    }


def _archive_payload(value: ArchiveStatus) -> dict[str, Any]:
    return {
        "path": os.environ.get("GARMIN_SYNC_ARCHIVE_DISPLAY_PATH", str(value.root)),
        "ready": value.exists,
        "daily_documents": value.daily_documents,
        "weekly_documents": value.weekly_documents,
        "last_updated": value.last_updated,
    }


def _download_stamp(generated_at: datetime) -> str:
    """Return a filesystem-safe Berlin timestamp for generated downloads."""
    localized = (
        generated_at.replace(tzinfo=BERLIN)
        if generated_at.tzinfo is None
        else generated_at.astimezone(BERLIN)
    )
    return localized.strftime("%Y-%m-%d_%H-%M-%S")


def _report_payload(report_id: str, result: WeeklyReportResult) -> dict[str, Any]:
    """Serialize normalized report models without exposing provider payloads or PDF bytes."""
    report = result.report
    return {
        "id": report_id,
        "status": result.status.value,
        "start_date": report.start_date.isoformat(),
        "end_date": report.end_date.isoformat(),
        "generated_at": report.generated_at.isoformat(),
        "availability": asdict(report.availability),
        "summary": {
            "training_minutes": round(report.total_training_minutes),
            "activities": len(report.activities),
            "pressure_days": report.pressure.days_covered,
            "weight_points": len(report.body),
        },
        "vo2_max": report.vo2_max,
        "activities": [
            {
                "id": item.activity_id,
                "name": item.name,
                "type": item.activity_type,
                "measured_at": item.measured_at.isoformat(),
                "duration_minutes": item.duration_minutes,
                "distance_km": item.distance_km,
                "calories": item.calories,
                "average_hr": item.average_hr,
                "max_hr": item.max_hr,
            }
            for item in report.activities
        ],
        "insights": [asdict(item) for item in report.insights],
        "charts": chart_payload(report),
        "lifestyle": [asdict(item) for item in report.comprehensive.lifestyle],
        "associations": [asdict(item) for item in report.comprehensive.associations],
    }


def _health_context_payload(context_id: str, result: HealthContextResult) -> dict[str, Any]:
    context = result.context
    return {
        "id": context_id,
        "status": result.status.value,
        "period": context.period.kind,
        "start_date": context.period.start_date.isoformat(),
        "end_date": context.period.end_date.isoformat(),
        "generated_at": context.generated_at.isoformat(),
        "archived": result.archived,
        "summary": {
            "activities": context.training_summary.total_sessions,
            "training_minutes": round(context.training_summary.total_duration_minutes),
            "pressure_days": context.blood_pressure.days_covered,
            "body_measurements": len(context.body_measurements),
        },
        "availability": context.availability.model_dump(mode="json"),
    }


def _job_payload(job_id: str, state: WebApiState, *, include_result: bool) -> dict[str, Any]:
    """Project a Future into UI state, consuming completed results once per job."""
    if (
        state.job_generations.get(job_id, 0) != state.account_generation
        and state.job_kinds.get(job_id) not in _LOGIN_KINDS
    ):
        return {
            "id": job_id,
            "state": "error",
            "error": {"code": "account_changed", "message": "Account changed; start again"},
        }
    if job_id in state.completed_jobs:
        return state.completed_jobs[job_id]
    job = state.jobs.jobs[job_id]
    broker = state.mfa.get(job_id)
    if (
        not job.future.done()
        and broker is not None
        and broker.requested.is_set()
        and not broker.supplied.is_set()
    ):
        return {"id": job_id, "state": "awaiting_input", "stage": "Enter Garmin MFA code"}
    if not job.future.done():
        progress = state.service.get_report_progress(job_id)
        return {
            "id": job_id,
            "state": "running" if job.started.is_set() else "queued",
            **progress,
        }
    try:
        result = job.future.result()
        payload = _consume_result(result, state, kind=state.job_kinds.get(job_id, "weekly-report"))
        final = {"id": job_id, "state": _terminal_state(result), "result": payload}
    except Exception as exc:
        final = {
            "id": job_id,
            "state": "error",
            "error": {"code": "operation_error", "message": _safe_error(exc)},
        }
    state.completed_jobs[job_id] = final
    state.mfa.pop(job_id, None)
    if include_result:
        return final
    return {key: value for key, value in final.items() if key != "result"}


def _consume_result(
    result: Any, state: WebApiState, *, kind: str = "weekly-report"
) -> dict[str, Any] | list[Any]:
    """Publish completed results while keeping dashboard periods separate from exports."""
    if isinstance(result, OperationResult):
        state.events.append(f"Operation: {result.status.value}")
        return {"type": "operation", "status": result.status.value, "message": result.message}
    if isinstance(result, RenphoPreview):
        preview_id = secrets.token_urlsafe(18)
        state.previews[preview_id] = StoredPreview(result, monotonic() + 600)
        return {
            "type": "renpho_preview",
            "preview_id": preview_id,
            "mode": result.mode,
            "count": result.count,
            "skipped": result.skipped,
            "measurements": [
                {
                    "measured_at": item.body.measured_at.isoformat(),
                    "weight_kg": item.body.weight,
                }
                for item in result.candidates
            ],
        }
    if isinstance(result, LatestRenphoReport):
        state.latest_renpho[:] = [result]
        state.latest_error.clear()
        state.events.append("RENPHO latest measurement refreshed")
        return {"type": "renpho_latest", **_latest_payload(result)}
    if isinstance(result, ArchiveStatus):
        state.events.append("Local archive structure prepared")
        return {"type": "archive_status", **_archive_payload(result)}
    if isinstance(result, RenphoHistory):
        return {
            "type": "renpho_history",
            "measurements": [
                {
                    "measured_at": item.body.measured_at.isoformat(),
                    "weight_kg": item.body.weight,
                    "body_fat_pct": (
                        item.report.body_fat_percentage.value if item.report else None
                    ),
                    "whr": item.report.whr if item.report else None,
                }
                for item in result.measurements
            ],
            "girth": [
                {
                    "measured_at": item.measured_at.isoformat(),
                    "values": [asdict(value) for value in item.values],
                }
                for item in result.girth_measurements
            ],
        }
    if isinstance(result, WeeklyReportResult):
        report_id = secrets.token_urlsafe(24)
        state.weekly_reports[report_id] = result
        if kind == "weekly-report":
            state.latest_weekly_id[:] = [report_id]
        period_days = (result.report.end_date - result.report.start_date).days + 1
        if period_days in {1, 7, 30}:
            state.dashboard_reports[period_days] = (report_id, result)
        state.events.append(
            f"Weekly report: {result.status.value} for {result.report.start_date} "
            f"to {result.report.end_date}"
        )
        return {"type": "weekly_report", **_report_payload(report_id, result)}
    if isinstance(result, HealthContextResult):
        context_id = secrets.token_urlsafe(24)
        state.health_contexts[context_id] = result
        state.latest_health_context_ids[result.context.period.kind] = context_id
        state.events.append(f"AI context: {result.status.value} for {result.context.period.kind}")
        return {
            "type": "health_context",
            **_health_context_payload(context_id, result),
        }
    if isinstance(result, list):
        return [
            {
                "type": "operation",
                "status": item.status.value,
                "message": item.message,
            }
            for item in result
            if isinstance(item, OperationResult)
        ]
    return {"type": "unknown", "message": "Operation completed"}


def _terminal_state(result: Any) -> str:
    """Reflect the business outcome instead of treating a completed Future as success."""
    if isinstance(result, (RenphoPreview, LatestRenphoReport, RenphoHistory)):
        return "verified"
    if isinstance(result, (WeeklyReportResult, HealthContextResult)):
        return "verified" if result.status == ResultStatus.SUCCESS else result.status.value
    statuses: list[str] = []
    if isinstance(result, OperationResult):
        statuses = [result.status.value]
    elif isinstance(result, list):
        statuses = [item.status.value for item in result if isinstance(item, OperationResult)]
    if not statuses:
        return "verified"
    if "uncertain" in statuses:
        return "uncertain"
    if "auth_required" in statuses:
        return "auth_required"
    if "rate_limited" in statuses:
        return "rate_limited"
    if "error" in statuses:
        return (
            "partial"
            if any(status in {"success", "already_exists"} for status in statuses)
            else "error"
        )
    if "conflict" in statuses:
        return (
            "partial"
            if any(status in {"success", "already_exists"} for status in statuses)
            else "conflict"
        )
    if all(status == "already_exists" for status in statuses):
        return "already_exists"
    return "verified"


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, (ValidationError, RuntimeError)):
        return str(exc)
    name = exc.__class__.__name__
    if name in {
        "AuthenticationRequired",
        "GarminSyncError",
        "RateLimited",
        "RenphoError",
        "SecretStoreError",
        "ScheduleError",
    }:
        return str(exc)
    return "Internal error; no data was changed"


_LOGIN_KINDS = {"garmin-login", "renpho-login"}
_AVATAR_HOSTS = {"s3.amazonaws.com"}
_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _avatar_bytes(url: str, cache: AvatarCache) -> tuple[bytes, str]:
    """Fetch a bounded, signature-checked image from an allowed HTTPS host into memory."""
    if cache.content is not None and cache.mimetype is not None and cache.expires_at > monotonic():
        return cache.content, cache.mimetype
    current = url
    for _ in range(2):
        parsed = urlparse(current)
        if parsed.scheme != "https" or not _allowed_avatar_host(parsed.hostname):
            raise ValueError("untrusted avatar host")
        try:
            response = requests.get(current, stream=True, timeout=(3, 8), allow_redirects=False)
        except requests.RequestException as exc:
            raise ValueError("avatar unavailable") from exc
        if response.is_redirect:
            location = response.headers.get("Location")
            if not location:
                raise ValueError("invalid avatar redirect")
            current = urljoin(current, location)
            continue
        if response.status_code != 200:
            raise ValueError("avatar unavailable")
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if content_type not in _AVATAR_TYPES:
            raise ValueError("invalid avatar type")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(65_536):
            total += len(chunk)
            if total > 2 * 1024 * 1024:
                raise ValueError("avatar too large")
            chunks.append(chunk)
        content = b"".join(chunks)
        if not _valid_avatar_signature(content, content_type):
            raise ValueError("invalid avatar image")
        cache.content, cache.mimetype, cache.expires_at = content, content_type, monotonic() + 900
        return content, content_type
    raise ValueError("too many avatar redirects")


def _allowed_avatar_host(hostname: str | None) -> bool:
    if hostname is None:
        return False
    host = hostname.lower()
    return host in _AVATAR_HOSTS or host.endswith(".garmin.com") or host.endswith(".amazonaws.com")


def _valid_avatar_signature(content: bytes, mimetype: str) -> bool:
    return (
        (mimetype == "image/png" and content.startswith(b"\x89PNG\r\n\x1a\n"))
        or (mimetype == "image/jpeg" and content.startswith(b"\xff\xd8\xff"))
        or (
            mimetype == "image/webp"
            and len(content) >= 12
            and content[:4] == b"RIFF"
            and content[8:12] == b"WEBP"
        )
    )
