from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import mean, median
from typing import Any

from .models import BERLIN
from .renpho import RenphoMeasurement
from .renpho_report import RenphoReportData


@dataclass(frozen=True, slots=True)
class DataAvailability:
    available: tuple[str, ...]
    unavailable: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActivitySummary:
    measured_at: datetime
    name: str
    activity_type: str
    duration_minutes: float
    distance_km: float | None
    calories: float | None
    average_hr: float | None
    max_hr: float | None
    aerobic_effect: float | None
    anaerobic_effect: float | None
    training_load: float | None
    hr_zone_minutes: tuple[float, ...]
    activity_id: str | None = None


@dataclass(frozen=True, slots=True)
class DailyRecovery:
    day: date
    steps: int | None
    moderate_minutes: int | None
    vigorous_minutes: int | None
    sleep_hours: float | None
    sleep_score: float | None
    resting_hr: float | None
    stress: float | None
    body_battery_charged: float | None
    body_battery_drained: float | None
    readiness_score: float | None


@dataclass(frozen=True, slots=True)
class PressureReading:
    measured_at: datetime
    systolic: int
    diastolic: int
    pulse: int | None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class DailyPressure:
    day: date
    systolic: float
    diastolic: float
    count: int


@dataclass(frozen=True, slots=True)
class PressureSeries:
    readings: tuple[PressureReading, ...]
    daily_averages: tuple[DailyPressure, ...]
    average_systolic: float | None
    average_diastolic: float | None
    days_covered: int
    has_extreme: bool
    esc_category: str


@dataclass(frozen=True, slots=True)
class BodyMeasurementPoint:
    measured_at: datetime
    weight_kg: float
    body_fat_pct: float | None
    muscle_mass_kg: float | None
    source: str
    report: RenphoReportData | None = None


@dataclass(frozen=True, slots=True)
class WeeklyInsight:
    level: str
    text: str
    category: str = "General"
    confidence: str = "Context only"
    source_title: str | None = None
    source_url: str | None = None


WHO_ACTIVITY = (
    "WHO physical activity guidelines",
    "https://www.who.int/publications/i/item/9789240015128",
)
AASM_SLEEP = (
    "AASM/SRS adult sleep duration consensus",
    "https://aasm.org/resources/pdf/adultsleepdurationconsensus.pdf",
)
AHA_PRESSURE = (
    "American Heart Association home BP monitoring",
    "https://www.heart.org/en/health-topics/high-blood-pressure/understanding-blood-pressure-readings/monitoring-your-blood-pressure-at-home",
)
GARMIN_STRESS = (
    "Garmin stress tracking methodology",
    "https://www.garmin.com/en-US/garmin-technology/health-science/stress-tracking/",
)
BIA_LIMITATIONS = (
    "Review of variability in bioimpedance measurements",
    "https://pmc.ncbi.nlm.nih.gov/articles/PMC13352812/",
)


@dataclass(frozen=True, slots=True)
class DailyHealthMetrics:
    day: date
    calories: float | None
    floors: float | None
    distance_km: float | None
    min_hr: float | None
    max_hr: float | None


@dataclass(frozen=True, slots=True)
class SleepMetrics:
    day: date
    deep_hours: float | None
    light_hours: float | None
    rem_hours: float | None
    awake_hours: float | None
    overnight_hrv: float | None
    spo2: float | None
    respiration: float | None
    skin_temp_deviation: float | None


@dataclass(frozen=True, slots=True)
class LifestyleEvent:
    day: date
    name: str
    category: str
    value: float | None
    sleep_related: bool


@dataclass(frozen=True, slots=True)
class BehaviorAssociation:
    behavior: str
    metric: str
    with_days: int
    without_days: int
    median_difference: float


@dataclass(frozen=True, slots=True)
class RoutePoint:
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class ExerciseSet:
    exercise_name: str | None
    category: str | None
    set_number: int | None
    repetitions: float | None
    weight_kg: float | None
    duration_seconds: float | None
    set_type: str | None
    is_warmup: bool | None = None
    rir: float | None = None
    rpe: float | None = None


@dataclass(frozen=True, slots=True)
class ActivitySplit:
    split_number: int | None
    duration_seconds: float | None
    distance_km: float | None
    average_hr: float | None
    average_power: float | None
    average_cadence: float | None


@dataclass(frozen=True, slots=True)
class ActivityDetail:
    activity_id: str
    location_name: str | None
    elevation_gain: float | None
    average_power: float | None
    route: tuple[RoutePoint, ...]
    average_cadence: float | None = None
    exercises: tuple[ExerciseSet, ...] = ()
    splits: tuple[ActivitySplit, ...] = ()
    component_types: tuple[str, ...] = ()
    exercise_sets_available: bool = False


@dataclass(frozen=True, slots=True)
class HydrationNutrition:
    day: date
    hydration_ml: float | None
    hydration_goal_ml: float | None
    nutrition_calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    nutrition_goal_calories: float | None = None
    protein_goal_g: float | None = None
    carbs_goal_g: float | None = None
    fat_goal_g: float | None = None


@dataclass(frozen=True, slots=True)
class ExtendedGarminDomain:
    name: str
    summary: str


@dataclass(frozen=True, slots=True)
class ChartAxisSpec:
    axis_id: str
    label: str
    unit: str
    formatter: str
    minimum: float | None = None
    maximum: float | None = None
    scale: bool = True


@dataclass(frozen=True, slots=True)
class ChartSeries:
    series_id: str
    name: str
    values: tuple[float | None, ...]
    axis_id: str
    render_type: str
    color_token: str
    source: str = "Garmin"


@dataclass(frozen=True, slots=True)
class ChartReferenceBand:
    label: str
    start: float
    end: float
    color_token: str


@dataclass(frozen=True, slots=True)
class ChartSpec:
    chart_id: str
    title: str
    timestamps: tuple[str, ...]
    axes: tuple[ChartAxisSpec, ...]
    series: tuple[ChartSeries, ...]
    reference_bands: tuple[ChartReferenceBand, ...] = ()


@dataclass(frozen=True, slots=True)
class ComprehensiveMetrics:
    daily_health: tuple[DailyHealthMetrics, ...]
    sleep: tuple[SleepMetrics, ...]
    stress_by_day: tuple[float | None, ...]
    body_battery_by_day: tuple[float | None, ...]
    hydration_nutrition: tuple[HydrationNutrition, ...]
    lifestyle: tuple[LifestyleEvent, ...]
    associations: tuple[BehaviorAssociation, ...]
    activity_details: tuple[ActivityDetail, ...]
    extended: tuple[ExtendedGarminDomain, ...]
    charts: tuple[ChartSpec, ...]
    truncated: tuple[str, ...]
    map_tiles_enabled: bool


