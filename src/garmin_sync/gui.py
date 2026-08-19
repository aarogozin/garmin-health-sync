from __future__ import annotations

import os
import secrets
import threading
import uuid
import webbrowser
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from importlib.resources import files
from socketserver import TCPServer
from typing import Any

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template_string,
    request,
    url_for,
)
from werkzeug.serving import BaseWSGIServer

from .garmin import GarminClient
from .models import BloodPressure, ValidationError, local_now, parse_local_datetime
from .renpho import RenphoCloud, RenphoMeasurement
from .secrets import configured_stores
from .service import (
    OPTIONAL_REPORT_SECTIONS,
    HealthSyncService,
    LatestRenphoReport,
    OperationResult,
    RenphoHistory,
    RenphoPreview,
    WeeklyReportResult,
)
from .state import SyncState
from .weekly_report import chart_payload, render_weekly_html
from .weekly_web import CHART_JAVASCRIPT

PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
{% if refresh %}<meta http-equiv=refresh content="1">{% endif %}
<title>Garmin Health Sync</title><style>
body{font:16px system-ui;max-width:760px;margin:32px auto;padding:0 18px;color:#17202a;background:#f5f7fa}
section{background:white;padding:22px;margin:16px 0;border-radius:12px;box-shadow:0 2px 12px #0001}
label{display:block;margin:10px 0}input,textarea{box-sizing:border-box;width:100%;padding:9px;margin-top:4px}
button{padding:10px 16px;margin:5px 4px 5px 0;background:#176b52;color:white;border:0;border-radius:7px}
button[disabled]{opacity:.45}.error,.uncertain{color:#a02b2b}.success{color:#176b52}.log{white-space:pre-wrap}.confidence{display:inline-block;background:#edf2f7;color:#52606d;border-radius:999px;padding:2px 7px;font-size:12px;margin-left:5px}
table{width:100%;border-collapse:collapse;margin:12px 0}th,td{padding:8px;border-bottom:1px solid #dbe4e0;text-align:left}th{width:55%}
.hero{background:linear-gradient(135deg,#172b4d,#244f86);color:white}.hero h2{font-size:34px;margin:4px 0}.eyebrow{font-size:12px;letter-spacing:.16em;color:#8dc6ff}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:22px}.metrics div{background:#ffffff16;border:1px solid #ffffff2c;padding:14px;border-radius:9px}.metrics strong,.metrics span{display:block}.metrics strong{font-size:24px}.metrics span{font-size:11px;text-transform:uppercase}.bars{height:130px;display:flex;align-items:flex-end;gap:7px;border-bottom:1px solid #ccd6e0;padding:8px}.bars span{flex:1;min-width:8px;border-radius:4px 4px 0 0}.trend{display:flex;align-items:center;gap:12px;background:#f1f6fb;padding:14px;border-radius:9px}.trend span{height:3px;background:#4776e6;flex:1}.caution{color:#8a5a00}.alert{color:#a02b2b}@media(max-width:620px){.metrics{grid-template-columns:repeat(2,1fr)}table{font-size:12px;display:block;overflow-x:auto}}
.chart-grid,.route-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}.chart-panel,.route-panel{border:1px solid #dbe4e0;border-radius:10px;padding:12px}.interactive-chart svg,.route-chart svg{display:block;width:100%;height:auto}.axis{stroke:#ccd6e0}.chart-legend{display:flex;flex-wrap:wrap;gap:6px}.chart-legend button{background:white;color:#17202a;border:2px solid;padding:5px 8px}.chart-legend button[aria-pressed=false]{opacity:.4}.lifestyle-marker{stroke:#9b59b6;stroke-width:2;stroke-dasharray:6 5;opacity:.7}.lifestyle-list{display:flex;flex-wrap:wrap;gap:6px}.lifestyle-chip{display:inline-block;background:#f0ebfa;color:#52377b;border:1px solid #d8c9ed;border-radius:999px;padding:4px 9px;font-size:13px}.map-attribution{font-size:11px;text-align:right;margin:3px 6px}.map-tiles{opacity:.88}progress{width:100%;height:18px;accent-color:#4776e6}#chart-tooltip{position:fixed;z-index:20;background:#17202a;color:white;padding:7px 9px;border-radius:5px;font-size:12px;pointer-events:none}details summary{cursor:pointer;padding:8px}
.body-measurement-card{border:1px solid #dbe4e0;border-radius:12px;padding:16px;margin:14px 0}.body-measurement-layout{display:grid;grid-template-columns:minmax(280px,1.15fr) minmax(230px,.85fr);gap:18px;align-items:start}.body-map{background:linear-gradient(180deg,#f7fbff,#eef5f2);border-radius:12px;padding:8px}.body-map svg{display:block;width:100%;height:auto}.body-map .figure{fill:#dce9e5;stroke:#176b52;stroke-width:2}.body-map .measure-line{stroke:#4776e6;stroke-width:2;fill:none}.body-map .measure-dot{fill:#4776e6}.body-map .measure-label{font:600 12px system-ui;fill:#17202a}.body-map .measure-value{font:11px system-ui;fill:#52606d}@media(max-width:680px){.body-measurement-layout{grid-template-columns:1fr}}
</style></head><body><h1>Garmin Health Sync</h1>{{ body|safe }}</body></html>"""


@dataclass(slots=True)
class Job:
    future: Future[Any]


class JobManager:
    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="garmin-sync")
        self.jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._busy = False

    def submit(self, operation: Callable[[], Any]) -> str | None:
        with self._lock:
            if self._busy:
                return None
            self._busy = True

        def run() -> Any:
            try:
                return operation()
            finally:
                with self._lock:
                    self._busy = False

        job_id = uuid.uuid4().hex
        self.jobs[job_id] = Job(self.executor.submit(run))
        return job_id

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy


class LoopbackWSGIServer(BaseWSGIServer):
    """Werkzeug server without macOS's potentially blocking FQDN lookup."""

    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


def create_app(service: HealthSyncService | None = None, csrf_token: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16_384)
    token = csrf_token or secrets.token_urlsafe(32)
    if service is None:
        token_store, renpho_store = configured_stores()
        sync_service = HealthSyncService(
            GarminClient(token_store), RenphoCloud(renpho_store), SyncState()
        )
    else:
        sync_service = service
    jobs = JobManager()
    startup_ready = threading.Event()
    app.extensions["garmin_sync_startup_ready"] = startup_ready
    previews: dict[str, RenphoPreview] = {}
    latest_renpho: list[LatestRenphoReport] = []
    latest_error: list[str] = []
    events: list[str] = []
    weekly_reports: dict[str, WeeklyReportResult] = {}
    latest_weekly_id: list[str] = []

    @app.before_request
    def protect_request() -> Response | None:
        allowed_hosts = {"127.0.0.1", "localhost"}
        if public_host := os.environ.get("GARMIN_SYNC_PUBLIC_HOST"):
            allowed_hosts.add(public_host)
        if request.host.split(":", 1)[0] not in allowed_hosts:
            abort(400)
        if request.method == "POST":
            origin = request.headers.get("Origin")
            same_origin_null = (
                origin == "null" and request.headers.get("Sec-Fetch-Site") == "same-origin"
            )
            if (
                origin
                and not same_origin_null
                and origin.split("//", 1)[-1].split(":", 1)[0] not in allowed_hosts
            ):
                abort(403)
            if not secrets.compare_digest(request.form.get("csrf", ""), token):
                abort(403)
        return None

    @app.after_request
    def secure_headers(response: Response) -> Response:
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; connect-src 'self'; "
            "img-src 'self' https://tile.openstreetmap.org; style-src 'unsafe-inline'; "
            "form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    def page(body: str, *, refresh: bool = False) -> str:
        return render_template_string(PAGE, body=body, refresh=refresh)

    @app.get("/health")
    def health() -> Response:
        return Response("ok\n", content_type="text/plain")

    @app.get("/")
    def index() -> str:
        disabled = "disabled" if jobs.busy else ""
        now = local_now().strftime("%Y-%m-%dT%H:%M")
        log = "\n".join(events[-20:]) or "No operations yet."
        latest = _renpho_card(latest_renpho[0], token) if latest_renpho else ""
        weekly_links = ""
        if latest_weekly_id:
            report_id = latest_weekly_id[0]
            weekly_links = (
                f"<p><a href='/weekly-report/{report_id}'>Open web report</a></p>"
                f"<form method=post action='/weekly-report/{report_id}/download'>"
                f"<input type=hidden name=csrf value='{_escape(token)}'>"
                "<button>Download PDF</button></form>"
            )
        if not latest and jobs.busy:
            latest = "<p>Loading the latest RENPHO measurement…</p>"
        elif not latest and latest_error:
            latest = f"<p class=error>{_escape(latest_error[-1])}</p>"
        return page(
            render_template_string(
                """
<section><h2>Garmin status</h2><form method=post action=/status><input type=hidden name=csrf value="{{csrf}}"><button {{disabled}}>Check connection</button></form></section>
<section><h2>Add blood pressure</h2><form method=post action=/pressure/confirm><input type=hidden name=csrf value="{{csrf}}">
<label>Date and time<input type=datetime-local name=measured_at required value="{{now}}"></label>
<label>Systolic, mmHg<input type=number name=systolic min=70 max=260 required></label>
<label>Diastolic, mmHg<input type=number name=diastolic min=40 max=150 required></label>
<label>Pulse, bpm<input type=number name=pulse min=20 max=250 required></label>
<label>Notes<textarea name=notes maxlength=500></textarea></label><button {{disabled}}>Review</button></form></section>
<section><h2>RENPHO data</h2>{{latest|safe}}<form method=post action=/renpho/latest><input type=hidden name=csrf value="{{csrf}}">
<button {{disabled}}>Refresh latest scale measurement</button></form></section>
<section><h2>Body measurements</h2><p>View your RENPHO waist, chest, arms, thighs, calves and other circumference measurements.</p><form method=post action=/renpho/history><input type=hidden name=csrf value="{{csrf}}"><button {{disabled}}>View body measurements</button></form></section>
<section><h2>RENPHO → Garmin</h2><form method=post action=/renpho/preview><input type=hidden name=csrf value="{{csrf}}">
<button name=mode value=latest {{disabled}}>Sync latest</button><button name=mode value=all {{disabled}}>Sync history</button></form></section>
<section><h2>Weekly health report</h2><p>Training, recovery, blood pressure and body-composition trends for today and the previous six days, with 30 days of Lifestyle Logging context.</p><form method=post action=/weekly-report/generate><input type=hidden name=csrf value="{{csrf}}"><label><input type=checkbox name=include_routes value=yes> Include activity routes and location names (kept in memory only)</label><label><input type=checkbox name=map_tiles value=yes> Show OpenStreetMap background (sends tile area and IP to OpenStreetMap)</label><br><button {{disabled}}>Generate 7-day health report</button></form>{{weekly_links|safe}}</section>
<section><h2>Run log</h2><div class=log>{{log}}</div></section>""",
                csrf=token,
                disabled=disabled,
                now=now,
                log=log,
                latest=latest,
                weekly_links=weekly_links,
            )
        )

    def start(operation: Callable[[], Any]) -> Any:
        job_id = jobs.submit(operation)
        if job_id is None:
            return Response(
                page("<section><h2>An operation is already running</h2><a href='/'>Back</a></section>"),
                status=409,
            )
        return redirect(url_for("job_status", job_id=job_id))

    @app.post("/status")
    def status() -> Any:
        return start(sync_service.status)

    @app.post("/pressure/confirm")
    def pressure_confirm() -> str:
        try:
            measurement = _pressure_from_form(request.form)
        except ValidationError as exc:
            return page(
                f"<section class=error><h2>Error</h2><p>{_escape(str(exc))}</p><a href='/'>Back</a></section>"
            )
        fields = _pressure_hidden(measurement, token)
        summary = "".join(f"<li>{_escape(k)}: {_escape(v)}</li>" for k, v in measurement.summary())
        return page(
            f"<section><h2>Confirm upload</h2><ul>{summary}</ul><form method=post action=/pressure/submit>{fields}<button>Upload to Garmin</button></form><a href='/'>Cancel</a></section>"
        )

    @app.post("/pressure/submit")
    def pressure_submit() -> Any:
        try:
            measurement = _pressure_from_form(request.form)
        except ValidationError as exc:
            return Response(
                page(
                    f"<section class=error><h2>Error</h2><p>{_escape(str(exc))}</p><a href='/'>Back</a></section>"
                ),
                status=400,
            )
        return start(lambda: sync_service.add_pressure(measurement))

    @app.post("/renpho/preview")
    def renpho_preview() -> Any:
        mode = request.form.get("mode", "")
        return start(lambda: sync_service.preview_renpho(mode))

    @app.post("/renpho/latest")
    def renpho_latest() -> Any:
        return start(sync_service.latest_report)

    @app.post("/renpho/history")
    def renpho_history() -> Any:
        return start(sync_service.renpho_history)

    @app.post("/weekly-report/generate")
    def weekly_report_generate() -> Any:
        map_tiles_enabled = request.form.get("map_tiles") == "yes"
        include_routes = request.form.get("include_routes") == "yes" or map_tiles_enabled
        return start(
            lambda: sync_service.build_weekly_report(
                include_routes=include_routes,
                map_tiles_enabled=map_tiles_enabled,
            )
        )

    @app.get("/weekly-report/<report_id>")
    def weekly_report_view(report_id: str) -> str:
        result = weekly_reports.get(report_id)
        if result is None:
            abort(404)
        return page(render_weekly_html(result.report, token, report_id))

    @app.get("/weekly-report/<report_id>/data")
    def weekly_report_data(report_id: str) -> Response:
        result = weekly_reports.get(report_id)
        if result is None:
            abort(404)
        return jsonify(chart_payload(result.report))

    @app.get("/assets/weekly-charts.js")
    def weekly_charts_asset() -> Response:
        return Response(CHART_JAVASCRIPT, mimetype="application/javascript")

    @app.get("/assets/body-silhouette.svg")
    def body_silhouette_asset() -> Response:
        content = files("garmin_sync").joinpath("assets/human-silhouette-cc0.svg").read_bytes()
        return Response(content, mimetype="image/svg+xml")

    @app.get("/jobs/<job_id>/progress")
    def weekly_report_progress(job_id: str) -> Response:
        if job_id not in jobs.jobs:
            abort(404)
        return jsonify(sync_service.get_report_progress(job_id))

    @app.post("/weekly-report/<report_id>/download")
    def weekly_report_download(report_id: str) -> Response:
        result = weekly_reports.get(report_id)
        if result is None:
            abort(404)
        report = result.report
        filename = f"weekly-health-report-{report.start_date}-to-{report.end_date}.pdf"
        response = Response(result.pdf, mimetype="application/pdf")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    def report_response(disposition: str) -> Response:
        if not latest_renpho:
            abort(404)
        latest = latest_renpho[0]
        measurement = latest.measurement.body
        filename = f"renpho-body-composition-{measurement.measured_at.date()}.pdf"
        response = Response(latest.document.content, mimetype="application/pdf")
        response.headers["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response

    @app.post("/renpho/report/view")
    def renpho_report_view() -> Response:
        return report_response("inline")

    @app.post("/renpho/report/download")
    def renpho_report_download() -> Response:
        return report_response("attachment")

    @app.post("/renpho/sync/<preview_id>")
    def renpho_sync(preview_id: str) -> Any:
        preview = previews.get(preview_id)
        if preview is None:
            abort(404)
        response = start(lambda: sync_service.sync_renpho(preview))
        if not isinstance(response, Response) or response.status_code != 409:
            previews.pop(preview_id, None)
        return response

    @app.get("/jobs/<job_id>")
    def job_status(job_id: str) -> str | Response:
        job = jobs.jobs.get(job_id)
        if job is None:
            abort(404)
        try:
            # Most reads finish in a few seconds. Waiting here avoids making
            # correctness depend on a browser honoring HTML meta refresh.
            result = job.future.result(timeout=1)
        except FutureTimeoutError:
            progress = sync_service.get_report_progress(job_id)
            stage = _escape(str(progress.get("stage", "Working")))
            completed_value = progress.get("completed", 0)
            total_value = progress.get("total", 5)
            completed = completed_value if isinstance(completed_value, int) else 0
            total = max(1, total_value if isinstance(total_value, int) else 5)
            percent = min(100, max(0, round(completed / total * 100)))
            response = Response(
                page(
                    f"<section><h2>Working…</h2><p>Current group: <strong>{stage}</strong></p>"
                    f"<progress value='{completed}' max='{total}' aria-label='Report progress'>"
                    f"{percent}%</progress><p>{percent}% complete</p>"
                    "<p>Core health → Sleep and recovery → Lifestyle context → "
                    "Activity details → Extended Garmin data</p><p>Keep this page open.</p>"
                    f"<p><a href='{url_for('job_status', job_id=job_id)}'>Check status</a></p>"
                    "</section>",
                    refresh=True,
                )
            )
            response.headers["Refresh"] = "1"
            return response
        except Exception as exc:
            message = _safe_error(exc)
            events.append(f"Error: {message}")
            return page(
                f"<section class=error><h2>Error</h2><p>{_escape(message)}</p><a href='/'>Back</a></section>"
            )
        if isinstance(result, RenphoPreview):
            preview_id = uuid.uuid4().hex
            previews[preview_id] = result
            if not result.candidates:
                events.append("RENPHO: no new measurements")
                return page(
                    "<section><h2>No new RENPHO measurements</h2><a href='/'>Back</a></section>"
                )
            first, last = (
                result.candidates[0].body.measured_at,
                result.candidates[-1].body.measured_at,
            )
            return page(
                f"<section><h2>Confirm RENPHO sync</h2><p>Measurements: {result.count}<br>Range: {_escape(str(first))} – {_escape(str(last))}</p><form method=post action=/renpho/sync/{preview_id}><input type=hidden name=csrf value='{token}'><button>Sync to Garmin</button></form><a href='/'>Cancel</a></section>"
            )
        if isinstance(result, LatestRenphoReport):
            latest_renpho[:] = [result]
            latest_error.clear()
            events.append(f"RENPHO: loaded measurement for {result.measurement.body.measured_at.date()}")
            return page(
                f"<section><h2>Latest RENPHO measurement</h2>{_renpho_card(result, token)}<a href='/'>Home</a></section>"
            )
        if isinstance(result, RenphoHistory):
            rows = "".join(_renpho_history_row(item) for item in result.measurements)
            if not rows:
                rows = "<tr><td colspan=4>No scale records available</td></tr>"
            girth = "".join(_renpho_girth_card(item) for item in result.girth_measurements)
            if not girth:
                girth = "<p>No body-circumference records available.</p>"
            return page(
                "<section><h2>RENPHO body measurements</h2>"
                f"{girth}"
                "<h3>Scale history</h3><p>WHR is the waist-to-hip ratio stored with "
                "each scale measurement; it is distinct from the circumference history above.</p>"
                "<table><tr><th>Measured at</th><th>Weight</th><th>Body fat</th><th>WHR</th></tr>"
                f"{rows}</table><a href='/'>Home</a></section>"
            )
        if isinstance(result, WeeklyReportResult):
            report_id = secrets.token_urlsafe(24)
            weekly_reports.clear()
            weekly_reports[report_id] = result
            latest_weekly_id[:] = [report_id]
            unavailable_items = result.report.availability.unavailable
            optional = [x for x in unavailable_items if x in OPTIONAL_REPORT_SECTIONS]
            required = [x for x in unavailable_items if x not in OPTIONAL_REPORT_SECTIONS]
            events.append(
                f"Weekly report: {result.status.value} for {result.report.start_date} to {result.report.end_date}"
            )
            notes: list[str] = []
            if required:
                notes.append(
                    f"<p class=caution>Unavailable health sections: "
                    f"{_escape(', '.join(required))}</p>"
                )
            if optional:
                notes.append(
                    "<p>Optional Garmin sections not available for this account: "
                    f"{_escape(', '.join(optional))}. The report is complete.</p>"
                )
            note = "".join(notes)
            return page(
                f"<section><h2>Weekly report ready</h2>{note}"
                f"<p><a href='/weekly-report/{report_id}'>Open web report</a></p>"
                f"<form method=post action='/weekly-report/{report_id}/download'>"
                f"<input type=hidden name=csrf value='{_escape(token)}'>"
                "<button>Download PDF</button></form><a href='/'>Home</a></section>"
            )
        results = result if isinstance(result, list) else [result]
        for item in results:
            if isinstance(item, OperationResult):
                events.append(f"{item.status.value}: {item.message}")
        content = "".join(
            f"<li class='{item.status.value}'>{_escape(item.message)}</li>" for item in results
        )
        return page(
            f"<section><h2>Result</h2><ul>{content}</ul><a href='/'>Home</a></section>"
        )

    def auto_loaded(future: Future[Any]) -> None:
        try:
            result = future.result()
            if isinstance(result, LatestRenphoReport):
                latest_renpho[:] = [result]
                latest_error.clear()
        except Exception as exc:
            latest_error[:] = [_safe_error(exc)]
        finally:
            startup_ready.set()

    def startup_checks() -> LatestRenphoReport:
        garmin_status = sync_service.status()
        events.append(f"Garmin startup check: {garmin_status.status.value}")
        return sync_service.latest_report()

    auto_job = jobs.submit(startup_checks)
    if auto_job is not None:
        jobs.jobs[auto_job].future.add_done_callback(auto_loaded)
    else:
        startup_ready.set()

    return app


def _pressure_from_form(form: Any) -> BloodPressure:
    try:
        return BloodPressure(
            measured_at=parse_local_datetime(str(form.get("measured_at", ""))),
            systolic=int(form.get("systolic", "")),
            diastolic=int(form.get("diastolic", "")),
            pulse=int(form.get("pulse", "")),
            notes=str(form.get("notes", "")).strip(),
        )
    except (TypeError, ValueError) as exc:
        raise ValidationError("Enter valid values in every numeric field") from exc


def _pressure_hidden(measurement: BloodPressure, token: str) -> str:
    values = {
        "csrf": token,
        "measured_at": measurement.measured_at.isoformat(),
        "systolic": str(measurement.systolic),
        "diastolic": str(measurement.diastolic),
        "pulse": str(measurement.pulse),
        "notes": measurement.notes,
    }
    return "".join(
        f"<input type=hidden name='{_escape(k)}' value='{_escape(v)}'>" for k, v in values.items()
    )


def _escape(value: str) -> str:
    import html

    return html.escape(value, quote=True)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, (ValidationError, RuntimeError)):
        return str(exc)
    return "Internal error; no data was changed"


def _renpho_card(latest: LatestRenphoReport, token: str) -> str:
    values = "".join(
        f"<tr><th>{_escape(label)}</th><td>{_escape(value)}</td></tr>"
        for label, value in latest.measurement.body.summary()
    )
    return (
        f"<p><strong>Report source:</strong> {_escape(latest.document.source)}</p>"
        f"<table>{values}</table>"
        f"<form method=post action=/renpho/report/view target=_blank>"
        f"<input type=hidden name=csrf value='{_escape(token)}'>"
        "<button>View report</button></form>"
        f"<form method=post action=/renpho/report/download>"
        f"<input type=hidden name=csrf value='{_escape(token)}'>"
        "<button>Download PDF</button></form>"
    )


def _renpho_history_row(item: RenphoMeasurement) -> str:
    report = item.report
    body_fat = report.body_fat_percentage.value if report is not None else None
    whr = report.whr if report is not None else None
    return (
        "<tr>"
        f"<td>{_escape(item.body.measured_at.strftime('%Y-%m-%d %H:%M'))}</td>"
        f"<td>{item.body.weight:.1f} kg</td>"
        f"<td>{f'{body_fat:.1f}%' if body_fat is not None else 'Not available'}</td>"
        f"<td>{f'{whr:.2f}' if whr is not None else 'Not available'}</td>"
        "</tr>"
    )


def _renpho_girth_card(item: Any) -> str:
    rows = "".join(
        "<tr>"
        f"<th>{_escape(value.label)}</th>"
        f"<td>{value.value:.2f} {_escape(value.unit) if value.unit != 'ratio' else ''}</td>"
        "</tr>"
        for value in item.values
    )
    return (
        "<article class=body-measurement-card>"
        f"<h4>{_escape(item.measured_at.strftime('%Y-%m-%d %H:%M'))}</h4>"
        "<div class=body-measurement-layout>"
        f"{_body_measurement_visual(item)}<table>{rows}</table></div></article>"
    )


BODY_CALLOUTS = {
    "Neck": ("right", 96, 219, 90),
    "Shoulders": ("left", 132, 154, 132),
    "Chest": ("right", 190, 239, 185),
    "Waist": ("left", 242, 173, 245),
    "Abdomen": ("right", 282, 232, 285),
    "Hips": ("left", 326, 161, 330),
    # Anatomical left/right: a front-facing person's left appears on the
    # viewer's right, and vice versa.
    "Left arm": ("right", 152, 257, 172),
    "Right arm": ("left", 205, 143, 214),
    "Left thigh": ("right", 363, 226, 365),
    "Right thigh": ("left", 405, 174, 405),
    "Left calf": ("right", 468, 221, 468),
    "Right calf": ("left", 510, 179, 510),
    "Waist-to-hip ratio": ("right", 326, 238, 330),
}

def _body_measurement_visual(item: Any) -> str:
    callouts: list[str] = []
    for value in item.values:
        position = BODY_CALLOUTS.get(value.label)
        if position is None:
            continue
        side, label_y, anchor_x, anchor_y = position
        label_x = 8 if side == "left" else 286
        line_end = 116 if side == "left" else 284
        badge_x = 3 if side == "left" else 281
        badge_width = 112 if side == "left" else 116
        display = f"{value.value:.2f} {value.unit if value.unit != 'ratio' else ''}".strip()
        callouts.append(
            f"<rect x='{badge_x}' y='{label_y - 19}' width='{badge_width}' height='36' "
            "rx='7' fill='#ffffff' stroke='#dbe4e0' stroke-width='1' opacity='.96'/>"
            + f"<path class=measure-line d='M {line_end} {label_y} L {anchor_x} {anchor_y}' "
            "stroke='#4776e6' stroke-width='2.5' fill='none' marker-end='url(#arrowhead)'/>"
            f"<text class=measure-label x='{label_x}' y='{label_y - 3}' fill='#17202a' "
            f"font-family='system-ui,sans-serif' font-size='12' font-weight='700'>{_escape(value.label)}</text>"
            f"<text class=measure-value x='{label_x}' y='{label_y + 12}' fill='#52606d' "
            f"font-family='system-ui,sans-serif' font-size='11'>{_escape(display)}</text>"
        )
    return (
        "<div class=body-map><svg viewBox='0 0 400 590' role=img "
        "aria-label='Body diagram showing measured locations'>"
        "<defs><marker id='arrowhead' markerWidth='8' markerHeight='8' refX='7' refY='4' "
        "orient='auto' markerUnits='strokeWidth'><path d='M0,0 L8,4 L0,8 Z' fill='#4776e6'/></marker></defs>"
        "<image href='/assets/body-silhouette.svg' x='72' y='8' width='256' height='550' "
        "preserveAspectRatio='xMidYMid meet'/>"
        + "".join(callouts)
        + "</svg><small>CC0 silhouette: Wikimedia Commons</small></div>"
    )


def run_gui(*, open_browser: bool = True, startup_timeout: float = 30.0) -> None:
    app = create_app()
    bind = os.environ.get("GARMIN_SYNC_BIND", "127.0.0.1")
    port = int(os.environ.get("GARMIN_SYNC_PORT", "0"))
    server = LoopbackWSGIServer(bind, port, app)
    browser_host = os.environ.get("GARMIN_SYNC_PUBLIC_HOST", "127.0.0.1")
    url = f"http://{browser_host}:{server.server_port}/"
    print(f"Garmin Health Sync GUI: {url}", flush=True)
    print("Checking Garmin session and loading the latest RENPHO measurement…", flush=True)
    ready = app.extensions["garmin_sync_startup_ready"]
    checks_finished = ready.wait(timeout=startup_timeout)
    if checks_finished:
        print("Startup checks finished.", flush=True)
    else:
        print("Startup checks are still running; the GUI will show progress.", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    if open_browser and os.environ.get("GARMIN_SYNC_NO_BROWSER") != "1":
        threading.Timer(0.1, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
