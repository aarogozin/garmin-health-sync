"""Privacy-safe, schema-versioned exports intended for local AI discussions."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict

from .models import BERLIN
from .renpho_report import BodySegment, Impedance, RenphoReportData
from .weekly_report import (
    ActivityDetail,
    ActivitySummary,
    BodyMeasurementPoint,
    DailyHealthMetrics,
    DailyRecovery,
    HydrationNutrition,
    SleepMetrics,
    WeeklyHealthReport,
)

SCHEMA_VERSION: Literal["garmin-health-sync/ai-context@3"] = "garmin-health-sync/ai-context@3"
MUSCLE_MAPPING_VERSION = "exercise-muscles@1"
ContextPeriod = Literal["current", "7d", "30d"]


class ExportModel(BaseModel):
    """Forbid silent schema expansion in files intended for machine consumption."""

    model_config = ConfigDict(extra="forbid")


class AvailabilityExport(ExportModel):
    status: Literal["complete", "partial"]
    available: list[str]
    unavailable: list[str]
    truncated: list[str]


class PeriodExport(ExportModel):
    kind: ContextPeriod
    start_date: date
    end_date: date
    timezone: str


class PrivacyExport(ExportModel):
    gps_included: bool = False
    locations_included: bool = False
    account_identifiers_included: bool = False
    activity_titles_included: bool = False


class MuscleInference(ExportModel):
    source: Literal["inferred"] = "inferred"
    mapping_version: str = MUSCLE_MAPPING_VERSION
    primary_muscles: list[str]
    secondary_muscles: list[str]


class ExerciseSetExport(ExportModel):
    exercise_name: str | None
    exercise_key: str | None
    category: str | None
    set_number: int | None
    reps: float | None
    weight_kg: float | None
    duration_seconds: float | None
    is_warmup: bool | None
    set_type: str | None
    rir: float | None = None
    rpe: float | None = None
    rir_status: Literal["recorded", "unavailable"] = "unavailable"
    rpe_status: Literal["recorded", "unavailable"] = "unavailable"
    muscles: MuscleInference | None


class ActivitySplitExport(ExportModel):
    split_number: int | None
    duration_seconds: float | None
    distance_km: float | None
    average_hr_bpm: float | None
    average_power_watts: float | None
    average_cadence_rpm: float | None


class HeartRateZonesExport(ExportModel):
    zone1_minutes: float
    zone2_minutes: float
    zone3_minutes: float
    zone4_minutes: float
    zone5_minutes: float
    boundaries_bpm: list[float] | None = None
    boundary_definition: str


class ActivityExport(ExportModel):
    measured_at: datetime
    activity_label: str
    activity_type: str
    training_categories: list[Literal["cardio", "strength", "mobility", "sport", "other"]]
    duration_minutes: float
    distance_km: float | None
    garmin_activity_calories_kcal: float | None
    calorie_definition: str
    average_hr_bpm: float | None
    max_hr_bpm: float | None
    aerobic_training_effect: float | None
    anaerobic_training_effect: float | None
    training_load: float | None
    heart_rate_zones: HeartRateZonesExport
    elevation_gain_m: float | None
    average_power_watts: float | None
    average_cadence_rpm: float | None
    exercise_sets_status: Literal["recorded", "partial", "not_recorded", "unavailable"]
    exercise_sets: list[ExerciseSetExport]
    splits: list[ActivitySplitExport]


class TrainingCategoryExport(ExportModel):
    sessions: int
    days: int
    duration_minutes: float
    distance_km: float
    garmin_activity_calories_kcal: float
    training_load: float


class TrainingSummaryExport(ExportModel):
    total_sessions: int
    total_duration_minutes: float
    total_distance_km: float
    total_garmin_activity_calories_kcal: float
    total_training_load: float
    moderate_intensity_minutes: int
    vigorous_intensity_minutes: int
    categories: dict[str, TrainingCategoryExport]
    unmapped_exercises: list[str]


class PressureExport(ExportModel):
    measured_at: datetime
    systolic_mmhg: int
    diastolic_mmhg: int
    pulse_bpm: int | None
    notes: str | None


class DailyPressureExport(ExportModel):
    day: date
    average_systolic_mmhg: float
    average_diastolic_mmhg: float
    readings: int


class PressureSummaryExport(ExportModel):
    readings: list[PressureExport]
    daily_averages: list[DailyPressureExport]
    period_average_systolic_mmhg: float | None
    period_average_diastolic_mmhg: float | None
    days_covered: int
    category: str
    extreme_reading_present: bool


class SegmentMetricExport(ExportModel):
    mass_kg: float | None
    percentage: float | None
    standard_kg: float | None


class BodySegmentExport(ExportModel):
    fat: SegmentMetricExport
    muscle: SegmentMetricExport


class ImpedanceExport(ExportModel):
    right_arm_ohm: float | None
    left_arm_ohm: float | None
    trunk_ohm: float | None
    right_leg_ohm: float | None
    left_leg_ohm: float | None


class BodyMeasurementExport(ExportModel):
    measured_at: datetime
    outside_period: bool
    source: str
    weight_kg: float
    bmi: float | None
    body_fat_percentage: float | None
    body_fat_mass_kg: float | None
    muscle_mass_kg: float | None
    skeletal_muscle_mass_kg: float | None
    fat_free_mass_kg: float | None
    water_mass_kg: float | None
    bone_mass_kg: float | None
    protein_mass_kg: float | None
    visceral_fat_rating: float | None
    subcutaneous_fat_percentage: float | None
    bmr_kcal: float | None
    smi_kg_m2: float | None
    metabolic_age_years: float | None
    waist_to_hip_ratio: float | None
    body_score: float | None
    segmental: dict[str, BodySegmentExport]
    impedance_20khz: ImpedanceExport | None
    impedance_100khz: ImpedanceExport | None


class MetricChangeExport(ExportModel):
    first_at: datetime
    last_at: datetime
    first_value: float
    last_value: float
    absolute_change: float
    percentage_change: float | None
    measurements: int
    source: str
    estimated: bool


class BodyDynamicsExport(ExportModel):
    weight_kg: MetricChangeExport | None
    body_fat_percentage: MetricChangeExport | None
    body_fat_mass_kg: MetricChangeExport | None
    muscle_mass_kg: MetricChangeExport | None
    bia_warning: str


class DailyHealthExport(ExportModel):
    day: date
    outside_period: bool
    steps: int | None
    distance_km: float | None
    floors: float | None
    calories_kcal: float | None
    moderate_intensity_minutes: int | None
    vigorous_intensity_minutes: int | None
    resting_hr_bpm: float | None
    minimum_hr_bpm: float | None
    maximum_hr_bpm: float | None
    stress_score: float | None
    body_battery_charged: float | None
    body_battery_drained: float | None
    training_readiness_score: float | None
    sleep_hours: float | None
    sleep_score: float | None
    deep_sleep_hours: float | None
    light_sleep_hours: float | None
    rem_sleep_hours: float | None
    awake_hours: float | None
    overnight_hrv_ms: float | None
    spo2_percentage: float | None
    respiration_breaths_min: float | None
    skin_temperature_deviation_c: float | None
    hydration_ml: float | None
    hydration_status: Literal["logged", "not_logged", "unavailable"]
    hydration_goal_ml: float | None
    nutrition_calories_kcal: float | None
    nutrition_status: Literal["logged", "not_logged", "unavailable"]
    nutrition_goal_calories_kcal: float | None
    protein_g: float | None
    carbohydrates_g: float | None
    fat_g: float | None
    protein_goal_g: float | None
    carbohydrates_goal_g: float | None
    fat_goal_g: float | None


class LifestyleExport(ExportModel):
    day: date
    name: str
    category: str
    value: float | None
    sleep_related: bool


class InsightExport(ExportModel):
    level: str
    category: str
    confidence: str
    text: str
    source_title: str | None
    source_url: str | None


class BehaviorAssociationExport(ExportModel):
    behavior: str
    metric: str
    with_days: int
    without_days: int
    median_difference: float


class ExtendedMetricExport(ExportModel):
    name: str
    summary: str


class LatestMetricExport(ExportModel):
    value: float | str | None
    unit: str | None
    measured_at: datetime | date | None
    source: str
    estimated: bool = False


class TrendWindowExport(ExportModel):
    period_days: Literal[7, 30]
    start_date: date
    end_date: date
    training: TrainingSummaryExport
    body: BodyDynamicsExport
    average_sleep_hours: float | None
    average_sleep_score: float | None
    average_stress_score: float | None
    average_resting_hr_bpm: float | None
    average_overnight_hrv_ms: float | None
    average_systolic_mmhg: float | None
    average_diastolic_mmhg: float | None
    pressure_days_covered: int


class ExerciseProgressionExport(ExportModel):
    exercise_key: str
    exercise_names: list[str]
    sessions: int
    valid_sets: int
    first_at: datetime
    last_at: datetime
    first_working_weight_kg: float | None
    latest_working_weight_kg: float | None
    best_weight_kg: float | None
    best_weight_x_reps: float | None
    best_estimated_1rm_kg: float | None
    average_working_weight_kg: float | None
    average_reps: float | None
    total_repetitions: float | None
    total_volume_kg: float | None
    trend_7d_change_pct: float | None
    trend_30d_change_pct: float | None
    estimated_1rm_change_pct: float | None
    last_performed_at: datetime
    warmup_sets_excluded: bool
    rir_status: Literal["recorded", "unavailable"]


class StrengthProgressExport(ExportModel):
    exercises_tracked: int
    exercises_with_weight_trend: int
    top_progressions: list[ExerciseProgressionExport]


class DefinitionsExport(ExportModel):
    estimated_1rm: str
    working_set: str
    missing_values: str


class EnergyBalanceExport(ExportModel):
    status: Literal["estimated", "insufficient_data"]
    logged_nutrition_days: int
    nutrition_goal_only_days: int
    average_logged_intake_kcal: float | None
    garmin_activity_calories_kcal: float
    estimated_balance_kcal: float | None
    explanation: str


class DataQualityFlagsExport(ExportModel):
    nutrition: Literal["actual_logged", "target_not_actual", "not_logged", "unavailable"]
    hydration: Literal["actual_logged", "not_logged", "unavailable"]
    body_composition: Literal["BIA_estimated", "not_available"]
    duplicate_body_measurements: bool
    activity_split_distance_anomalies: bool
    multisport_contains_strength: bool
    exercise_sets: Literal["recorded", "not_recorded", "partial", "unavailable"]
    notes: list[str]


class HealthContextSummaryExport(ExportModel):
    latest_metrics: dict[str, LatestMetricExport]
    trends_7d: TrendWindowExport
    trends_30d: TrendWindowExport
    data_quality_flags: DataQualityFlagsExport
    exercise_progression: list[ExerciseProgressionExport]
    strength_progress: StrengthProgressExport
    energy_balance: EnergyBalanceExport
    definitions: DefinitionsExport


class HealthContextRawDataExport(ExportModel):
    vo2_max: float | None
    training_status: str | None
    training_summary: TrainingSummaryExport
    activities: list[ActivityExport]
    daily_health: list[DailyHealthExport]
    blood_pressure: PressureSummaryExport
    body_measurements: list[BodyMeasurementExport]
    body_dynamics: BodyDynamicsExport
    lifestyle: list[LifestyleExport]
    behavior_associations: list[BehaviorAssociationExport]
    extended_metrics: list[ExtendedMetricExport]
    derived_insights: list[InsightExport]


class HealthContextExport(ExportModel):
    schema_version: Literal["garmin-health-sync/ai-context@3"] = SCHEMA_VERSION
    generated_at: datetime
    period: PeriodExport
    availability: AvailabilityExport
    privacy: PrivacyExport
    summary: HealthContextSummaryExport
    raw_data: HealthContextRawDataExport
    limitations: list[str]

    @property
    def vo2_max(self) -> float | None:
        return self.raw_data.vo2_max

    @property
    def training_status(self) -> str | None:
        return self.raw_data.training_status

    @property
    def training_summary(self) -> TrainingSummaryExport:
        return self.raw_data.training_summary

    @property
    def activities(self) -> list[ActivityExport]:
        return self.raw_data.activities

    @property
    def daily_health(self) -> list[DailyHealthExport]:
        return self.raw_data.daily_health

    @property
    def blood_pressure(self) -> PressureSummaryExport:
        return self.raw_data.blood_pressure

    @property
    def body_measurements(self) -> list[BodyMeasurementExport]:
        return self.raw_data.body_measurements

    @property
    def body_dynamics(self) -> BodyDynamicsExport:
        return self.raw_data.body_dynamics

    @property
    def lifestyle(self) -> list[LifestyleExport]:
        return self.raw_data.lifestyle

    @property
    def extended_metrics(self) -> list[ExtendedMetricExport]:
        return self.raw_data.extended_metrics


_CARDIO = ("run", "walk", "hike", "cycl", "swim", "row", "elliptical", "cardio")
_STRENGTH = ("strength", "weight", "gym")
_MOBILITY = ("yoga", "pilates", "stretch", "mobility")
_SPORT = ("football", "soccer", "basketball", "tennis", "badminton", "golf", "boxing")

_MUSCLES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "squat": (("quadriceps", "gluteals"), ("hamstrings", "core")),
    "deadlift": (("hamstrings", "gluteals", "back"), ("quadriceps", "forearms", "core")),
    "bench press": (("chest", "triceps"), ("front deltoids",)),
    "push up": (("chest", "triceps"), ("front deltoids", "core")),
    "pull up": (("latissimus dorsi", "biceps"), ("upper back", "forearms")),
    "row": (("upper back", "latissimus dorsi"), ("biceps", "rear deltoids")),
    "shoulder press": (("deltoids", "triceps"), ("upper chest", "core")),
    "overhead press": (("deltoids", "triceps"), ("upper chest", "core")),
    "biceps curl": (("biceps",), ("forearms",)),
    "triceps extension": (("triceps",), ()),
    "lunge": (("quadriceps", "gluteals"), ("hamstrings", "calves", "core")),
    "leg press": (("quadriceps", "gluteals"), ("hamstrings",)),
    "calf raise": (("calves",), ()),
    "lat pulldown": (("latissimus dorsi",), ("biceps", "upper back")),
    "plank": (("core",), ("shoulders", "gluteals")),
}

_EXERCISE_ALIASES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("deadlift",), "deadlift"),
    (("bench", "press"), "bench_press"),
    (("squat",), "squat"),
    (("overhead", "press"), "overhead_press"),
    (("shoulder", "press"), "shoulder_press"),
    (("lat", "pulldown"), "lat_pulldown"),
    (("pull", "up"), "pull_up"),
    (("push", "up"), "push_up"),
    (("biceps", "curl"), "biceps_curl"),
    (("triceps", "extension"), "triceps_extension"),
    (("leg", "press"), "leg_press"),
    (("calf", "raise"), "calf_raise"),
    (("lunge",), "lunge"),
    (("plank",), "plank"),
    (("row",), "row"),
)


def build_health_context(report: WeeklyHealthReport, period: ContextPeriod) -> HealthContextExport:
    """Project the normalized report into a privacy-safe, deterministic AI contract."""
    end = report.end_date
    start = {
        "current": end,
        "7d": end - timedelta(days=6),
        "30d": end - timedelta(days=29),
    }[period]

    def in_period(timestamp: datetime) -> bool:
        return start <= timestamp.astimezone(BERLIN).date() <= end

    details = {item.activity_id: item for item in report.comprehensive.activity_details}
    all_activities = [
        _activity(item, details.get(item.activity_id or "")) for item in report.activities
    ]
    activities = [item for item in all_activities if in_period(item.measured_at)]
    all_body = [_body(item, False) for item in report.body]
    body_in_period = [item for item in report.body if in_period(item.measured_at)]
    body_points = list(body_in_period)
    if period == "current" and not body_points and report.body:
        body_points.append(max(report.body, key=lambda item: item.measured_at))
    body = [_body(item, not in_period(item.measured_at)) for item in body_points]
    pressure = [item for item in report.pressure.readings if in_period(item.measured_at)]
    daily_pressure = [item for item in report.pressure.daily_averages if start <= item.day <= end]
    recovery = {item.day: item for item in report.recovery}
    health = {item.day: item for item in report.comprehensive.daily_health}
    sleep = {item.day: item for item in report.comprehensive.sleep}
    nutrition = {item.day: item for item in report.comprehensive.hydration_nutrition}
    all_days = sorted(set(recovery) | set(health) | set(sleep) | set(nutrition))
    daily_all = [
        _daily(
            day,
            recovery.get(day),
            health.get(day),
            sleep.get(day),
            nutrition.get(day),
            not (start <= day <= end),
        )
        for day in all_days
    ]
    daily_health = [item for item in daily_all if start <= item.day <= end]
    if period == "current":
        prior = [item for item in daily_all if item.day < start and _has_daily_values(item)]
        if prior:
            daily_health.insert(0, prior[-1])
    summary_recovery = {day: item for day, item in recovery.items() if start <= day <= end}
    pressure_export = PressureSummaryExport(
        readings=[
            PressureExport(
                measured_at=x.measured_at,
                systolic_mmhg=x.systolic,
                diastolic_mmhg=x.diastolic,
                pulse_bpm=x.pulse,
                notes=x.notes,
            )
            for x in pressure
        ],
        daily_averages=[
            DailyPressureExport(
                day=x.day,
                average_systolic_mmhg=x.systolic,
                average_diastolic_mmhg=x.diastolic,
                readings=x.count,
            )
            for x in daily_pressure
        ],
        period_average_systolic_mmhg=_mean([float(x.systolic) for x in pressure]),
        period_average_diastolic_mmhg=_mean([float(x.diastolic) for x in pressure]),
        days_covered=len({x.measured_at.astimezone(BERLIN).date() for x in pressure}),
        category=report.pressure.esc_category,
        extreme_reading_present=any(x.systolic > 180 or x.diastolic > 120 for x in pressure),
    )
    training_summary = _training_summary(activities, summary_recovery)
    body_dynamics = _body_dynamics(body)
    raw_data = HealthContextRawDataExport(
        vo2_max=report.vo2_max,
        training_status=report.training_status,
        training_summary=training_summary,
        activities=activities,
        daily_health=daily_health,
        blood_pressure=pressure_export,
        body_measurements=body,
        body_dynamics=body_dynamics,
        lifestyle=[
            LifestyleExport(
                day=x.day,
                name=x.name,
                category=x.category,
                value=x.value,
                sleep_related=x.sleep_related,
            )
            for x in report.comprehensive.lifestyle
            if start <= x.day <= end
        ],
        behavior_associations=[
            BehaviorAssociationExport(
                behavior=x.behavior,
                metric=x.metric,
                with_days=x.with_days,
                without_days=x.without_days,
                median_difference=x.median_difference,
            )
            for x in report.comprehensive.associations
        ],
        extended_metrics=[
            ExtendedMetricExport(name=x.name, summary=x.summary)
            for x in report.comprehensive.extended
        ],
        derived_insights=[
            InsightExport(
                level=x.level,
                category=x.category,
                confidence=x.confidence,
                text=x.text,
                source_title=x.source_title,
                source_url=x.source_url,
            )
            for x in (report.insights if period != "current" else ())
        ],
    )
    return HealthContextExport(
        generated_at=report.generated_at,
        period=PeriodExport(kind=period, start_date=start, end_date=end, timezone="Europe/Berlin"),
        availability=AvailabilityExport(
            status="partial" if report.availability.unavailable else "complete",
            available=list(report.availability.available),
            unavailable=list(report.availability.unavailable),
            truncated=list(report.comprehensive.truncated),
        ),
        privacy=PrivacyExport(),
        summary=_context_summary(
            report,
            all_activities,
            all_body,
            daily_all,
        ),
        raw_data=raw_data,
        limitations=[
            "This export is for personal context, not diagnosis or medical advice.",
            "Consumer wearables can have missing or estimated values.",
            "BIA body-composition changes are sensitive to hydration, meals, exercise and measurement timing.",
            "Muscle targets are conservative local inferences from recognized exercise names, not Garmin measurements.",
        ],
    )


def render_context_json(context: HealthContextExport) -> str:
    """Return stable, indented JSON with explicit null values and UTF-8 text."""
    return context.model_dump_json(indent=2, exclude_none=False) + "\n"


def render_context_markdown(context: HealthContextExport) -> str:
    """Render a human-readable view exclusively from the canonical export model."""
    period = context.period
    lines = [
        "---",
        f'schema_version: "{context.schema_version}"',
        f'period: "{period.kind}"',
        f'start_date: "{period.start_date}"',
        f'end_date: "{period.end_date}"',
        f'generated_at: "{context.generated_at.isoformat()}"',
        f'completeness: "{context.availability.status}"',
        "---",
        "",
        f"# AI health context — {period.start_date} to {period.end_date}",
        "",
        "> Personal monitoring context only. This is not medical advice or a diagnosis.",
        "",
        "## Summary",
        "",
        f"- Activities: **{context.training_summary.total_sessions}**",
        f"- Training duration: **{context.training_summary.total_duration_minutes:.0f} min**",
        f"- Blood-pressure days: **{context.blood_pressure.days_covered}**",
        f"- Body measurements: **{len(context.body_measurements)}**",
        f"- VO₂ max: **{_display(context.vo2_max)}**",
        "",
        "## Data quality flags",
        "",
        f"- Nutrition: **{context.summary.data_quality_flags.nutrition}**",
        f"- Hydration: **{context.summary.data_quality_flags.hydration}**",
        f"- Body composition: **{context.summary.data_quality_flags.body_composition}**",
        f"- Duplicate body measurements: **{context.summary.data_quality_flags.duplicate_body_measurements}**",
        f"- Split distance anomalies: **{context.summary.data_quality_flags.activity_split_distance_anomalies}**",
        f"- Multisport contains strength: **{context.summary.data_quality_flags.multisport_contains_strength}**",
        f"- Exercise sets: **{context.summary.data_quality_flags.exercise_sets}**",
        "",
        "## 7- and 30-day trends",
        "",
    ]
    lines.extend(
        _table(
            ["Window", "Activities", "Training", "Sleep", "Stress", "Resting HR", "Weight change"],
            [
                [
                    f"{trend.period_days} days",
                    trend.training.total_sessions,
                    f"{trend.training.total_duration_minutes:.0f} min",
                    _display(trend.average_sleep_hours, " h"),
                    _display(trend.average_stress_score),
                    _display(trend.average_resting_hr_bpm, " bpm"),
                    _display_change(trend.body.weight_kg),
                ]
                for trend in (context.summary.trends_7d, context.summary.trends_30d)
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Exercise progression",
            "",
        ]
    )
    lines.extend(
        _table(
            [
                "Exercise",
                "Sessions",
                "Valid sets",
                "First working",
                "Latest working",
                "Best 1RM",
                "Total reps",
                "Volume",
                "RIR",
            ],
            [
                [
                    item.exercise_key,
                    item.sessions,
                    item.valid_sets,
                    _display(item.first_working_weight_kg, " kg"),
                    _display(item.latest_working_weight_kg, " kg"),
                    _display(item.best_estimated_1rm_kg, " kg"),
                    _display(item.total_repetitions),
                    _display(item.total_volume_kg, " kg"),
                    item.rir_status,
                ]
                for item in context.summary.exercise_progression
            ],
        )
    )
    lines.extend(
        [
            "",
            "## Energy balance",
            "",
            f"- Status: **{context.summary.energy_balance.status}**",
            f"- Logged nutrition days: **{context.summary.energy_balance.logged_nutrition_days}**",
            f"- Goal-only days: **{context.summary.energy_balance.nutrition_goal_only_days}**",
            f"- Garmin activity calories: **{context.summary.energy_balance.garmin_activity_calories_kcal:.0f} kcal**",
            f"- {context.summary.energy_balance.explanation}",
            "",
            "## Body dynamics",
            "",
        ]
    )
    for label, change in (
        ("Weight", context.body_dynamics.weight_kg),
        ("Body fat", context.body_dynamics.body_fat_percentage),
        ("Estimated fat mass", context.body_dynamics.body_fat_mass_kg),
        ("Muscle mass", context.body_dynamics.muscle_mass_kg),
    ):
        lines.append(f"- **{label}:** {_display_change(change)}")
    lines.extend(["", f"> {context.body_dynamics.bia_warning}", "", "## Activities", ""])
    lines.extend(
        _table(
            [
                "Time",
                "Activity",
                "Type",
                "Categories",
                "Duration",
                "Distance",
                "Garmin activity calories",
            ],
            [
                [
                    x.measured_at.isoformat(),
                    x.activity_label,
                    x.activity_type,
                    ", ".join(x.training_categories),
                    f"{x.duration_minutes:.1f} min",
                    _display(x.distance_km, " km"),
                    _display(x.garmin_activity_calories_kcal, " kcal"),
                ]
                for x in context.activities
            ],
        )
    )
    for activity in context.activities:
        if not activity.exercise_sets:
            continue
        lines.extend(["", f"### {_escape(activity.activity_label)} — exercise sets", ""])
        lines.extend(
            _table(
                ["Exercise", "Key", "Set", "Reps", "Weight", "Warm-up", "RIR", "RPE"],
                [
                    [
                        x.exercise_name or "Not available",
                        x.exercise_key or "Not available",
                        _display(x.set_number),
                        _display(x.reps),
                        _display(x.weight_kg, " kg"),
                        _display(x.is_warmup),
                        _display(x.rir),
                        _display(x.rpe),
                    ]
                    for x in activity.exercise_sets
                ],
            )
        )
    lines.extend(["", "## Daily health", ""])
    lines.extend(
        _table(
            [
                "Day",
                "Steps",
                "Sleep",
                "Score",
                "Stress",
                "Resting HR",
                "HRV",
                "Body Battery +/−",
                "Baseline",
            ],
            [
                [
                    x.day,
                    _display(x.steps),
                    _display(x.sleep_hours, " h"),
                    _display(x.sleep_score),
                    _display(x.stress_score),
                    _display(x.resting_hr_bpm, " bpm"),
                    _display(x.overnight_hrv_ms, " ms"),
                    f"{_display(x.body_battery_charged)} / {_display(x.body_battery_drained)}",
                    "outside period" if x.outside_period else "in period",
                ]
                for x in context.daily_health
            ],
        )
    )
    lines.extend(["", "## Blood pressure", ""])
    lines.extend(
        _table(
            ["Time", "Systolic", "Diastolic", "Pulse", "Notes"],
            [
                [
                    x.measured_at.isoformat(),
                    f"{x.systolic_mmhg} mmHg",
                    f"{x.diastolic_mmhg} mmHg",
                    _display(x.pulse_bpm, " bpm"),
                    x.notes or "",
                ]
                for x in context.blood_pressure.readings
            ],
        )
    )
    lines.extend(["", "## Body measurements", ""])
    lines.extend(
        _table(
            ["Time", "Source", "Weight", "Body fat", "Fat mass", "Muscle", "BMI", "Baseline"],
            [
                [
                    x.measured_at.isoformat(),
                    x.source,
                    f"{x.weight_kg:.2f} kg",
                    _display(x.body_fat_percentage, "%"),
                    _display(x.body_fat_mass_kg, " kg"),
                    _display(x.muscle_mass_kg, " kg"),
                    _display(x.bmi),
                    "outside period" if x.outside_period else "in period",
                ]
                for x in context.body_measurements
            ],
        )
    )
    lines.extend(["", "## Lifestyle context", ""])
    lines.extend(
        _table(
            ["Day", "Category", "Event", "Value"],
            [[x.day, x.category, x.name, _display(x.value)] for x in context.lifestyle],
        )
    )
    lines.extend(["", "## Extended Garmin metrics", ""])
    lines.extend(
        _table(["Domain", "Availability"], [[x.name, x.summary] for x in context.extended_metrics])
    )
    lines.extend(
        [
            "",
            "## Data availability",
            "",
            f"- Available: {', '.join(context.availability.available) or 'None'}",
            f"- Unavailable: {', '.join(context.availability.unavailable) or 'None'}",
            f"- Truncated: {', '.join(context.availability.truncated) or 'None'}",
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {_escape(item)}" for item in context.limitations)
    return "\n".join(lines).rstrip() + "\n"


def _activity(item: ActivitySummary, detail: ActivityDetail | None) -> ActivityExport:
    categories = _training_categories(
        item.activity_type,
        detail.component_types if detail else (),
        bool(detail and detail.exercises),
    )
    zones = list(item.hr_zone_minutes[:5])
    zones.extend([0.0] * (5 - len(zones)))
    exercises = list(detail.exercises if detail else ())
    exercise_status: Literal["recorded", "partial", "not_recorded", "unavailable"]
    if detail is None or not detail.exercise_sets_available:
        exercise_status = "unavailable"
    elif not exercises:
        exercise_status = "not_recorded"
    elif any(
        exercise.exercise_name is None
        or all(
            value is None
            for value in (
                exercise.repetitions,
                exercise.weight_kg,
                exercise.duration_seconds,
            )
        )
        for exercise in exercises
    ):
        exercise_status = "partial"
    else:
        exercise_status = "recorded"
    return ActivityExport(
        measured_at=item.measured_at,
        activity_label=_activity_label(item.activity_type),
        activity_type=item.activity_type,
        training_categories=categories,
        duration_minutes=item.duration_minutes,
        distance_km=item.distance_km,
        garmin_activity_calories_kcal=item.calories,
        calorie_definition="Garmin activity-summary calories; device semantics may include estimated resting energy depending on activity and device.",
        average_hr_bpm=item.average_hr,
        max_hr_bpm=item.max_hr,
        aerobic_training_effect=item.aerobic_effect,
        anaerobic_training_effect=item.anaerobic_effect,
        training_load=item.training_load,
        heart_rate_zones=HeartRateZonesExport(
            zone1_minutes=zones[0],
            zone2_minutes=zones[1],
            zone3_minutes=zones[2],
            zone4_minutes=zones[3],
            zone5_minutes=zones[4],
            boundaries_bpm=None,
            boundary_definition="Garmin zone time is preserved, but personal BPM boundaries were not available in this collection.",
        ),
        elevation_gain_m=detail.elevation_gain if detail else None,
        average_power_watts=detail.average_power if detail else None,
        average_cadence_rpm=detail.average_cadence if detail else None,
        exercise_sets_status=exercise_status,
        exercise_sets=[
            ExerciseSetExport(
                exercise_name=x.exercise_name,
                exercise_key=_exercise_key(x.exercise_name or x.category),
                category=x.category,
                set_number=x.set_number,
                reps=x.repetitions,
                weight_kg=x.weight_kg,
                duration_seconds=x.duration_seconds,
                is_warmup=x.is_warmup,
                set_type=x.set_type,
                rir=x.rir,
                rpe=x.rpe,
                rir_status="recorded" if x.rir is not None else "unavailable",
                rpe_status="recorded" if x.rpe is not None else "unavailable",
                muscles=_infer_muscles(x.exercise_name) if x.exercise_name else None,
            )
            for x in exercises
        ],
        splits=[
            ActivitySplitExport(
                split_number=x.split_number,
                duration_seconds=x.duration_seconds,
                distance_km=x.distance_km,
                average_hr_bpm=x.average_hr,
                average_power_watts=x.average_power,
                average_cadence_rpm=x.average_cadence,
            )
            for x in (detail.splits if detail else ())
        ],
    )


def _training_category(value: str) -> Literal["cardio", "strength", "mobility", "sport", "other"]:
    normalized = value.lower()
    for category, needles in (
        ("strength", _STRENGTH),
        ("mobility", _MOBILITY),
        ("sport", _SPORT),
        ("cardio", _CARDIO),
    ):
        if any(needle in normalized for needle in needles):
            return cast(Literal["cardio", "strength", "mobility", "sport", "other"], category)
    return "other"


def _training_categories(
    activity_type: str, component_types: tuple[str, ...], has_exercises: bool
) -> list[Literal["cardio", "strength", "mobility", "sport", "other"]]:
    """Classify a multisport session from its typed component splits."""
    categories = [_training_category(value) for value in (activity_type, *component_types)]
    if has_exercises:
        categories.append("strength")
    unique = [item for item in dict.fromkeys(categories) if item != "other"]
    return cast(
        list[Literal["cardio", "strength", "mobility", "sport", "other"]],
        unique or ["other"],
    )


def _activity_label(activity_type: str) -> str:
    """Return a location-free label instead of the user supplied Garmin title."""
    return activity_type.replace("_", " ").replace("-", " ").title() or "Activity"


def _training_summary(
    activities: list[ActivityExport], recovery: Mapping[date, DailyRecovery]
) -> TrainingSummaryExport:
    categories: dict[str, TrainingCategoryExport] = {}
    for category in ("cardio", "strength", "mobility", "sport", "other"):
        items = [x for x in activities if category in x.training_categories]
        categories[category] = TrainingCategoryExport(
            sessions=len(items),
            days=len({x.measured_at.astimezone(BERLIN).date() for x in items}),
            duration_minutes=sum(x.duration_minutes for x in items),
            distance_km=sum(x.distance_km or 0 for x in items),
            garmin_activity_calories_kcal=sum(x.garmin_activity_calories_kcal or 0 for x in items),
            training_load=sum(x.training_load or 0 for x in items),
        )
    unknown = sorted(
        {
            x.exercise_name or x.exercise_key or "unknown"
            for a in activities
            for x in a.exercise_sets
            if x.muscles is None
        }
    )
    return TrainingSummaryExport(
        total_sessions=len(activities),
        total_duration_minutes=sum(x.duration_minutes for x in activities),
        total_distance_km=sum(x.distance_km or 0 for x in activities),
        total_garmin_activity_calories_kcal=sum(
            x.garmin_activity_calories_kcal or 0 for x in activities
        ),
        total_training_load=sum(x.training_load or 0 for x in activities),
        moderate_intensity_minutes=sum(
            int(getattr(x, "moderate_minutes", 0) or 0) for x in recovery.values()
        ),
        vigorous_intensity_minutes=sum(
            int(getattr(x, "vigorous_minutes", 0) or 0) for x in recovery.values()
        ),
        categories=categories,
        unmapped_exercises=unknown,
    )


def _context_summary(
    report: WeeklyHealthReport,
    activities: list[ActivityExport],
    body: list[BodyMeasurementExport],
    daily: list[DailyHealthExport],
) -> HealthContextSummaryExport:
    """Build compact model-ready context without discarding the raw timeline."""
    latest_body = max(body, key=lambda item: item.measured_at) if body else None
    latest_daily = max(daily, key=lambda item: item.day) if daily else None
    latest: dict[str, LatestMetricExport] = {}

    def add(
        name: str,
        value: float | str | None,
        unit: str | None,
        measured_at: datetime | date | None,
        source: str,
        *,
        estimated: bool = False,
    ) -> None:
        latest[name] = LatestMetricExport(
            value=value,
            unit=unit,
            measured_at=measured_at,
            source=source,
            estimated=estimated,
        )

    if latest_body:
        add("weight", latest_body.weight_kg, "kg", latest_body.measured_at, latest_body.source)
        add(
            "body_fat",
            latest_body.body_fat_percentage,
            "%",
            latest_body.measured_at,
            latest_body.source,
            estimated=True,
        )
        add(
            "muscle_mass",
            latest_body.muscle_mass_kg,
            "kg",
            latest_body.measured_at,
            latest_body.source,
            estimated=True,
        )
        add(
            "skeletal_muscle_mass",
            latest_body.skeletal_muscle_mass_kg,
            "kg",
            latest_body.measured_at,
            latest_body.source,
            estimated=True,
        )
        add(
            "fat_free_mass",
            latest_body.fat_free_mass_kg,
            "kg",
            latest_body.measured_at,
            latest_body.source,
            estimated=True,
        )
        add(
            "water_mass",
            latest_body.water_mass_kg,
            "kg",
            latest_body.measured_at,
            latest_body.source,
            estimated=True,
        )
    if latest_daily:
        for name, value, unit in (
            ("sleep", latest_daily.sleep_hours, "h"),
            ("sleep_score", latest_daily.sleep_score, "score"),
            ("stress", latest_daily.stress_score, "score"),
            ("resting_hr", latest_daily.resting_hr_bpm, "bpm"),
            ("overnight_hrv", latest_daily.overnight_hrv_ms, "ms"),
            ("steps", latest_daily.steps, "steps"),
        ):
            add(name, value, unit, latest_daily.day, "Garmin")
    add("vo2_max", report.vo2_max, "mL/kg/min", report.end_date, "Garmin", estimated=True)

    quality = _data_quality(activities, body, daily)
    progression = _exercise_progression(activities, report.end_date)
    top_progressions = sorted(
        [
            item
            for item in progression
            if item.sessions >= 2
            and (
                item.estimated_1rm_change_pct is not None
                or _percentage_change(item.first_working_weight_kg, item.latest_working_weight_kg)
                is not None
            )
        ],
        key=lambda item: abs(
            item.estimated_1rm_change_pct
            if item.estimated_1rm_change_pct is not None
            else _percentage_change(item.first_working_weight_kg, item.latest_working_weight_kg)
            or 0
        ),
        reverse=True,
    )[:5]
    return HealthContextSummaryExport(
        latest_metrics=latest,
        trends_7d=_trend_window(report, activities, body, daily, 7),
        trends_30d=_trend_window(report, activities, body, daily, 30),
        data_quality_flags=quality,
        exercise_progression=progression,
        strength_progress=StrengthProgressExport(
            exercises_tracked=len(progression),
            exercises_with_weight_trend=sum(
                item.first_working_weight_kg is not None
                and item.latest_working_weight_kg is not None
                and item.sessions >= 2
                for item in progression
            ),
            top_progressions=top_progressions,
        ),
        energy_balance=_energy_balance(activities, daily),
        definitions=DefinitionsExport(
            estimated_1rm="Epley formula: weight_kg × (1 + reps / 30). Calculated only for recorded working sets with positive weight and 1–30 reps.",
            working_set="A recorded set not explicitly marked as warm-up. Sets with unknown warm-up status are included and remain identifiable in raw_data.",
            missing_values="null means the provider did not supply the value. Missing values are never converted to zero or inferred from heart rate or activity duration.",
        ),
    )


def _trend_window(
    report: WeeklyHealthReport,
    activities: list[ActivityExport],
    body: list[BodyMeasurementExport],
    daily: list[DailyHealthExport],
    days: Literal[7, 30],
) -> TrendWindowExport:
    start = report.end_date - timedelta(days=days - 1)
    selected_activities = [
        item
        for item in activities
        if start <= item.measured_at.astimezone(BERLIN).date() <= report.end_date
    ]
    selected_body = [
        item
        for item in body
        if start <= item.measured_at.astimezone(BERLIN).date() <= report.end_date
    ]
    selected_daily = [item for item in daily if start <= item.day <= report.end_date]
    selected_recovery = {
        item.day: item for item in report.recovery if start <= item.day <= report.end_date
    }
    pressure = [
        item
        for item in report.pressure.readings
        if start <= item.measured_at.astimezone(BERLIN).date() <= report.end_date
    ]
    return TrendWindowExport(
        period_days=days,
        start_date=start,
        end_date=report.end_date,
        training=_training_summary(selected_activities, selected_recovery),
        body=_body_dynamics(selected_body),
        average_sleep_hours=_average_attr(selected_daily, "sleep_hours"),
        average_sleep_score=_average_attr(selected_daily, "sleep_score"),
        average_stress_score=_average_attr(selected_daily, "stress_score"),
        average_resting_hr_bpm=_average_attr(selected_daily, "resting_hr_bpm"),
        average_overnight_hrv_ms=_average_attr(selected_daily, "overnight_hrv_ms"),
        average_systolic_mmhg=_mean([float(item.systolic) for item in pressure]),
        average_diastolic_mmhg=_mean([float(item.diastolic) for item in pressure]),
        pressure_days_covered=len(
            {item.measured_at.astimezone(BERLIN).date() for item in pressure}
        ),
    )


def _data_quality(
    activities: list[ActivityExport],
    body: list[BodyMeasurementExport],
    daily: list[DailyHealthExport],
) -> DataQualityFlagsExport:
    nutrition_statuses = {item.nutrition_status for item in daily}
    hydration_statuses = {item.hydration_status for item in daily}
    duplicate_body = any(
        abs((left.measured_at - right.measured_at).total_seconds()) <= 120
        and abs(left.weight_kg - right.weight_kg) <= 0.05
        for index, left in enumerate(body)
        for right in body[index + 1 :]
    )
    split_anomaly = any(
        split.distance_km is not None
        and (
            split.distance_km < 0
            or (activity.distance_km is not None and split.distance_km > activity.distance_km + 0.1)
        )
        for activity in activities
        for split in activity.splits
    )
    set_statuses = {
        item.exercise_sets_status for item in activities if "strength" in item.training_categories
    }
    exercise_sets: Literal["recorded", "not_recorded", "partial", "unavailable"]
    if not set_statuses or set_statuses == {"unavailable"}:
        exercise_sets = "unavailable"
    elif set_statuses == {"recorded"}:
        exercise_sets = "recorded"
    elif set_statuses <= {"not_recorded"}:
        exercise_sets = "not_recorded"
    else:
        exercise_sets = "partial"
    nutrition: Literal["actual_logged", "target_not_actual", "not_logged", "unavailable"]
    if "logged" in nutrition_statuses:
        nutrition = "actual_logged"
    elif any(item.nutrition_goal_calories_kcal is not None for item in daily):
        nutrition = "target_not_actual"
    elif "not_logged" in nutrition_statuses:
        nutrition = "not_logged"
    else:
        nutrition = "unavailable"
    hydration: Literal["actual_logged", "not_logged", "unavailable"]
    if "logged" in hydration_statuses:
        hydration = "actual_logged"
    elif "not_logged" in hydration_statuses:
        hydration = "not_logged"
    else:
        hydration = "unavailable"
    notes = [
        "Body-composition values are BIA estimates and can move with water and glycogen.",
        "A missing RIR value means Garmin did not provide it; it is not equivalent to zero.",
    ]
    return DataQualityFlagsExport(
        nutrition=nutrition,
        hydration=hydration,
        body_composition="BIA_estimated"
        if any("RENPHO" in item.source for item in body)
        else "not_available",
        duplicate_body_measurements=duplicate_body,
        activity_split_distance_anomalies=split_anomaly,
        multisport_contains_strength=any(
            "multi" in item.activity_type.lower() and "strength" in item.training_categories
            for item in activities
        ),
        exercise_sets=exercise_sets,
        notes=notes,
    )


def _exercise_progression(
    activities: list[ActivityExport], as_of: date
) -> list[ExerciseProgressionExport]:
    by_exercise: dict[str, list[tuple[datetime, ExerciseSetExport]]] = {}
    for activity in activities:
        for item in activity.exercise_sets:
            if item.exercise_key and item.is_warmup is not True:
                by_exercise.setdefault(item.exercise_key, []).append((activity.measured_at, item))
    result: list[ExerciseProgressionExport] = []
    for exercise_key, records in sorted(by_exercise.items()):
        records.sort(key=lambda item: item[0])
        first_at, last_at = records[0][0], records[-1][0]
        first_weights = [
            item.weight_kg for at, item in records if at == first_at and item.weight_kg is not None
        ]
        last_weights = [
            item.weight_kg for at, item in records if at == last_at and item.weight_kg is not None
        ]
        weights = [item.weight_kg for _, item in records if item.weight_kg is not None]
        repetitions = [item.reps for _, item in records if item.reps is not None]
        volume = [
            item.weight_kg * item.reps
            for _, item in records
            if item.weight_kg is not None and item.reps is not None
        ]
        estimated_1rm = [
            value
            for _, item in records
            if (value := _estimated_1rm(item.weight_kg, item.reps)) is not None
        ]
        first_1rm = [
            value
            for at, item in records
            if at == first_at and (value := _estimated_1rm(item.weight_kg, item.reps)) is not None
        ]
        last_1rm = [
            value
            for at, item in records
            if at == last_at and (value := _estimated_1rm(item.weight_kg, item.reps)) is not None
        ]
        valid_sets = [
            item
            for _, item in records
            if any(
                value is not None for value in (item.weight_kg, item.reps, item.duration_seconds)
            )
        ]
        result.append(
            ExerciseProgressionExport(
                exercise_key=exercise_key,
                exercise_names=sorted(
                    {item.exercise_name for _, item in records if item.exercise_name}
                ),
                sessions=len({at for at, _ in records}),
                valid_sets=len(valid_sets),
                first_at=first_at,
                last_at=last_at,
                first_working_weight_kg=max(first_weights) if first_weights else None,
                latest_working_weight_kg=max(last_weights) if last_weights else None,
                best_weight_kg=max(weights) if weights else None,
                best_weight_x_reps=max(volume) if volume else None,
                best_estimated_1rm_kg=max(estimated_1rm) if estimated_1rm else None,
                average_working_weight_kg=_mean([float(value) for value in weights]),
                average_reps=_mean([float(value) for value in repetitions]),
                total_repetitions=sum(repetitions) if repetitions else None,
                total_volume_kg=sum(volume) if volume else None,
                trend_7d_change_pct=_exercise_weight_trend(records, as_of, 7),
                trend_30d_change_pct=_exercise_weight_trend(records, as_of, 30),
                estimated_1rm_change_pct=_percentage_change(
                    max(first_1rm) if first_1rm else None,
                    max(last_1rm) if last_1rm else None,
                ),
                last_performed_at=last_at,
                warmup_sets_excluded=any(
                    item.is_warmup is True
                    for activity in activities
                    for item in activity.exercise_sets
                    if item.exercise_key == exercise_key
                ),
                rir_status="recorded"
                if any(item.rir is not None for _, item in records)
                else "unavailable",
            )
        )
    return result


def _exercise_key(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    tokens = set(normalized.split())
    for needles, key in _EXERCISE_ALIASES:
        if set(needles) <= tokens:
            return key
    return normalized.replace(" ", "_") or None


def _estimated_1rm(weight_kg: float | None, reps: float | None) -> float | None:
    if weight_kg is None or reps is None or weight_kg <= 0 or not 1 <= reps <= 30:
        return None
    return weight_kg * (1 + reps / 30)


def _percentage_change(first: float | None, last: float | None) -> float | None:
    if first is None or last is None or first == 0:
        return None
    return (last - first) / first * 100


def _exercise_weight_trend(
    records: list[tuple[datetime, ExerciseSetExport]], end: date, days: int
) -> float | None:
    start = end - timedelta(days=days - 1)
    selected = [
        (at, item)
        for at, item in records
        if start <= at.astimezone(BERLIN).date() <= end and item.weight_kg is not None
    ]
    if not selected:
        return None
    first_at, last_at = selected[0][0], selected[-1][0]
    first = max(
        item.weight_kg for at, item in selected if at == first_at and item.weight_kg is not None
    )
    last = max(
        item.weight_kg for at, item in selected if at == last_at and item.weight_kg is not None
    )
    return _percentage_change(first, last) if first_at != last_at else None


def _energy_balance(
    activities: list[ActivityExport], daily: list[DailyHealthExport]
) -> EnergyBalanceExport:
    intake = [
        item.nutrition_calories_kcal for item in daily if item.nutrition_calories_kcal is not None
    ]
    goal_only = sum(
        item.nutrition_calories_kcal is None and item.nutrition_goal_calories_kcal is not None
        for item in daily
    )
    activity_calories = sum(item.garmin_activity_calories_kcal or 0 for item in activities)
    return EnergyBalanceExport(
        status="insufficient_data",
        logged_nutrition_days=len(intake),
        nutrition_goal_only_days=goal_only,
        average_logged_intake_kcal=_mean([float(value) for value in intake]),
        garmin_activity_calories_kcal=activity_calories,
        estimated_balance_kcal=None,
        explanation="Energy balance is not calculated without reliable logged intake and compatible total expenditure data.",
    )


def _average_attr(items: list[DailyHealthExport], name: str) -> float | None:
    values = [getattr(item, name) for item in items if getattr(item, name) is not None]
    return _mean([float(value) for value in values])


def _body(item: BodyMeasurementPoint, outside: bool) -> BodyMeasurementExport:
    report = item.report
    return BodyMeasurementExport(
        measured_at=item.measured_at,
        outside_period=outside,
        source=item.source,
        weight_kg=item.weight_kg,
        bmi=_rv(report, "bmi"),
        body_fat_percentage=item.body_fat_pct,
        body_fat_mass_kg=_rv(report, "body_fat_mass")
        or (item.weight_kg * item.body_fat_pct / 100 if item.body_fat_pct is not None else None),
        muscle_mass_kg=_rv(report, "muscle_mass") if report else item.muscle_mass_kg,
        skeletal_muscle_mass_kg=_rv(report, "skeletal_muscle_mass"),
        fat_free_mass_kg=report.fat_free_mass if report else None,
        water_mass_kg=_rv(report, "water_mass"),
        bone_mass_kg=_rv(report, "bone_mass"),
        protein_mass_kg=_rv(report, "protein_mass"),
        visceral_fat_rating=report.visceral_fat if report else None,
        subcutaneous_fat_percentage=report.subcutaneous_fat if report else None,
        bmr_kcal=report.bmr if report else None,
        smi_kg_m2=report.smi if report else None,
        metabolic_age_years=report.metabolic_age if report else None,
        waist_to_hip_ratio=report.whr if report else None,
        body_score=report.body_score if report else None,
        segmental=_segments(report),
        impedance_20khz=_impedance(report.impedance_20khz) if report else None,
        impedance_100khz=_impedance(report.impedance_100khz) if report else None,
    )


def _body_dynamics(items: list[BodyMeasurementExport]) -> BodyDynamicsExport:
    in_period = [x for x in items if not x.outside_period]
    composition = [x for x in in_period if "RENPHO" in x.source]
    return BodyDynamicsExport(
        weight_kg=_metric_change(in_period, "weight_kg", False),
        body_fat_percentage=_metric_change(composition, "body_fat_percentage", True),
        body_fat_mass_kg=_metric_change(composition, "body_fat_mass_kg", True),
        muscle_mass_kg=_metric_change(composition, "muscle_mass_kg", True),
        bia_warning="BIA-derived fat and muscle changes are estimates and should be compared under similar measurement conditions.",
    )


def _metric_change(
    items: list[BodyMeasurementExport], field: str, estimated: bool
) -> MetricChangeExport | None:
    values = [(x, getattr(x, field)) for x in items if getattr(x, field) is not None]
    if len(values) < 2:
        return None
    first_item, first = values[0]
    last_item, last = values[-1]
    if not isinstance(first, float) or not isinstance(last, float):
        return None
    return MetricChangeExport(
        first_at=first_item.measured_at,
        last_at=last_item.measured_at,
        first_value=first,
        last_value=last,
        absolute_change=last - first,
        percentage_change=((last - first) / first * 100 if first else None),
        measurements=len(values),
        source=first_item.source,
        estimated=estimated,
    )


def _daily(
    day: date,
    recovery: DailyRecovery | None,
    health: DailyHealthMetrics | None,
    sleep: SleepMetrics | None,
    nutrition: HydrationNutrition | None,
    outside_period: bool,
) -> DailyHealthExport:
    def get(obj: object | None, name: str) -> Any:
        return getattr(obj, name, None) if obj is not None else None

    hydration_value = get(nutrition, "hydration_ml")
    nutrition_value = get(nutrition, "nutrition_calories")
    return DailyHealthExport(
        day=day,
        outside_period=outside_period,
        steps=get(recovery, "steps"),
        distance_km=get(health, "distance_km"),
        floors=get(health, "floors"),
        calories_kcal=get(health, "calories"),
        moderate_intensity_minutes=get(recovery, "moderate_minutes"),
        vigorous_intensity_minutes=get(recovery, "vigorous_minutes"),
        resting_hr_bpm=get(recovery, "resting_hr"),
        minimum_hr_bpm=get(health, "min_hr"),
        maximum_hr_bpm=get(health, "max_hr"),
        stress_score=get(recovery, "stress"),
        body_battery_charged=get(recovery, "body_battery_charged"),
        body_battery_drained=get(recovery, "body_battery_drained"),
        training_readiness_score=get(recovery, "readiness_score"),
        sleep_hours=get(recovery, "sleep_hours"),
        sleep_score=get(recovery, "sleep_score"),
        deep_sleep_hours=get(sleep, "deep_hours"),
        light_sleep_hours=get(sleep, "light_hours"),
        rem_sleep_hours=get(sleep, "rem_hours"),
        awake_hours=get(sleep, "awake_hours"),
        overnight_hrv_ms=get(sleep, "overnight_hrv"),
        spo2_percentage=get(sleep, "spo2"),
        respiration_breaths_min=get(sleep, "respiration"),
        skin_temperature_deviation_c=get(sleep, "skin_temp_deviation"),
        hydration_ml=hydration_value,
        hydration_status="logged"
        if hydration_value is not None
        else ("not_logged" if nutrition is not None else "unavailable"),
        hydration_goal_ml=get(nutrition, "hydration_goal_ml"),
        nutrition_calories_kcal=nutrition_value,
        nutrition_status="logged"
        if nutrition_value is not None
        else ("not_logged" if nutrition is not None else "unavailable"),
        nutrition_goal_calories_kcal=get(nutrition, "nutrition_goal_calories"),
        protein_g=get(nutrition, "protein_g"),
        carbohydrates_g=get(nutrition, "carbs_g"),
        fat_g=get(nutrition, "fat_g"),
        protein_goal_g=get(nutrition, "protein_goal_g"),
        carbohydrates_goal_g=get(nutrition, "carbs_goal_g"),
        fat_goal_g=get(nutrition, "fat_goal_g"),
    )


def _has_daily_values(item: DailyHealthExport) -> bool:
    values = item.model_dump(exclude={"day", "outside_period"}).values()
    return any(value is not None for value in values)


def _infer_muscles(name: str) -> MuscleInference | None:
    normalized = re.sub(r"[_-]+", " ", name).lower()
    for needle, (primary, secondary) in _MUSCLES.items():
        if needle in normalized:
            return MuscleInference(primary_muscles=list(primary), secondary_muscles=list(secondary))
    return None


def _rv(report: RenphoReportData | None, name: str) -> float | None:
    metric = getattr(report, name, None) if report else None
    return getattr(metric, "value", None)


def _segments(report: RenphoReportData | None) -> dict[str, BodySegmentExport]:
    if report is None:
        return {}
    return {
        name: _segment(getattr(report, name))
        for name in ("left_arm", "right_arm", "trunk", "left_leg", "right_leg")
    }


def _segment(value: BodySegment) -> BodySegmentExport:
    return BodySegmentExport(
        fat=SegmentMetricExport(
            mass_kg=value.fat.mass, percentage=value.fat.percentage, standard_kg=value.fat.standard
        ),
        muscle=SegmentMetricExport(
            mass_kg=value.muscle.mass,
            percentage=value.muscle.percentage,
            standard_kg=value.muscle.standard,
        ),
    )


def _impedance(value: Impedance) -> ImpedanceExport:
    return ImpedanceExport(
        right_arm_ohm=value.right_arm,
        left_arm_ohm=value.left_arm,
        trunk_ohm=value.trunk,
        right_leg_ohm=value.right_leg,
        left_leg_ohm=value.left_leg,
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ").strip()


def _display(value: object | None, suffix: str = "") -> str:
    if value is None:
        return "Not available"
    if isinstance(value, float):
        return f"{value:.1f}{suffix}"
    return f"{value}{suffix}"


def _display_change(value: MetricChangeExport | None) -> str:
    if value is None:
        return "Not enough comparable measurements"
    return f"{value.first_value:.2f} → {value.last_value:.2f} ({value.absolute_change:+.2f}, {value.measurements} measurements; {value.source})"


def _table(headers: list[str], rows: list[list[object]]) -> list[str]:
    if not rows:
        return ["Not available."]
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *["| " + " | ".join(_escape(value) for value in row) + " |" for row in rows],
    ]


def schema_json() -> str:
    """Expose a stable schema for tests and external AI tooling."""
    return json.dumps(HealthContextExport.model_json_schema(), indent=2, sort_keys=True) + "\n"
