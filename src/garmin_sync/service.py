from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from .body_report import ReportDocument, ReportProvider
from .garmin import (
    AuthenticationRequired,
    GarminClient,
    GarminSyncError,
    RateLimited,
    UploadUncertain,
)
from .models import BERLIN, BloodPressure
from .renpho import RenphoCloud, RenphoError, RenphoGirthMeasurement, RenphoMeasurement
from .state import SyncState
from .weekly_pdf import render_weekly_report_pdf
from .weekly_report import WeeklyHealthReport, build_report

OPTIONAL_REPORT_SECTIONS = frozenset(
    {
        "adhoc_challenges",
        "badge_challenges",
        "badges",
        "endurance_score",
        "golf",
        "hill_score",
        "last_used_device",
        "personal_records",
        "race_predictions",
        "running_tolerance",
        "training_plans",
        "virtual_challenges",
    }
)


class ResultStatus(StrEnum):
    SUCCESS = "success"
    CONFLICT = "conflict"
    ALREADY_EXISTS = "already_exists"
    UNCERTAIN = "uncertain"
    ERROR = "error"
    PARTIAL = "partial"
    AUTH_REQUIRED = "auth_required"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True, slots=True)
class OperationResult:
    status: ResultStatus
    message: str


@dataclass(frozen=True, slots=True)
class RenphoPreview:
    mode: str
    candidates: tuple[RenphoMeasurement, ...]
    skipped: int

    @property
    def count(self) -> int:
        return len(self.candidates)


@dataclass(frozen=True, slots=True)
class LatestRenphoReport:
    measurement: RenphoMeasurement
    document: ReportDocument


@dataclass(frozen=True, slots=True)
class RenphoHistory:
    measurements: tuple[RenphoMeasurement, ...]
    girth_measurements: tuple[RenphoGirthMeasurement, ...]


@dataclass(frozen=True, slots=True)
class WeeklyReportResult:
    status: ResultStatus
    report: WeeklyHealthReport
    pdf: bytes