@dataclass(frozen=True, slots=True)
class WeeklyHealthReport:
    start_date: date
    end_date: date
    generated_at: datetime
    availability: DataAvailability
    activities: tuple[ActivitySummary, ...]
    recovery: tuple[DailyRecovery, ...]
    pressure: PressureSeries
    body: tuple[BodyMeasurementPoint, ...]
    training_status: str | None
    vo2_max: float | None
    insights: tuple[WeeklyInsight, ...]
    comprehensive: ComprehensiveMetrics

    @property
    def period_days(self) -> int:
        """Return the inclusive calendar span, independent of local DST transitions."""
        return (self.end_date - self.start_date).days + 1

    @property
    def total_training_minutes(self) -> float:
        return sum(item.duration_minutes for item in self.activities)


def build_report(
    *,
    start_date: date,
    end_date: date,
    garmin: dict[str, Any],
    renpho: list[RenphoMeasurement],
    available: list[str],
    unavailable: list[str],
    generated_at: datetime | None = None,
) -> WeeklyHealthReport:
    """Normalize collected source data into the model shared by web, PDF and archive views."""
    activities = tuple(_activities(garmin.get("activities", [])))
    recovery = tuple(_recovery(start_date, end_date, garmin))
    pressure_readings = tuple(_pressure_readings(garmin.get("pressure", {})))
    daily_pressure = tuple(_daily_pressure(pressure_readings))
    average_systolic = _average([x.systolic for x in pressure_readings])
    average_diastolic = _average([x.diastolic for x in pressure_readings])
    pressure = PressureSeries(
        pressure_readings,
        daily_pressure,
        average_systolic,
        average_diastolic,
        len(daily_pressure),
        any(x.systolic > 180 or x.diastolic > 120 for x in pressure_readings),
        _esc_category(average_systolic, average_diastolic),
    )
    body = tuple(_merge_body(_garmin_body(garmin.get("body", {})), renpho, start_date, end_date))
    status = _training_status(garmin.get("training_status"))
    vo2_max = _vo2_max(garmin.get("max_metrics"))
    report = WeeklyHealthReport(
        start_date,
        end_date,
        generated_at or datetime.now(BERLIN),
        DataAvailability(tuple(sorted(set(available))), tuple(sorted(set(unavailable)))),
        activities,
        recovery,
        pressure,
        body,
        status,
        vo2_max,
        (),
        _comprehensive(
            start_date,
            end_date,
            garmin,
            activities,
            recovery,
            pressure,
            body,
        ),
    )
    return WeeklyHealthReport(
        report.start_date,
        report.end_date,
        report.generated_at,
        report.availability,
        report.activities,
        report.recovery,
        report.pressure,
        report.body,
        report.training_status,
        report.vo2_max,
        tuple(_insights(report)),
        report.comprehensive,
    )


def _activities(raw: Any) -> list[ActivitySummary]:
    result: list[ActivitySummary] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        measured_at = _datetime(item.get("startTimeLocal") or item.get("beginTimestamp"))
        if measured_at is None:
            continue
        kind = item.get("activityType", {})
        kind_name = kind.get("typeKey") if isinstance(kind, dict) else kind
        result.append(
            ActivitySummary(
                measured_at,
                str(item.get("activityName") or kind_name or "Activity"),
                str(kind_name or "other"),
                (_number(item.get("duration")) or 0) / 60,
                _scaled(item.get("distance"), 1000),
                _number(item.get("calories")),
                _number(item.get("averageHR")),
                _number(item.get("maxHR")),
                _number(item.get("aerobicTrainingEffect")),
                _number(item.get("anaerobicTrainingEffect")),
                _number(item.get("activityTrainingLoad")),
                tuple(
                    (_number(item.get(f"hrTimeInZone_{zone}")) or 0) / 60 for zone in range(1, 6)
                ),
                _activity_id(item.get("activityId")),
            )
        )
    return sorted(result, key=lambda item: item.measured_at)


def _recovery(start: date, end: date, raw: dict[str, Any]) -> list[DailyRecovery]:
    stats = raw.get("stats", {})
    sleep = raw.get("sleep", {})
    readiness = raw.get("readiness", {})
    battery = raw.get("body_battery", {})
    result: list[DailyRecovery] = []
    day = start
    while day <= end:
        stat = stats.get(day.isoformat(), {}) if isinstance(stats, dict) else {}
        slp = sleep.get(day.isoformat(), {}) if isinstance(sleep, dict) else {}
        ready = readiness.get(day.isoformat(), {}) if isinstance(readiness, dict) else {}
        bat = battery.get(day.isoformat(), {}) if isinstance(battery, dict) else {}
        daily = slp.get("dailySleepDTO", {}) if isinstance(slp, dict) else {}
        result.append(
            DailyRecovery(
                day,
                _integer(stat.get("totalSteps")),
                _integer(stat.get("moderateIntensityMinutes")),
                _integer(stat.get("vigorousIntensityMinutes")),
                _scaled(daily.get("sleepTimeSeconds"), 3600),
                _number(daily.get("sleepScores", {}).get("overall", {}).get("value"))
                if isinstance(daily.get("sleepScores"), dict)
                else _number(daily.get("sleepScore")),
                _number(slp.get("restingHeartRate") or stat.get("restingHeartRate")),
                _number(stat.get("averageStressLevel")),
                _number(bat.get("charged")),
                _number(bat.get("drained")),
                _number(ready.get("score")),
            )
        )
        day += timedelta(days=1)
    return result


def _pressure_readings(raw: Any) -> list[PressureReading]:
    result: list[PressureReading] = []
    for item in _nested_records(raw, {"systolic", "diastolic"}):
        measured = _datetime(
            item.get("measurementTimestampGMT")
            or item.get("measurementTimestampLocal")
            or item.get("timestamp"),
            naive_utc=item.get("measurementTimestampGMT") is not None,
        )
        systolic, diastolic = _integer(item.get("systolic")), _integer(item.get("diastolic"))
        if measured is not None and systolic is not None and diastolic is not None:
            result.append(
                PressureReading(
                    measured,
                    systolic,
                    diastolic,
                    _integer(item.get("pulse")),
                    _string(item.get("notes") or item.get("note")),
                )
            )
    return sorted(result, key=lambda item: item.measured_at)


def _garmin_body(raw: Any) -> list[BodyMeasurementPoint]:
    items = raw.get("dateWeightList", []) if isinstance(raw, dict) else []
    result: list[BodyMeasurementPoint] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        measured = _datetime(item.get("timestampGMT") or item.get("date"))
        weight = _number(item.get("weight"))
        if measured is None or weight is None:
            continue
        if weight > 1000:
            weight /= 1000
        muscle = _number(item.get("muscleMass"))
        if muscle is not None and muscle > 1000:
            muscle /= 1000
        result.append(
            BodyMeasurementPoint(
                measured,
                weight,
                _number(item.get("bodyFat") or item.get("bodyFatPercentage")),
                muscle,
                "Garmin",
            )
        )
    return result


