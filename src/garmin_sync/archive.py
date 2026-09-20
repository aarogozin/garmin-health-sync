# ruff: noqa: E501
"""Private, human-readable Markdown archive for normalized health snapshots.

This module deliberately accepts only ``WeeklyHealthReport``.  It never sees
provider responses, credentials, routes, PDFs, or profile URLs.
"""

from __future__ import annotations

import contextlib
import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .ai_context import ContextPeriod
from .models import BERLIN
from .weekly_report import (
    ActivitySummary,
    BodyMeasurementPoint,
    DailyHealthMetrics,
    DailyRecovery,
    HydrationNutrition,
    LifestyleEvent,
    PressureReading,
    SleepMetrics,
    WeeklyHealthReport,
)

SCHEMA = "garmin-health-sync/health-note@1"
PROFILE_ID = "default"


class ArchiveError(RuntimeError):
    """The local archive could not be safely read or written."""


@dataclass(frozen=True, slots=True)
class ArchiveStatus:
    root: Path
    exists: bool
    daily_documents: int
    weekly_documents: int
    last_updated: str | None


def default_archive_root() -> Path:
    """Return a visible host path, or a container-friendly configurable path."""
    configured = os.environ.get("GARMIN_SYNC_ARCHIVE_DIR")
    if configured:
        return Path(configured).expanduser()
    if data_dir := os.environ.get("GARMIN_SYNC_DATA_DIR"):
        return Path(data_dir) / "archive"
    return Path.home() / "Documents" / "Garmin Health Sync"