class HealthSyncService:
    """UI-independent application operations shared by CLI and web GUI."""

    def __init__(
        self,
        garmin: GarminClient,
        renpho: RenphoCloud,
        state: SyncState,
        reports: ReportProvider | None = None,
    ) -> None:
        self.garmin = garmin
        self.renpho = renpho
        self.state = state
        self.reports = reports or ReportProvider()
        self._report_progress: dict[str, object] = {"stage": "Idle", "completed": 0, "total": 5}

    def status(self) -> OperationResult:
        try:
            name = self.garmin.connect()
            return OperationResult(ResultStatus.SUCCESS, f"Connected: {name}")
        except GarminSyncError as exc:
            return OperationResult(ResultStatus.ERROR, str(exc))

    def add_pressure(self, measurement: BloodPressure) -> OperationResult:
        try:
            self.garmin.connect()
            if self.garmin.has_blood_pressure(measurement):
                return OperationResult(
                    ResultStatus.ALREADY_EXISTS, "This entry already exists in Garmin"
                )
            self.garmin.add_blood_pressure(measurement)
            return OperationResult(ResultStatus.SUCCESS, "Blood pressure uploaded and verified")
        except UploadUncertain as exc:
            return OperationResult(ResultStatus.UNCERTAIN, str(exc))
        except GarminSyncError as exc:
            return OperationResult(ResultStatus.ERROR, str(exc))

    def preview_renpho(self, mode: str) -> RenphoPreview:
        measurements, skipped = self.renpho.fetch()
        synced = self.state.synced_ids()
        if mode == "latest":
            candidates = measurements[:1]
        elif mode == "all":
            candidates = _latest_per_day(measurements)
        else:
            raise RenphoError("Unknown RENPHO sync mode")
        return RenphoPreview(
            mode, tuple(item for item in candidates if item.source_id not in synced), skipped
        )

    def latest_renpho(self) -> RenphoMeasurement:
        measurements, _skipped = self.renpho.fetch()
        if not measurements:
            raise RenphoError("RENPHO returned no measurements")
        return measurements[0]

    def latest_report(self) -> LatestRenphoReport:
        measurement = self.latest_renpho()
        if measurement.report is None:
            raise RenphoError("The latest RENPHO measurement has no report data")
        return LatestRenphoReport(measurement, self.reports.resolve(measurement.report))

    def renpho_history(self) -> RenphoHistory:
        measurements, _skipped = self.renpho.fetch()
        return RenphoHistory(tuple(measurements), tuple(self.renpho.fetch_girth()))

    def build_weekly_report(
        self,
        end_date: date | None = None,
        *,
        include_routes: bool = False,
        map_tiles_enabled: bool = False,
    ) -> WeeklyReportResult:
        return self.build_comprehensive_report(
            end_date=end_date,
            include_routes=include_routes,
            map_tiles_enabled=map_tiles_enabled,
        )

    def get_report_progress(self, job_id: str | None = None) -> dict[str, object]:
        return dict(self._report_progress)

    def build_comprehensive_report(
        self,
        period: int = 7,
        lifestyle_context: int = 30,
        end_date: date | None = None,
        include_routes: bool = False,
        map_tiles_enabled: bool = False,
    ) -> WeeklyReportResult:
        end = end_date or datetime.now(BERLIN).date()
        start = end - timedelta(days=period - 1)
        context_start = end - timedelta(days=lifestyle_context - 1)
        self._report_progress = {"stage": "Core health", "completed": 0, "total": 5}
        raw: dict[str, object] = {}
        available: list[str] = []
        unavailable: list[str] = []
        terminal: ResultStatus | None = None

        try:
            self.garmin.connect()
        except AuthenticationRequired:
            terminal = ResultStatus.AUTH_REQUIRED
            unavailable.append("Garmin session")
        except RateLimited:
            terminal = ResultStatus.RATE_LIMITED
            unavailable.append("Garmin rate limited")
        except GarminSyncError:
            terminal = ResultStatus.ERROR
            unavailable.append("Garmin connection")

        def collect(name: str, operation: Callable[[], object]) -> None:
            nonlocal terminal
            if terminal is not None:
                return
            try:
                raw[name] = operation()
                available.append(name)
            except AuthenticationRequired:
                terminal = ResultStatus.AUTH_REQUIRED
                unavailable.append(name)
            except RateLimited:
                terminal = ResultStatus.RATE_LIMITED
                unavailable.append(name)
            except GarminSyncError:
                unavailable.append(name)

        start_text, end_text = start.isoformat(), end.isoformat()
        collect("activities", lambda: self.garmin.read_activities(start_text, end_text))
        collect("pressure", lambda: self.garmin.read_blood_pressure(start_text, end_text))
        collect("body", lambda: self.garmin.read_body_composition(start_text, end_text))
        collect("training_status", lambda: self.garmin.read_training_status(end_text))
        collect(
            "body_battery",
            lambda: _battery_by_date(
                self.garmin.read_body_battery(context_start.isoformat(), end_text)
            ),
        )

        stats: dict[str, object] = {}
        sleep: dict[str, object] = {}
        readiness: dict[str, object] = {}
        stress: dict[str, object] = {}
        hrv: dict[str, object] = {}
        lifestyle: dict[str, object] = {}
        spo2: dict[str, object] = {}
        respiration: dict[str, object] = {}
        hydration: dict[str, object] = {}
        nutrition: dict[str, object] = {}
        events: dict[str, object] = {}
        self._report_progress = {"stage": "Sleep and recovery", "completed": 1, "total": 5}
        day = context_start
        while day <= end and terminal is None:
            key = day.isoformat()
            try:
                _collect_daily(self.garmin.read_daily_stats, key, stats, unavailable, "stats")
                _collect_daily(self.garmin.read_sleep, key, sleep, unavailable, "sleep")
                _collect_daily(self.garmin.read_stress, key, stress, unavailable, "stress")
                _collect_daily(self.garmin.read_hrv, key, hrv, unavailable, "hrv")
                _collect_daily(self.garmin.read_lifestyle, key, lifestyle, unavailable, "lifestyle")
                if day >= start:
                    _collect_daily(
                        self.garmin.read_training_readiness,
                        key,
                        readiness,
                        unavailable,
                        "readiness",
                        first=True,
                    )
                    _collect_daily(self.garmin.read_spo2, key, spo2, unavailable, "spo2")
                    _collect_daily(
                        self.garmin.read_respiration,
                        key,
                        respiration,
                        unavailable,
                        "respiration",
                    )
                    _collect_daily(
                        self.garmin.read_hydration,
                        key,
                        hydration,
                        unavailable,
                        "hydration",
                    )
                    _collect_daily(
                        self.garmin.read_nutrition,
                        key,
                        nutrition,
                        unavailable,
                        "nutrition",
                    )
                    _collect_daily(
                        self.garmin.read_daily_events,
                        key,
                        events,
                        unavailable,
                        "daily_events",
                    )
            except AuthenticationRequired:
                terminal = ResultStatus.AUTH_REQUIRED
            except RateLimited:
                terminal = ResultStatus.RATE_LIMITED
            day += timedelta(days=1)
        self._report_progress = {"stage": "Lifestyle context", "completed": 2, "total": 5}
        for name, values in (
            ("stats", stats), ("sleep", sleep), ("readiness", readiness),
            ("stress", stress), ("hrv", hrv), ("lifestyle", lifestyle),
            ("spo2", spo2), ("respiration", respiration), ("hydration", hydration),
            ("nutrition", nutrition), ("daily_events", events),
        ):
            if values:
                raw[name] = values
                available.append(name)

        self._report_progress = {"stage": "Activity details", "completed": 3, "total": 5}
        activity_details: dict[str, object] = {}
        activities_value = raw.get("activities", [])
        activity_items = activities_value if isinstance(activities_value, list) else []
        if len(activity_items) > 200:
            raw["truncated"] = ["activity_details"]
        for item in activity_items[:200]:
            if not isinstance(item, dict) or item.get("activityId") is None:
                continue
            activity_id = str(item["activityId"])
            try:
                activity_details[activity_id] = self.garmin.read_activity_detail(activity_id)
            except AuthenticationRequired:
                terminal = ResultStatus.AUTH_REQUIRED
                break
            except RateLimited:
                terminal = ResultStatus.RATE_LIMITED
                break
            except (GarminSyncError, AttributeError):
                unavailable.append(f"activity_detail:{activity_id}")
        if activity_details:
            raw["activity_details"] = activity_details
            raw["include_routes"] = include_routes
            raw["map_tiles_enabled"] = map_tiles_enabled and include_routes
            available.append("activity_details")

        self._report_progress = {"stage": "Extended Garmin data", "completed": 4, "total": 5}
        if terminal is None:
            try:
                extended, extended_unavailable = self.garmin.read_extended(start_text, end_text)
                raw["extended"] = extended
                available.append("extended")
                unavailable.extend(extended_unavailable)
            except AuthenticationRequired:
                terminal = ResultStatus.AUTH_REQUIRED
            except RateLimited:
                terminal = ResultStatus.RATE_LIMITED
            except (GarminSyncError, AttributeError):
                unavailable.append("extended")

        renpho_measurements: list[RenphoMeasurement] = []
        try:
            renpho_measurements, _ = self.renpho.fetch()
            available.append("renpho")
        except RenphoError:
            unavailable.append("renpho")

        report = build_report(
            start_date=start,
            end_date=end,
            garmin=raw,
            renpho=renpho_measurements,
            available=available,
            unavailable=unavailable,
        )
        required_unavailable = [
            section for section in unavailable if section not in OPTIONAL_REPORT_SECTIONS
        ]
        status = terminal or (
            ResultStatus.PARTIAL if required_unavailable else ResultStatus.SUCCESS
        )
        result = WeeklyReportResult(status, report, self.render_weekly_report_pdf(report))
        self._report_progress = {"stage": "Complete", "completed": 5, "total": 5}
        return result

    @staticmethod
    def render_weekly_report_pdf(report: WeeklyHealthReport) -> bytes:
        return render_weekly_report_pdf(report)

    def sync_renpho(self, preview: RenphoPreview) -> list[OperationResult]:
        results: list[OperationResult] = []
        try:
            self.garmin.connect()
            for item in preview.candidates:
                if self.garmin.has_body_composition(item.body):
                    self.state.mark_synced(item.source_id)
                    results.append(
                        OperationResult(
                            ResultStatus.ALREADY_EXISTS,
                            f"{item.body.measured_at.date()}: already uploaded",
                        )
                    )
                    continue
                if self.garmin.has_body_composition_on_date(item.body):
                    results.append(
                        OperationResult(
                            ResultStatus.CONFLICT,
                            f"{item.body.measured_at.date()}: Garmin contains a different entry",
                        )
                    )
                    continue
                try:
                    self.garmin.add_body_composition(item.body)
                except UploadUncertain as exc:
                    results.append(OperationResult(ResultStatus.UNCERTAIN, str(exc)))
                    break
                self.state.mark_synced(item.source_id)
                results.append(
                    OperationResult(
                        ResultStatus.SUCCESS, f"{item.body.measured_at.date()}: uploaded"
                    )
                )
        except GarminSyncError as exc:
            results.append(OperationResult(ResultStatus.ERROR, str(exc)))
        return results


def _latest_per_day(measurements: list[RenphoMeasurement]) -> list[RenphoMeasurement]:
    latest: dict[object, RenphoMeasurement] = {}
    for item in measurements:
        latest.setdefault(item.body.measured_at.date(), item)
    return sorted(latest.values(), key=lambda item: item.body.measured_at)


def _collect_daily(
    operation: Callable[[str], object],
    key: str,
    target: dict[str, object],
    unavailable: list[str],
    section: str,
    *,
    first: bool = False,
) -> None:
    try:
        value = operation(key)
        if first and isinstance(value, list):
            value = value[0] if value else {}
        target[key] = value
    except (AuthenticationRequired, RateLimited):
        raise
    except (GarminSyncError, AttributeError):
        unavailable.append(f"{section}:{key}")


def _battery_by_date(items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(item.get("date")): item for item in items if item.get("date")}