def _merge_body(
    garmin: list[BodyMeasurementPoint],
    renpho: list[RenphoMeasurement],
    start: date,
    end: date,
) -> list[BodyMeasurementPoint]:
    points = list(garmin)
    for item in renpho:
        body = item.body
        if not start <= body.measured_at.date() <= end:
            continue
        match = next(
            (
                point
                for point in points
                if abs((point.measured_at - body.measured_at).total_seconds()) <= 120
                and abs(point.weight_kg - body.weight) <= 0.05
            ),
            None,
        )
        renpho_point = BodyMeasurementPoint(
            body.measured_at,
            body.weight,
            body.percent_fat,
            body.muscle_mass,
            "RENPHO",
            item.report,
        )
        if match is None:
            points.append(renpho_point)
        else:
            points[points.index(match)] = BodyMeasurementPoint(
                body.measured_at,
                body.weight,
                body.percent_fat if body.percent_fat is not None else match.body_fat_pct,
                body.muscle_mass if body.muscle_mass is not None else match.muscle_mass_kg,
                "RENPHO + Garmin",
                item.report,
            )
    return sorted(points, key=lambda point: point.measured_at)


def _insights(report: WeeklyHealthReport) -> list[WeeklyInsight]:
    insights: list[WeeklyInsight] = []
    moderate = sum(x.moderate_minutes or 0 for x in report.recovery)
    vigorous = sum(x.vigorous_minutes or 0 for x in report.recovery)
    equivalent = moderate + vigorous * 2
    if equivalent:
        text = f"Garmin recorded {moderate} moderate and {vigorous} vigorous intensity minutes."
        text += (
            " This meets the WHO weekly minimum."
            if equivalent >= 150
            else " This is below the WHO weekly minimum; if the device captured the full week, gradually adding activity is one option."
        )
        insights.append(WeeklyInsight("info", text, "Activity", "High", *WHO_ACTIVITY))
    strength_days = {
        activity.measured_at.date()
        for activity in report.activities
        if "strength" in f"{activity.activity_type} {activity.name}".lower()
    }
    if report.activities:
        insights.append(
            WeeklyInsight(
                "info",
                f"Strength activity was recorded on {len(strength_days)} day(s); WHO guidance recommends muscle-strengthening activity on at least 2 days per week.",
                "Activity",
                "High",
                *WHO_ACTIVITY,
            )
        )
    sleep_values = [item.sleep_hours for item in report.recovery if item.sleep_hours is not None]
    if len(sleep_values) >= 4:
        typical_sleep = median(sleep_values)
        if typical_sleep < 7:
            insights.append(
                WeeklyInsight(
                    "caution",
                    f"Median recorded sleep was {typical_sleep:.1f} hours across {len(sleep_values)} nights. Adults are generally advised to sleep 7 or more hours regularly; consider whether the schedule allows enough sleep opportunity.",
                    "Sleep",
                    "Moderate",
                    *AASM_SLEEP,
                )
            )
        else:
            insights.append(
                WeeklyInsight(
                    "info",
                    f"Median recorded sleep was {typical_sleep:.1f} hours across {len(sleep_values)} nights, consistent with the general 7+ hour adult recommendation.",
                    "Sleep",
                    "Moderate",
                    *AASM_SLEEP,
                )
            )
    stress_values = [item.stress for item in report.recovery if item.stress is not None]
    if len(stress_values) >= 4 and median(stress_values) > 50:
        insights.append(
            WeeklyInsight(
                "caution",
                f"Median Garmin all-day stress was {median(stress_values):.0f}. Garmin classifies 51–75 as medium physiological stress; review recurring context, sleep and recovery, but do not treat the score as a diagnosis or a measure of psychological stress.",
                "Recovery",
                "Device context",
                *GARMIN_STRESS,
            )
        )
    if report.pressure.readings:
        if report.pressure.days_covered < 3:
            insights.append(
                WeeklyInsight(
                    "caution",
                    "Blood pressure coverage is too sparse for a meaningful weekly trend. For a more interpretable log, measure under consistent conditions and take two readings one minute apart when practical.",
                    "Blood pressure",
                    "High",
                    *AHA_PRESSURE,
                )
            )
        else:
            insights.append(
                WeeklyInsight(
                    "info",
                    f"Observed home blood pressure averaged {report.pressure.average_systolic:.0f}/{report.pressure.average_diastolic:.0f} mmHg across {report.pressure.days_covered} days. Only a clinician can interpret this in personal medical context.",
                    "Blood pressure",
                    "High",
                    *AHA_PRESSURE,
                )
            )
    if report.pressure.has_extreme:
        insights.append(
            WeeklyInsight(
                "alert",
                "At least one reading exceeded 180 systolic or 120 diastolic. Repeat after at least one minute; contact a healthcare professional promptly if it remains very high, and seek emergency help if symptoms are present.",
                "Blood pressure",
                "High",
                *AHA_PRESSURE,
            )
        )
    if len(report.body) >= 2:
        delta = report.body[-1].weight_kg - report.body[0].weight_kg
        insights.append(
            WeeklyInsight(
                "info",
                f"Scale weight changed {delta:+.1f} kg over the report window. Treat body-composition estimates as a trend and compare measurements taken under similar hydration, meal, exercise and time-of-day conditions.",
                "Body composition",
                "Moderate",
                *BIA_LIMITATIONS,
            )
        )
    if not insights:
        insights.append(
            WeeklyInsight(
                "caution", "There is not enough data for a reliable weekly trend summary."
            )
        )
    return insights