class LocalHealthArchive:
    """Safely materialize report snapshots as a single-user Markdown workspace."""

    def __init__(self, root: Path | None = None, profile_id: str = PROFILE_ID) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", profile_id):
            raise ArchiveError("Invalid archive profile id")
        self.root = (root or default_archive_root()).expanduser()
        self.profile_id = profile_id

    @property
    def profile_root(self) -> Path:
        return self.root / "users" / self.profile_id

    def setup(self) -> ArchiveStatus:
        """Prepare private directories and refresh the archive's generated guidance."""
        try:
            self._mkdir(self.root)
            self._mkdir(self.root / "users")
            self._mkdir(self.profile_root)
            self._mkdir(self.profile_root / "daily")
            self._mkdir(self.profile_root / "weekly")
            self._mkdir(self.profile_root / "context")
            self._write(self.root / ".gitignore", "*\n!.gitignore\n")
            self._write(self.root / "README.md", _archive_readme())
        except OSError as exc:
            raise ArchiveError("Could not create the local Markdown archive") from exc
        return self.status()

    def write_context(self, period: ContextPeriod, json_content: str, markdown: str) -> None:
        """Atomically publish deterministic AI context files with private permissions."""
        self.setup()
        stem = {"current": "CURRENT", "7d": "LAST_7_DAYS", "30d": "LAST_30_DAYS"}[period]
        context_root = self.profile_root / "context"
        self._write(context_root / f"{stem}.json", json_content)
        self._write(context_root / f"{stem}.md", markdown)

    def status(self) -> ArchiveStatus:
        """Count materialized notes and inspect modification times without reading health data."""
        daily = tuple((self.profile_root / "daily").glob("**/*.md"))
        weekly = tuple((self.profile_root / "weekly").glob("**/*.md"))
        documents = (*daily, *weekly)
        last_updated = None
        if documents:
            newest = max(documents, key=lambda item: item.stat().st_mtime)
            last_updated = datetime.fromtimestamp(newest.stat().st_mtime, BERLIN).isoformat(
                timespec="seconds"
            )
        return ArchiveStatus(
            self.root,
            self.profile_root.exists(),
            len(daily),
            len(weekly),
            last_updated,
        )

    def write_report(
        self,
        report: WeeklyHealthReport,
        *,
        include_weekly: bool | None = None,
        preserve_existing: bool = False,
    ) -> ArchiveStatus:
        """Atomically replace deterministic day/week files from a completed snapshot."""
        self.setup()
        days = _days(report)
        for day in days:
            self._write(
                self._daily_path(day),
                render_daily_markdown(report, day),
                overwrite=not preserve_existing,
            )
        weekly = include_weekly if include_weekly is not None else len(days) == 7
        if weekly:
            self._write(
                self._weekly_path(report.end_date),
                render_weekly_markdown(report),
                overwrite=not preserve_existing,
            )
        self._write(
            self.profile_root / "PROFILE.md",
            render_profile_markdown(report),
            overwrite=not preserve_existing,
        )
        self._write(self.profile_root / "INDEX.md", render_index_markdown(self.status(), report))
        return self.status()

    def _daily_path(self, day: date) -> Path:
        return self.profile_root / "daily" / f"{day:%Y}" / f"{day:%m}" / f"{day.isoformat()}.md"

    def _weekly_path(self, day: date) -> Path:
        year, week, _weekday = day.isocalendar()
        return self.profile_root / "weekly" / f"{year}" / f"{year}-W{week:02}.md"

    @staticmethod
    def _mkdir(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        with contextlib.suppress(OSError):
            os.chmod(path, 0o700)

    def _write(self, path: Path, content: str, *, overwrite: bool = True) -> None:
        self._mkdir(path.parent)
        fd, temporary = tempfile.mkstemp(prefix=".health-note-", suffix=".tmp", dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
            if overwrite:
                os.replace(temporary, path)
            else:
                # A hard link publishes the completed note only if its name is
                # still unused, including when another collector writes concurrently.
                with contextlib.suppress(FileExistsError):
                    os.link(temporary, path)
                os.unlink(temporary)
            with contextlib.suppress(OSError):
                os.chmod(path, 0o600)
        except OSError as exc:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
            raise ArchiveError("Could not write a local health note") from exc


def render_daily_markdown(report: WeeklyHealthReport, day: date) -> str:
    """Select one Berlin calendar day and render only normalized, privacy-safe fields."""
    recovery = _by_day(report.recovery, day)
    health = _by_day(report.comprehensive.daily_health, day)
    sleep = _by_day(report.comprehensive.sleep, day)
    nutrition = _by_day(report.comprehensive.hydration_nutrition, day)
    activities = [
        item for item in report.activities if item.measured_at.astimezone(BERLIN).date() == day
    ]
    body = [item for item in report.body if item.measured_at.astimezone(BERLIN).date() == day]
    pressure = [
        item
        for item in report.pressure.readings
        if item.measured_at.astimezone(BERLIN).date() == day
    ]
    lifestyle = [item for item in report.comprehensive.lifestyle if item.day == day]
    return (
        _front_matter(report, day, day, "daily")
        + "\n"
        + "\n".join(
            [
                f"# Health note — {day.isoformat()}",
                "",
                "> Personal monitoring context, not a medical record or diagnosis.",
                _daily_overview(recovery, health, sleep),
                _activities(activities),
                _body(body),
                _pressure(pressure),
                _sleep_recovery(recovery, health, sleep, nutrition),
                _lifestyle(lifestyle),
                _insights(report),
            ]
        ).strip()
        + "\n"
    )


def render_weekly_markdown(report: WeeklyHealthReport) -> str:
    """Render the report window as Markdown without provider identifiers or route data."""
    return (
        _front_matter(report, report.start_date, report.end_date, "weekly")
        + "\n"
        + "\n".join(
            [
                f"# Weekly health summary — {report.start_date.isoformat()} to {report.end_date.isoformat()}",
                "",
                "> Personal monitoring context, not medical advice or a diagnosis.",
                f"- Training: **{report.total_training_minutes:.0f} min** across **{len(report.activities)}** activities.",
                f"- Blood-pressure coverage: **{report.pressure.days_covered} day(s)**.",
                f"- Body-composition points: **{len(report.body)}**.",
                _activities(list(report.activities)),
                _body(list(report.body)),
                _pressure(list(report.pressure.readings)),
                _weekly_recovery(report),
                _insights(report),
            ]
        ).strip()
        + "\n"
    )


def render_profile_markdown(report: WeeklyHealthReport) -> str:
    """Summarize the supplied snapshot and explain safe interpretation of the archive."""
    latest_body = max(report.body, key=lambda value: value.measured_at, default=None)
    latest_recovery = max(report.recovery, key=lambda value: value.day, default=None)
    return "\n".join(
        [
            "---",
            f"schema: {SCHEMA}",
            f"profile: {PROFILE_ID}",
            f"updated_at: {report.generated_at.astimezone(BERLIN).isoformat(timespec='seconds')}",
            "timezone: Europe/Berlin",
            "---",
            "",
            "# Health Sync — AI context",
            "",
            "This is a local, normalized personal health summary. Treat trends as context for discussion, not medical conclusions.",
            "",
            "## Current snapshot",
            f"- Latest body measurement: {_body_line(latest_body) if latest_body else 'Not available'}",
            f"- Latest recovery day: {_recovery_line(latest_recovery) if latest_recovery else 'Not available'}",
            f"- Recent report window: {report.start_date.isoformat()} to {report.end_date.isoformat()}",
            f"- Data availability: {_availability(report)}",
            "",
            "## How to use this archive",
            "- Start with this file, then read the relevant daily and weekly notes for evidence and data coverage.",
            "- Missing values mean the source did not provide a usable value; do not estimate them.",
            "- BIA body composition is best interpreted as a trend and is affected by hydration, timing, meals, and recent activity.",
            "- Do not use this archive for emergency or diagnostic decisions.",
            "",
            "## Privacy",
            "This archive intentionally excludes credentials, raw API payloads, GPS/location data, profile URLs, and PDFs. It is ignored by Git by default.",
            "",
        ]
    )


def render_index_markdown(status: ArchiveStatus, report: WeeklyHealthReport) -> str:
    """Describe archive coverage and the window of the most recently written report."""
    return "\n".join(
        [
            "# Local Health Archive",
            "",
            f"- Profile: `{PROFILE_ID}`",
            f"- Daily notes: {status.daily_documents}",
            f"- Weekly notes: {status.weekly_documents}",
            f"- Last archive update: {status.last_updated or 'Not available'}",
            f"- Latest report window: {report.start_date.isoformat()} to {report.end_date.isoformat()}",
            "",
            "Open `PROFILE.md` first. Daily documents are organized by calendar date; weekly documents use ISO weeks.",
            "",
        ]
    )


def _front_matter(report: WeeklyHealthReport, start: date, end: date, document_type: str) -> str:
    return "\n".join(
        [
            "---",
            f"schema: {SCHEMA}",
            f"profile: {PROFILE_ID}",
            f"document_type: {document_type}",
            f"period_start: {start.isoformat()}",
            f"period_end: {end.isoformat()}",
            f"generated_at: {report.generated_at.astimezone(BERLIN).isoformat(timespec='seconds')}",
            "timezone: Europe/Berlin",
            f"available_sources: {_yaml_list(report.availability.available)}",
            f"unavailable_sections: {_yaml_list(report.availability.unavailable)}",
            f"completeness: {'partial' if report.availability.unavailable else 'complete'}",
            "---",
        ]
    )


def _daily_overview(
    recovery: DailyRecovery | None, health: DailyHealthMetrics | None, sleep: SleepMetrics | None
) -> str:
    values = [
        ("Steps", _value(recovery.steps if recovery else None)),
        ("Sleep", _value(recovery.sleep_hours if recovery else None, " h")),
        ("Sleep score", _value(recovery.sleep_score if recovery else None)),
        ("Stress", _value(recovery.stress if recovery else None)),
        ("Resting HR", _value(recovery.resting_hr if recovery else None, " bpm")),
        ("Overnight HRV", _value(sleep.overnight_hrv if sleep else None, " ms")),
        ("Distance", _value(health.distance_km if health else None, " km")),
    ]
    return "## Overview\n\n" + _table(["Metric", "Value"], values)


def _activities(items: list[ActivitySummary]) -> str:
    rows = [
        (
            _text(item.activity_type),
            f"{item.duration_minutes:.0f} min",
            _value(item.distance_km, " km"),
            _value(item.calories, " kcal"),
            _value(item.average_hr, " bpm"),
            _value(item.training_load),
        )
        for item in items
    ]
    return "## Activities\n\n" + _table(
        ["Type", "Duration", "Distance", "Calories", "Average HR", "Training load"],
        rows,
        empty="No activity summaries available.",
    )


def _body(items: list[BodyMeasurementPoint]) -> str:
    rows = [
        (
            item.measured_at.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M"),
            f"{item.weight_kg:.1f} kg",
            _value(item.body_fat_pct, " %"),
            _value(item.muscle_mass_kg, " kg"),
            _text(item.source),
        )
        for item in items
    ]
    details = [_renpho_detail(item) for item in items if item.report is not None]
    detail_text = "\n\n".join(detail for detail in details if detail)
    summary = "## Weight and body composition\n\n" + _table(
        ["Measured", "Weight", "Body fat", "Muscle mass", "Source"],
        rows,
        empty="No body-composition measurements available.",
    )
    return summary + ("\n\n" + detail_text if detail_text else "")


def _renpho_detail(item: BodyMeasurementPoint) -> str:
    report = item.report
    if report is None:
        return ""
    values = [
        ("Body score", _value(report.body_score)),
        ("BMI", _value(report.bmi.value)),
        ("Bone mass", _value(report.bone_mass.value, " kg")),
        ("Protein mass", _value(report.protein_mass.value, " kg")),
        ("Water mass", _value(report.water_mass.value, " kg")),
        ("Skeletal muscle mass", _value(report.skeletal_muscle_mass.value, " kg")),
        ("Visceral fat", _value(report.visceral_fat)),
        ("BMR", _value(report.bmr, " kcal")),
        ("Fat-free mass", _value(report.fat_free_mass, " kg")),
        ("Subcutaneous fat", _value(report.subcutaneous_fat, " %")),
        ("SMI", _value(report.smi, " kg/m²")),
        ("Metabolic age", _value(report.metabolic_age, " years")),
        ("Waist-to-hip ratio", _value(report.whr)),
        ("Optimal weight", _value(report.optimal_weight, " kg")),
        (
            "Weight / fat / muscle control",
            _triple(report.weight_control, report.fat_control, report.muscle_control, " kg"),
        ),
    ]
    return "### RENPHO detailed composition\n\n" + _table(["Metric", "Value"], values)


def _pressure(items: list[PressureReading]) -> str:
    rows = []
    for item in items:
        rows.append(
            (
                item.measured_at.astimezone(BERLIN).strftime("%Y-%m-%d %H:%M"),
                f"{item.systolic}/{item.diastolic} mmHg",
                _value(item.pulse, " bpm"),
            )
        )
    return "## Blood pressure\n\n" + _table(
        ["Measured", "Blood pressure", "Pulse"],
        rows,
        empty="No blood-pressure readings available.",
    )


def _sleep_recovery(
    recovery: DailyRecovery | None,
    health: DailyHealthMetrics | None,
    sleep: SleepMetrics | None,
    nutrition: HydrationNutrition | None,
) -> str:
    values = [
        ("Steps", _value(recovery.steps if recovery else None)),
        (
            "Moderate / vigorous minutes",
            _pair(
                recovery.moderate_minutes if recovery else None,
                recovery.vigorous_minutes if recovery else None,
                " min",
            ),
        ),
        ("Stress", _value(recovery.stress if recovery else None)),
        (
            "Body Battery charged / drained",
            _pair(
                recovery.body_battery_charged if recovery else None,
                recovery.body_battery_drained if recovery else None,
            ),
        ),
        ("Readiness", _value(recovery.readiness_score if recovery else None)),
        (
            "Minimum / maximum HR",
            _pair(health.min_hr if health else None, health.max_hr if health else None, " bpm"),
        ),
        (
            "Sleep stages (deep / light / REM)",
            _triple(
                sleep.deep_hours if sleep else None,
                sleep.light_hours if sleep else None,
                sleep.rem_hours if sleep else None,
                " h",
            ),
        ),
        ("Overnight HRV", _value(sleep.overnight_hrv if sleep else None, " ms")),
        ("SpO₂", _value(sleep.spo2 if sleep else None, " %")),
        ("Respiration", _value(sleep.respiration if sleep else None, " breaths/min")),
        ("Hydration", _value(nutrition.hydration_ml if nutrition else None, " ml")),
        (
            "Nutrition calories",
            _value(nutrition.nutrition_calories if nutrition else None, " kcal"),
        ),
        (
            "Macros (protein / carbs / fat)",
            _triple(
                nutrition.protein_g if nutrition else None,
                nutrition.carbs_g if nutrition else None,
                nutrition.fat_g if nutrition else None,
                " g",
            ),
        ),
    ]
    return "## Recovery, activity, and nutrition\n\n" + _table(["Metric", "Value"], values)


def _weekly_recovery(report: WeeklyHealthReport) -> str:
    rows = []
    for item in report.recovery:
        rows.append(
            (
                item.day.isoformat(),
                _value(item.steps),
                _value(item.sleep_hours, " h"),
                _value(item.sleep_score),
                _value(item.stress),
                _value(item.resting_hr, " bpm"),
            )
        )
    return "## Recovery trend\n\n" + _table(
        ["Day", "Steps", "Sleep", "Sleep score", "Stress", "Resting HR"],
        rows,
        empty="No daily recovery metrics available.",
    )


def _lifestyle(items: list[LifestyleEvent]) -> str:
    rows = [(_text(item.category), _text(item.name), _value(item.value)) for item in items]
    return "## Lifestyle context\n\n" + _table(
        ["Category", "Event", "Value"],
        rows,
        empty="No lifestyle events recorded.",
    )


def _insights(report: WeeklyHealthReport) -> str:
    if not report.insights:
        return "## Observations and limitations\n\nNo rule-based observations available for this snapshot."
    lines = ["## Observations and limitations", ""]
    for item in report.insights:
        lines.append(f"- **{_text(item.category)} — {_text(item.confidence)}:** {_text(item.text)}")
    return "\n".join(lines)


def _days(report: WeeklyHealthReport) -> list[date]:
    result: list[date] = []
    current = report.start_date
    while current <= report.end_date:
        result.append(current)
        current = date.fromordinal(current.toordinal() + 1)
    return result


def _by_day[T](items: tuple[T, ...], day: date) -> T | None:
    return next((item for item in items if getattr(item, "day", None) == day), None)


def _table(
    headers: Sequence[str], rows: Sequence[tuple[object, ...]], *, empty: str = "Not available."
) -> str:
    if not rows:
        return empty
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    content = ["| " + " | ".join(_text(value) for value in row) + " |" for row in rows]
    return "\n".join([header, separator, *content])


def _value(value: object | None, suffix: str = "") -> str:
    if value is None:
        return "Not available"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def _pair(left: object | None, right: object | None, suffix: str = "") -> str:
    return f"{_value(left, suffix)} / {_value(right, suffix)}"


def _triple(
    first: object | None, second: object | None, third: object | None, suffix: str = ""
) -> str:
    return f"{_value(first, suffix)} / {_value(second, suffix)} / {_value(third, suffix)}"


def _text(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ").strip()


def _yaml_list(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(_yaml_scalar(value) for value in values) + "]"


def _yaml_scalar(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _body_line(item: BodyMeasurementPoint) -> str:
    return f"{item.weight_kg:.1f} kg ({item.source}, {item.measured_at.astimezone(BERLIN).strftime('%Y-%m-%d')})"


def _recovery_line(item: DailyRecovery) -> str:
    return f"{item.day.isoformat()} — {_value(item.sleep_hours, ' h')} sleep, {_value(item.stress)} stress"


def _availability(report: WeeklyHealthReport) -> str:
    if not report.availability.unavailable:
        return "Complete for the requested sections"
    return f"Partial; unavailable: {', '.join(report.availability.unavailable)}"


def _archive_readme() -> str:
    return """# Garmin Health Sync local archive

This folder contains intentionally persisted personal health summaries for local discussion with an AI assistant or clinician. It is ignored by Git by default.

Documents use `garmin-health-sync/health-note@1` YAML front matter and human-readable Markdown tables. `PROFILE.md` is the starting point; daily and weekly notes retain the supporting history.

The `users/default/context` directory contains deterministic `CURRENT`, `LAST_7_DAYS`, and `LAST_30_DAYS` JSON/Markdown pairs. JSON uses the strict `garmin-health-sync/ai-context@3` schema with a compact `summary` and detailed `raw_data`; Markdown is rendered from that same model. Exercise muscle targets are conservative local inferences and are labelled accordingly.

Only normalized summaries are stored. Credentials, API payloads, GPS/location data, profile URLs, and PDF bytes are deliberately excluded. Missing values mean no usable source value was available.

Partial collections create missing notes but never replace existing notes or `PROFILE.md`, including previously partial notes. Unsupported metrics can keep collections partial; in that case an existing note can remain stale. A successful collection is required to replace it. The Markdown format cannot safely prove that a newer partial snapshot retains every prior measurement.

Consumer wearable and BIA measurements are trend context only. This archive is not medical advice, a diagnosis, or emergency guidance.
"""