def render_weekly_html(report: WeeklyHealthReport, csrf: str, report_id: str) -> str:
    def e(value: object) -> str:
        return html.escape(str(value), quote=True)

    insights = "".join(
        f"<li class='{e(x.level)}'><strong>{e(x.category)}</strong> "
        f"<span class=confidence>{e(x.confidence)} confidence</span><br>{e(x.text)}"
        + (
            f" <a href='{e(x.source_url)}' target=_blank rel='noreferrer noopener'>"
            f"{e(x.source_title)}</a>"
            if x.source_url and x.source_title
            else ""
        )
        + "</li>"
        for x in report.insights
    )
    activities = (
        "".join(
            f"<tr><td>{x.measured_at:%a %H:%M}</td><td>"
            + (
                f"<a href='{e(garmin_activity_url(x.activity_id))}' target=_blank "
                f"rel='noreferrer noopener'>{e(x.name)}</a>"
                if garmin_activity_url(x.activity_id)
                else e(x.name)
            )
            + f"</td><td>{x.duration_minutes:.0f} min</td>"
            f"<td>{_fmt(x.distance_km, ' km')}</td>"
            f"<td>{_fmt(x.average_hr, ' bpm')}</td></tr>"
            for x in report.activities
        )
        or "<tr><td colspan=5>No activities available</td></tr>"
    )
    recovery = "".join(
        f"<tr><td>{x.day:%a %d}</td><td>{_fmt(x.steps)}</td><td>{_fmt(x.sleep_hours, ' h')}</td><td>{_fmt(x.resting_hr, ' bpm')}</td><td>{_fmt(x.stress)}</td><td>{_fmt(x.readiness_score)}</td></tr>"
        for x in report.recovery
    )
    pressure = (
        "".join(
            f"<tr><td>{x.measured_at:%a %H:%M}</td><td>{x.systolic}/{x.diastolic}</td><td>{_fmt(x.pulse, ' bpm')}</td></tr>"
            for x in report.pressure.readings
        )
        or "<tr><td colspan=3>No readings available</td></tr>"
    )
    pressure_daily = (
        "".join(
            f"<tr><td>{x.day:%a %d}</td><td>{x.systolic:.0f}/{x.diastolic:.0f}</td><td>{x.count}</td></tr>"
            for x in report.pressure.daily_averages
        )
        or "<tr><td colspan=3>No daily averages available</td></tr>"
    )
    body = (
        "".join(
            f"<tr><td>{x.measured_at:%a %H:%M}</td><td>{x.weight_kg:.1f} kg</td><td>{_fmt(x.body_fat_pct, '%')}</td><td>{_fmt(x.muscle_mass_kg, ' kg')}</td><td>{e(x.source)}</td></tr>"
            for x in report.body
        )
        or "<tr><td colspan=5>No measurements available</td></tr>"
    )
    chart_panels = "".join(
        f"<article class=chart-panel><h3>{e(chart.title)}</h3><div class=interactive-chart data-chart='{e(chart.chart_id)}' tabindex=0 role=img aria-label='{e(chart.title)}'></div></article>"
        for chart in report.comprehensive.charts
    )
    lifestyle = (
        "".join(
            f"<tr><td>{day:%d %b}</td><td><div class=lifestyle-list>"
            + "".join(f"<span class=lifestyle-chip>{e(label)}</span>" for label in labels)
            + "</div></td></tr>"
            for day, labels in group_lifestyle_events(report.comprehensive.lifestyle)
        )
        or "<tr><td colspan=2>No lifestyle events available</td></tr>"
    )
    associations = (
        "".join(
            f"<li><strong>{e(item.behavior)}</strong> and {e(item.metric)}: observed median difference {item.median_difference:+.1f} ({item.with_days} days with / {item.without_days} without). This is an association, not evidence of causation.</li>"
            for item in report.comprehensive.associations
        )
        or "<li>Not enough repeated observations for behavior comparisons.</li>"
    )
    routes = (
        "".join(
            f"<article class=route-panel><h3>{e(item.location_name or 'Activity route')}</h3><div class=route-chart data-route='{e(item.activity_id)}' tabindex=0 role=img aria-label='Route for {e(item.location_name or item.activity_id)}'></div></article>"
            for item in report.comprehensive.activity_details
            if item.route
        )
        or "<p>No route data available.</p>"
    )
    extended = (
        "".join(
            f"<li><strong>{e(item.name)}</strong>: {e(item.summary)}</li>"
            for item in report.comprehensive.extended
        )
        or "<li>No extended domains available.</li>"
    )
    unavailable = ", ".join(report.availability.unavailable) or "None"
    return f"""
<section class=hero><p class=eyebrow>PERSONAL HEALTH SUMMARY</p><h2>{report.period_days}-day health report</h2><p>{report.start_date:%d %b %Y} - {report.end_date:%d %b %Y}</p>
<div class=metrics><div><strong>{len(report.activities)}</strong><span>workouts</span></div><div><strong>{report.total_training_minutes:.0f}</strong><span>training min</span></div><div><strong>{len(report.pressure.readings)}</strong><span>BP readings</span></div><div><strong>{len(report.body)}</strong><span>body records</span></div></div></section>
<section><h2>Period overview</h2><ul>{insights}</ul><p><strong>Unavailable:</strong> {e(unavailable)}</p></section>
<section><h2>Interactive health dashboard</h2><p>Use the legend to show or hide series. Focus or hover over a point for its value.</p><div class=chart-grid>{chart_panels}</div></section>
<section><h2>Training</h2><div class=chart>{_bar_chart([x.duration_minutes for x in report.activities], "#4776e6")}</div><table><tr><th>Time</th><th>Activity</th><th>Duration</th><th>Distance</th><th>Avg HR</th></tr>{activities}</table></section>
<section><h2>Recovery and activity</h2><table><tr><th>Day</th><th>Steps</th><th>Sleep</th><th>Resting HR</th><th>Stress</th><th>Readiness</th></tr>{recovery}</table><p><strong>Training status:</strong> {e(report.training_status or "Not available")}</p></section>
<section><h2>Blood pressure</h2>{_line_chart([(x.systolic, x.diastolic) for x in report.pressure.readings])}<p><strong>{e(report.pressure.esc_category)}</strong></p><h3>Daily averages</h3><table><tr><th>Day</th><th>Average</th><th>Readings</th></tr>{pressure_daily}</table><h3>All readings</h3><table><tr><th>Time</th><th>Blood pressure</th><th>Pulse</th></tr>{pressure}</table><p>Observed average: {_fmt(report.pressure.average_systolic)}/{_fmt(report.pressure.average_diastolic)} mmHg across {report.pressure.days_covered} day(s).</p></section>
<section><h2>Weight and body composition</h2>{_sparkline([x.weight_kg for x in report.body])}<table><tr><th>Time</th><th>Weight</th><th>Body fat</th><th>Muscle</th><th>Source</th></tr>{body}</table></section>
<section><h2>Lifestyle Logging - 30-day context</h2><table><tr><th>Date</th><th>Logged behaviors</th></tr>{lifestyle}</table><h3>Observed associations</h3><ul>{associations}</ul></section>
<section><h2>Activity routes</h2><div class=route-grid>{routes}</div></section>
<section><details><summary><strong>Extended Garmin appendix</strong></summary><ul>{extended}</ul></details></section>
<section><h2>Practical next steps</h2><p>This collected rule-based summary covers the available data for the week. Prioritize repeatable changes and discuss medical measurements with a qualified professional.</p><ol class=recommendations>{insights}</ol></section>
<section><h2>Methodology and limitations</h2><p>This report is for personal monitoring, not diagnosis. Consumer wearable and BIA values are estimates. Hydration, meals, recent exercise and measurement timing can change body-composition readings. Blood pressure should be measured with a validated upper-arm cuff and interpreted from repeated measurements with a healthcare professional.</p><p>References: WHO Guidelines on Physical Activity and Sedentary Behaviour (2020); 2024 ESC Guidelines for elevated blood pressure and hypertension; AHA Home Blood Pressure Monitoring guidance.</p></section>
<section><form method=post action='/weekly-report/{e(report_id)}/download'><input type=hidden name=csrf value='{e(csrf)}'><button>Download PDF</button></form><a href='/'>Home</a></section><div id=chart-tooltip role=status aria-live=polite></div><script src='/assets/weekly-charts.js' data-report='{e(report_id)}' defer></script>"""


def _bar_chart(values: list[float], color: str) -> str:
    if not values:
        return "<p>No chart data</p>"
    maximum = max(values) or 1
    bars = "".join(
        f"<span style='height:{max(4, value / maximum * 100):.1f}%;background:{color}' title='{value:.0f} min'></span>"
        for value in values
    )
    return f"<div class=bars>{bars}</div>"


def _line_chart(values: list[tuple[int, int]]) -> str:
    if not values:
        return "<p>No chart data</p>"
    return f"<div class=trend><strong>{min(x for x, _ in values)}-{max(x for x, _ in values)}</strong> systolic range <span></span><strong>{min(y for _, y in values)}-{max(y for _, y in values)}</strong> diastolic range</div>"


def _sparkline(values: list[float]) -> str:
    if not values:
        return "<p>No chart data</p>"
    return f"<div class=trend><strong>{values[0]:.1f} kg</strong><span></span><strong>{values[-1]:.1f} kg</strong></div>"


def _training_status(raw: Any) -> str | None:
    if not isinstance(raw, dict):
        return None
    return _find_status(raw.get("mostRecentTrainingStatus"))


def _find_status(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("trainingStatusFeedbackPhrase", "trainingStatus", "status"):
            if value.get(key) is not None:
                return str(value[key]).replace("_", " ").title()
        for item in value.values():
            found = _find_status(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_status(item)
            if found:
                return found
    return None


def _daily_pressure(readings: tuple[PressureReading, ...]) -> list[DailyPressure]:
    grouped: dict[date, list[PressureReading]] = {}
    for reading in readings:
        grouped.setdefault(reading.measured_at.date(), []).append(reading)
    return [
        DailyPressure(
            day,
            mean(item.systolic for item in values),
            mean(item.diastolic for item in values),
            len(values),
        )
        for day, values in sorted(grouped.items())
    ]


def _esc_category(systolic: float | None, diastolic: float | None) -> str:
    if systolic is None or diastolic is None:
        return "ESC home-BP category unavailable"
    if systolic >= 135 or diastolic >= 85:
        return "At or above the ESC home-BP hypertension threshold"
    if systolic < 120 and diastolic < 70:
        return "Below the ESC elevated-BP range"
    return "Within the ESC elevated-BP range"


def _nested_records(value: Any, keys: set[str]) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        records = [value] if keys <= set(value) else []
        for item in value.values():
            records.extend(_nested_records(item, keys))
        return records
    if isinstance(value, list | tuple):
        return [record for item in value for record in _nested_records(item, keys)]
    return []


def _datetime(value: Any, *, naive_utc: bool = False) -> datetime | None:
    if isinstance(value, int | float):
        timestamp = float(value) / 1000 if value > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(timestamp, UTC).astimezone(BERLIN)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC if naive_utc else BERLIN)
    return parsed.astimezone(BERLIN)


def _number(value: Any) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _activity_id(value: Any) -> str | None:
    candidate = str(value) if value is not None else ""
    return candidate if candidate.isascii() and candidate.isdecimal() else None


def garmin_activity_url(activity_id: str | None) -> str | None:
    safe_id = _activity_id(activity_id)
    if safe_id is None:
        return None
    return f"https://connect.garmin.com/modern/activity/{safe_id}"


def _integer(value: Any) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _scaled(value: Any, scale: float) -> float | None:
    number = _number(value)
    return None if number is None else number / scale


def _average(values: list[int]) -> float | None:
    return mean(values) if values else None


def _vo2_max(raw: Any) -> float | None:
    """Extract a plausible VO₂-max estimate from Garmin's nested max-metrics response."""
    preferred: list[float] = []
    fallback: list[float] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = "".join(char for char in str(key).lower() if char.isalnum())
                number = _number(nested)
                if number is not None and 10 <= number <= 100:
                    if normalized in {"vo2maxprecisevalue", "vo2maxvalue"}:
                        preferred.append(number)
                    elif normalized == "vo2max":
                        fallback.append(number)
                visit(nested)
        elif isinstance(value, list | tuple):
            for nested in value:
                visit(nested)

    visit(raw)
    values = preferred or fallback
    return values[0] if values else None


def _fmt(value: float | int | None, suffix: str = "") -> str:
    if value is None:
        return "Not available"
    return f"{value:.1f}{suffix}" if isinstance(value, float) else f"{value}{suffix}"


def _comprehensive(
    start: date,
    end: date,
    raw: dict[str, Any],
    activities: tuple[ActivitySummary, ...],
    recovery: tuple[DailyRecovery, ...],
    pressure: PressureSeries,
    body: tuple[BodyMeasurementPoint, ...],
) -> ComprehensiveMetrics:
    stats = raw.get("stats", {}) if isinstance(raw.get("stats"), dict) else {}
    sleep_raw = raw.get("sleep", {}) if isinstance(raw.get("sleep"), dict) else {}
    stress_raw = raw.get("stress", {}) if isinstance(raw.get("stress"), dict) else {}
    hrv_raw = raw.get("hrv", {}) if isinstance(raw.get("hrv"), dict) else {}
    spo2_raw = raw.get("spo2", {}) if isinstance(raw.get("spo2"), dict) else {}
    respiration_raw = raw.get("respiration", {}) if isinstance(raw.get("respiration"), dict) else {}
    hydration_raw = raw.get("hydration", {}) if isinstance(raw.get("hydration"), dict) else {}
    nutrition_raw = raw.get("nutrition", {}) if isinstance(raw.get("nutrition"), dict) else {}
    battery_raw = raw.get("body_battery", {}) if isinstance(raw.get("body_battery"), dict) else {}
    days: list[date] = []
    day = start
    while day <= end:
        days.append(day)
        day += timedelta(days=1)
    health: list[DailyHealthMetrics] = []
    sleep: list[SleepMetrics] = []
    hydration: list[HydrationNutrition] = []
    stress: list[float | None] = []
    battery: list[float | None] = []
    for current in days:
        key = current.isoformat()
        stat = _mapping(stats.get(key))
        slp = _mapping(sleep_raw.get(key))
        daily = _mapping(slp.get("dailySleepDTO"))
        hrv = _mapping(hrv_raw.get(key))
        hrv_summary = _mapping(hrv.get("hrvSummary"))
        spo2 = _mapping(spo2_raw.get(key))
        respiration = _mapping(respiration_raw.get(key))
        hyd = _mapping(hydration_raw.get(key))
        nutrition = _mapping(nutrition_raw.get(key))
        health.append(
            DailyHealthMetrics(
                current,
                _number(stat.get("burnedKilocalories")),
                _number(stat.get("floorsAscended")),
                _scaled(stat.get("totalDistanceMeters"), 1000),
                _number(stat.get("minHeartRate")),
                _number(stat.get("maxHeartRate")),
            )
        )
        sleep.append(
            SleepMetrics(
                current,
                _scaled(daily.get("deepSleepSeconds"), 3600),
                _scaled(daily.get("lightSleepSeconds"), 3600),
                _scaled(daily.get("remSleepSeconds"), 3600),
                _scaled(daily.get("awakeSleepSeconds"), 3600),
                _number(hrv_summary.get("weeklyAvg") or hrv_summary.get("lastNightAvg")),
                _number(spo2.get("avgSleepSpO2") or spo2.get("averageSpO2")),
                _number(respiration.get("avgSleepRespirationValue")),
                _number(slp.get("avgSkinTempDeviationC")),
            )
        )
        stress_item = _mapping(stress_raw.get(key))
        battery_item = _mapping(battery_raw.get(key))
        stress.append(_number(stress_item.get("avgStressLevel") or stat.get("averageStressLevel")))
        battery.append(_number(battery_item.get("charged")))
        totals, goals = _nutrition_totals(nutrition)
        consumed_water = _number(hyd.get("valueInML"))
        if consumed_water is not None and consumed_water <= 0:
            consumed_water = None
        hydration.append(
            HydrationNutrition(
                current,
                consumed_water,
                _number(hyd.get("goalInML")),
                totals[0],
                totals[1],
                totals[2],
                totals[3],
                goals[0],
                goals[1],
                goals[2],
                goals[3],
            )
        )
    lifestyle = tuple(_lifestyle_events(raw.get("lifestyle", {})))
    associations = tuple(_behavior_associations(lifestyle, raw))
    details = tuple(
        _activity_details(
            raw.get("activity_details", {}), include_routes=raw.get("include_routes") is True
        )
    )
    extended = tuple(_extended_domains(raw.get("extended", {})))
    charts = _chart_specs(
        days,
        health,
        sleep,
        stress,
        battery,
        hydration,
        activities,
        recovery,
        pressure,
        body,
    )
    truncated = tuple(str(x) for x in raw.get("truncated", []) if isinstance(x, str))
    return ComprehensiveMetrics(
        tuple(health),
        tuple(sleep),
        tuple(stress),
        tuple(battery),
        tuple(hydration),
        lifestyle,
        associations,
        details,
        extended,
        charts,
        truncated,
        raw.get("map_tiles_enabled") is True,
    )


def chart_payload(report: WeeklyHealthReport) -> dict[str, Any]:
    """Serialize chart axes, nullable series and opt-in routes for both browser renderers."""
    return {
        "charts": [
            {
                "id": chart.chart_id,
                "title": chart.title,
                "timestamps": list(chart.timestamps),
                "axes": [
                    {
                        "id": axis.axis_id,
                        "label": axis.label,
                        "unit": axis.unit,
                        "formatter": axis.formatter,
                        "minimum": axis.minimum,
                        "maximum": axis.maximum,
                        "scale": axis.scale,
                    }
                    for axis in chart.axes
                ],
                "series": [
                    {
                        "id": series.series_id,
                        "name": series.name,
                        "values": list(series.values),
                        "axis_id": series.axis_id,
                        "render_type": series.render_type,
                        "color_token": series.color_token,
                        "source": series.source,
                    }
                    for series in chart.series
                ],
                "reference_bands": [
                    {
                        "label": band.label,
                        "start": band.start,
                        "end": band.end,
                        "color_token": band.color_token,
                    }
                    for band in chart.reference_bands
                ],
            }
            for chart in report.comprehensive.charts
        ],
        "routes": [
            {
                "id": detail.activity_id,
                "name": detail.location_name or "Activity route",
                "points": [[point.latitude, point.longitude] for point in detail.route],
            }
            for detail in report.comprehensive.activity_details
            if detail.route
        ],
        "lifestyle": [
            {"date": event.day.isoformat(), "name": event.name, "value": event.value}
            for event in report.comprehensive.lifestyle
        ],
        "map_tiles_enabled": report.comprehensive.map_tiles_enabled,
    }


def _chart_specs(
    days: list[date],
    health: list[DailyHealthMetrics],
    sleep: list[SleepMetrics],
    stress: list[float | None],
    battery: list[float | None],
    hydration: list[HydrationNutrition],
    activities: tuple[ActivitySummary, ...],
    recovery: tuple[DailyRecovery, ...],
    pressure: PressureSeries,
    body: tuple[BodyMeasurementPoint, ...],
) -> tuple[ChartSpec, ...]:
    timestamps = tuple(day.isoformat() for day in days)
    activity_days = {
        day: [item for item in activities if item.measured_at.date() == day] for day in days
    }

    def axis(
        axis_id: str,
        label: str,
        unit: str,
        formatter: str,
        minimum: float | None = None,
        maximum: float | None = None,
        scale: bool = True,
    ) -> ChartAxisSpec:
        return ChartAxisSpec(axis_id, label, unit, formatter, minimum, maximum, scale)

    def series(
        series_id: str,
        name: str,
        values: tuple[float | None, ...],
        axis_id: str,
        color_token: str,
        render_type: str = "line",
        source: str = "Garmin",
    ) -> ChartSeries:
        return ChartSeries(series_id, name, values, axis_id, render_type, color_token, source)

    return (
        ChartSpec(
            "stress-battery",
            "Stress and Body Battery",
            timestamps,
            (axis("score", "Score", "score", "integer", 0, 100, False),),
            (
                series("stress", "Stress", tuple(stress), "score", "stress"),
                series("body-battery", "Body Battery", tuple(battery), "score", "battery"),
            ),
        ),
        ChartSpec(
            "sleep-duration",
            "Sleep duration and stages",
            timestamps,
            (axis("hours", "Hours", "h", "one_decimal", 0),),
            (
                series(
                    "sleep-duration",
                    "Sleep duration",
                    tuple(x.sleep_hours for x in recovery),
                    "hours",
                    "sleep",
                    "bar",
                ),
                series(
                    "deep-sleep", "Deep sleep", tuple(x.deep_hours for x in sleep), "hours", "deep"
                ),
                series("rem-sleep", "REM sleep", tuple(x.rem_hours for x in sleep), "hours", "rem"),
            ),
        ),
        ChartSpec(
            "sleep-score",
            "Sleep score",
            timestamps,
            (axis("score", "Score", "score", "integer", 0, 100, False),),
            (
                series(
                    "sleep-score",
                    "Sleep score",
                    tuple(x.sleep_score for x in recovery),
                    "score",
                    "sleep",
                ),
            ),
        ),
        ChartSpec(
            "hrv",
            "Overnight HRV",
            timestamps,
            (axis("hrv", "HRV", "ms", "integer"),),
            (
                series(
                    "overnight-hrv",
                    "Overnight HRV",
                    tuple(x.overnight_hrv for x in sleep),
                    "hrv",
                    "violet",
                ),
            ),
        ),
        ChartSpec(
            "heart-rate",
            "Heart rate",
            timestamps,
            (axis("bpm", "Heart rate", "bpm", "integer"),),
            (
                series(
                    "min-hr", "Daily minimum HR", tuple(x.min_hr for x in health), "bpm", "blue"
                ),
                series("max-hr", "Daily maximum HR", tuple(x.max_hr for x in health), "bpm", "red"),
            ),
        ),
        ChartSpec(
            "spo2",
            "Sleep SpO₂",
            timestamps,
            (axis("percent", "SpO₂", "%", "one_decimal", 80, 100, False),),
            (series("spo2", "Sleep SpO₂", tuple(x.spo2 for x in sleep), "percent", "cyan"),),
        ),
        ChartSpec(
            "respiration",
            "Sleep respiration",
            timestamps,
            (axis("breaths", "Respiration", "breaths/min", "one_decimal"),),
            (
                series(
                    "respiration",
                    "Sleep respiration",
                    tuple(x.respiration for x in sleep),
                    "breaths",
                    "violet",
                ),
            ),
        ),
        ChartSpec(
            "steps",
            "Steps",
            timestamps,
            (axis("steps", "Steps", "steps", "integer", 0),),
            (series("steps", "Steps", tuple(x.steps for x in recovery), "steps", "blue", "bar"),),
        ),
        ChartSpec(
            "calories",
            "Calories",
            timestamps,
            (axis("kcal", "Calories", "kcal", "integer", 0),),
            (
                series(
                    "calories",
                    "Calories",
                    tuple(x.calories for x in health),
                    "kcal",
                    "amber",
                    "bar",
                ),
            ),
        ),
        ChartSpec(
            "intensity-minutes",
            "Intensity minutes",
            timestamps,
            (axis("minutes", "Minutes", "min", "integer", 0),),
            (
                series(
                    "intensity-minutes",
                    "Intensity minutes",
                    tuple((x.moderate_minutes or 0) + (x.vigorous_minutes or 0) for x in recovery),
                    "minutes",
                    "violet",
                    "bar",
                ),
            ),
        ),
        ChartSpec(
            "training-duration",
            "Training duration",
            timestamps,
            (axis("minutes", "Minutes", "min", "integer", 0),),
            (
                series(
                    "training-duration",
                    "Duration",
                    tuple(
                        sum(item.duration_minutes for item in activity_days[day]) for day in days
                    ),
                    "minutes",
                    "blue",
                    "bar",
                ),
            ),
        ),
        ChartSpec(
            "training-load",
            "Training load",
            timestamps,
            (axis("load", "Load", "load", "integer", 0),),
            (
                series(
                    "training-load",
                    "Training load",
                    tuple(
                        sum(item.training_load or 0 for item in activity_days[day]) for day in days
                    ),
                    "load",
                    "amber",
                    "bar",
                ),
            ),
        ),
        ChartSpec(
            "hydration",
            "Hydration",
            timestamps,
            (axis("ml", "Hydration", "ml", "integer", 0),),
            (
                series(
                    "hydration",
                    "Hydration",
                    tuple(x.hydration_ml for x in hydration),
                    "ml",
                    "cyan",
                    "bar",
                ),
            ),
        ),
        ChartSpec(
            "nutrition",
            "Nutrition energy",
            timestamps,
            (axis("kcal", "Energy", "kcal", "integer", 0),),
            (
                series(
                    "nutrition",
                    "Nutrition calories",
                    tuple(x.nutrition_calories for x in hydration),
                    "kcal",
                    "amber",
                    "bar",
                ),
            ),
        ),
        ChartSpec(
            "blood-pressure",
            "Blood pressure",
            tuple(item.measured_at.isoformat() for item in pressure.readings),
            (axis("mmhg", "Pressure", "mmHg", "integer"),),
            (
                series(
                    "systolic",
                    "Systolic",
                    tuple(float(item.systolic) for item in pressure.readings),
                    "mmhg",
                    "red",
                    "scatter",
                ),
                series(
                    "diastolic",
                    "Diastolic",
                    tuple(float(item.diastolic) for item in pressure.readings),
                    "mmhg",
                    "blue",
                    "scatter",
                ),
            ),
            (ChartReferenceBand("Home monitoring reference", 0, 135, "neutral"),),
        ),
        ChartSpec(
            "body-kg",
            "Weight and muscle mass",
            tuple(item.measured_at.isoformat() for item in body),
            (axis("kg", "Mass", "kg", "one_decimal"),),
            (
                series(
                    "weight",
                    "Weight",
                    tuple(item.weight_kg for item in body),
                    "kg",
                    "blue",
                    source="Garmin + RENPHO",
                ),
                series(
                    "muscle-mass",
                    "Muscle mass",
                    tuple(item.muscle_mass_kg for item in body),
                    "kg",
                    "battery",
                    source="RENPHO",
                ),
            ),
        ),
        ChartSpec(
            "body-fat",
            "Body fat",
            tuple(item.measured_at.isoformat() for item in body),
            (axis("percent", "Body fat", "%", "one_decimal", 0, 100, False),),
            (
                series(
                    "body-fat",
                    "Body fat",
                    tuple(item.body_fat_pct for item in body),
                    "percent",
                    "amber",
                    source="RENPHO",
                ),
            ),
        ),
    )


def _lifestyle_events(value: Any) -> list[LifestyleEvent]:
    events: list[LifestyleEvent] = []
    if not isinstance(value, dict):
        return events
    for key, response in value.items():
        try:
            day = date.fromisoformat(str(key))
        except ValueError:
            continue
        logs = response.get("dailyLogsReport", []) if isinstance(response, dict) else []
        for log in logs if isinstance(logs, list) else []:
            if not isinstance(log, dict):
                continue
            status = str(log.get("logStatus", "")).upper()
            if status in {"NO", "FALSE", "NOT_LOGGED", "SKIPPED"}:
                continue
            # Garmin ``details`` lists configured quantity subtypes. It does
            # not represent doses logged on this date.
            if status in {"", "NONE"}:
                continue
            value = _number(log.get("logStatus"))
            events.append(
                LifestyleEvent(
                    day,
                    str(log.get("name") or "Behavior"),
                    str(log.get("category") or "Other"),
                    value,
                    bool(log.get("sleepRelated")),
                )
            )
    return events


def group_lifestyle_events(
    events: tuple[LifestyleEvent, ...],
) -> tuple[tuple[date, tuple[str, ...]], ...]:
    """Group display labels by day without changing event-level analysis data."""
    grouped: dict[date, list[str]] = {}
    for event in events:
        label = event.name
        if event.value is not None:
            value = f"{event.value:g}"
            label = f"{label} × {value}"
        grouped.setdefault(event.day, []).append(label)
    return tuple(
        (day, tuple(labels)) for day, labels in sorted(grouped.items(), key=lambda item: item[0])
    )


def _behavior_associations(
    events: tuple[LifestyleEvent, ...], raw: dict[str, Any]
) -> list[BehaviorAssociation]:
    by_behavior: dict[str, set[date]] = {}
    for event in events:
        by_behavior.setdefault(event.name, set()).add(event.day)
    metrics: dict[str, dict[date, float]] = {
        name: {}
        for name in (
            "Sleep score",
            "Overnight HRV",
            "Resting HR",
            "Stress",
            "Body Battery charged",
        )
    }
    for key, response in _mapping(raw.get("sleep")).items():
        try:
            day = date.fromisoformat(str(key))
        except ValueError:
            continue
        slp = _mapping(response)
        daily = _mapping(slp.get("dailySleepDTO"))
        score = _number(daily.get("sleepScore"))
        if score is not None:
            metrics["Sleep score"][day] = score
        resting = _number(slp.get("restingHeartRate"))
        if resting is not None:
            metrics["Resting HR"][day] = resting
    for key, response in _mapping(raw.get("hrv")).items():
        summary = _mapping(_mapping(response).get("hrvSummary"))
        value = _number(summary.get("lastNightAvg") or summary.get("weeklyAvg"))
        if value is not None:
            metrics["Overnight HRV"][date.fromisoformat(str(key))] = value
    for key, response in _mapping(raw.get("stress")).items():
        value = _number(_mapping(response).get("avgStressLevel"))
        if value is not None:
            metrics["Stress"][date.fromisoformat(str(key))] = value
    for key, response in _mapping(raw.get("body_battery")).items():
        value = _number(_mapping(response).get("charged"))
        if value is not None:
            metrics["Body Battery charged"][date.fromisoformat(str(key))] = value
    result: list[BehaviorAssociation] = []
    for behavior, event_days in by_behavior.items():
        for metric_name, observations in metrics.items():
            with_values = [value for day, value in observations.items() if day in event_days]
            without_values = [value for day, value in observations.items() if day not in event_days]
            if len(with_values) >= 3 and len(without_values) >= 3:
                result.append(
                    BehaviorAssociation(
                        behavior,
                        metric_name,
                        len(with_values),
                        len(without_values),
                        median(with_values) - median(without_values),
                    )
                )
    return result


def _activity_details(value: Any, *, include_routes: bool) -> list[ActivityDetail]:
    result: list[ActivityDetail] = []
    if not isinstance(value, dict):
        return result
    for activity_id, raw in value.items():
        mapping = _mapping(raw)
        summary = _mapping(mapping.get("summaryDTO"))
        route = (
            tuple(RoutePoint(lat, lon) for lat, lon in _coordinates(mapping))
            if include_routes
            else ()
        )
        location = _string(summary.get("locationName")) if include_routes else None
        exercises = tuple(_exercise_sets(mapping.get("exerciseSets")))
        splits = tuple(_activity_splits(mapping.get("splits")))
        component_types = tuple(_activity_component_types(mapping.get("typedSplits")))
        result.append(
            ActivityDetail(
                str(activity_id),
                location,
                _number(summary.get("elevationGain")),
                _number(summary.get("averagePower")),
                route,
                _number(summary.get("averageBikeCadence") or summary.get("averageCadence")),
                exercises,
                splits,
                component_types,
                "exerciseSets" in mapping,
            )
        )
    return result


def _records(value: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in keys:
            nested = value.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _exercise_sets(value: Any) -> list[ExerciseSet]:
    result: list[ExerciseSet] = []
    for index, item in enumerate(
        _records(value, ("exerciseSets", "sets", "exerciseSetDTOs")), start=1
    ):
        exercise = _mapping(item.get("exercise"))
        name = _string(
            item.get("exerciseName")
            or item.get("exerciseKey")
            or item.get("exerciseCategory")
            or exercise.get("name")
            or exercise.get("displayName")
        )
        category = _string(
            item.get("category") or item.get("exerciseCategory") or exercise.get("category")
        )
        repetitions = _number(_first_present(item, "repetitionCount", "repetitions", "reps"))
        duration = _number(_first_present(item, "duration", "durationSeconds", "setDuration"))
        set_type = _string(_first_present(item, "setType", "type"))
        weight_grams = _number(item.get("weightGrams"))
        raw_weight = _number(item.get("weight"))
        weight_kg = (
            weight_grams / 1000
            if weight_grams is not None
            else raw_weight / 1000
            if raw_weight is not None and raw_weight > 500
            else raw_weight
        )
        rir = _number(_first_present(item, "repsInReserve", "rir"))
        rpe = _number(_first_present(item, "rateOfPerceivedExertion", "rpe"))
        if not any(
            (
                name,
                category,
                repetitions is not None,
                weight_kg is not None,
                duration is not None,
                set_type,
                rir is not None,
                rpe is not None,
            )
        ):
            continue
        warmup_value = item.get("isWarmup")
        is_warmup = (
            warmup_value
            if isinstance(warmup_value, bool)
            else set_type.upper() == "WARMUP"
            if set_type is not None
            else None
        )
        result.append(
            ExerciseSet(
                name,
                category,
                _integer(_first_present(item, "setNumber", "setIndex")) or index,
                repetitions,
                weight_kg,
                duration,
                set_type,
                is_warmup,
                rir,
                rpe,
            )
        )
    return result


def _first_present(value: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in value and value[key] is not None:
            return value[key]
    return None


def _activity_splits(value: Any) -> list[ActivitySplit]:
    result: list[ActivitySplit] = []
    for item in _records(value, ("lapDTOs", "splits", "splitSummaries")):
        distance = _number(item.get("distance"))
        result.append(
            ActivitySplit(
                _integer(item.get("splitNumber") or item.get("lapIndex")),
                _number(item.get("duration") or item.get("elapsedDuration")),
                distance / 1000 if distance is not None else None,
                _number(item.get("averageHR") or item.get("averageHeartRate")),
                _number(item.get("averagePower")),
                _number(item.get("averageCadence") or item.get("averageBikeCadence")),
            )
        )
    return result


def _coordinates(value: Any) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    if isinstance(value, dict):
        lat = _number(value.get("latitude") or value.get("lat"))
        lon = _number(value.get("longitude") or value.get("lon"))
        if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
            result.append((lat, lon))
        for item in value.values():
            result.extend(_coordinates(item))
    elif isinstance(value, list):
        for item in value:
            result.extend(_coordinates(item))
    return result


def _extended_domains(value: Any) -> list[ExtendedGarminDomain]:
    if not isinstance(value, dict):
        return []
    result: list[ExtendedGarminDomain] = []
    for name, item in sorted(value.items()):
        if item in ({}, [], None):
            continue
        count = len(item) if isinstance(item, dict | list) else 1
        result.append(
            ExtendedGarminDomain(
                str(name).replace("_", " ").title(), f"{count} record(s) available"
            )
        )
    return result


def _activity_component_types(value: Any) -> list[str]:
    """Return ordered discipline keys from Garmin typed multisport splits."""
    result: list[str] = []
    for item in _records(value, ("typedSplits", "splits", "splitSummaries")):
        activity_type = _mapping(item.get("activityType"))
        key = _string(
            activity_type.get("typeKey") or item.get("typeKey") or item.get("activityTypeKey")
        )
        if key and key not in result:
            result.append(key)
    return result


def _nutrition_totals(
    value: dict[str, Any],
) -> tuple[
    tuple[float | None, float | None, float | None, float | None],
    tuple[float | None, float | None, float | None, float | None],
]:
    """Keep consumed nutrients separate from daily targets.

    Garmin returns daily goals even when no food was logged. Falling back from
    an empty meal log to those goals makes a target look like actual intake.
    """
    goals = _mapping(value.get("dailyNutritionGoals"))
    details = value.get("mealDetails", [])
    records = details if isinstance(details, list) else []

    def total(*keys: str) -> float | None:
        numbers = [
            _number(item.get(key))
            for item in records
            if isinstance(item, dict)
            for key in keys
            if item.get(key) is not None
        ]
        return sum(x for x in numbers if x is not None) if numbers else None

    def goal(*keys: str) -> float | None:
        return next(
            (_number(goals.get(key)) for key in keys if _number(goals.get(key)) is not None),
            None,
        )

    return (
        (
            total("calories", "caloriesConsumed"),
            total("protein", "proteinInGrams"),
            total("carbohydrates", "carbsInGrams"),
            total("fat", "fatInGrams"),
        ),
        (
            goal("calories", "calorieGoal"),
            goal("protein", "proteinInGrams"),
            goal("carbohydrates", "carbsInGrams"),
            goal("fat", "fatInGrams"),
        ),
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None
