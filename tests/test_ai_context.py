from __future__ import annotations

import json
import os
import stat
from datetime import date, datetime

from garmin_sync.ai_context import (
    HealthContextExport,
    build_health_context,
    render_context_json,
    render_context_markdown,
)
from garmin_sync.archive import LocalHealthArchive
from garmin_sync.models import BERLIN, BodyComposition
from garmin_sync.renpho import RenphoMeasurement
from garmin_sync.renpho_report import normalize_report
from garmin_sync.weekly_report import build_report


def _report():
    first = datetime(2026, 9, 1, 7, tzinfo=BERLIN)
    last = datetime(2026, 9, 19, 7, tzinfo=BERLIN)
    return build_report(
        start_date=date(2026, 8, 21),
        end_date=date(2026, 9, 19),
        garmin={
            "activities": [
                {
                    "activityId": 42,
                    "activityName": "Upper body",
                    "activityType": {"typeKey": "strength_training"},
                    "startTimeLocal": "2026-09-19T08:00:00",
                    "duration": 1800,
                    "calories": 220,
                    "averageHR": 112,
                }
            ],
            "activity_details": {
                "42": {
                    "summaryDTO": {"averagePower": 120, "averageCadence": 34},
                    "exerciseSets": {
                        "exerciseSets": [
                            {
                                "exerciseName": "Bench Press",
                                "repetitionCount": 8,
                                "weight": 80,
                                "repsInReserve": 2,
                            },
                            {"exerciseName": "Custom movement", "repetitions": 10},
                        ]
                    },
                    "splits": {"splits": [{"splitNumber": 1, "duration": 900, "averageHR": 110}]},
                }
            },
            "pressure": {
                "readings": [
                    {
                        "systolic": 124,
                        "diastolic": 78,
                        "pulse": 58,
                        "measurementTimestampLocal": "2026-09-19T07:00:00",
                    }
                ]
            },
            "stats": {
                "2026-09-18": {"totalSteps": 7000, "averageStressLevel": 31},
                "2026-09-19": {
                    "totalSteps": 9000,
                    "moderateIntensityMinutes": 30,
                    "vigorousIntensityMinutes": 10,
                },
            },
        },
        renpho=[
            RenphoMeasurement(
                "source-secret-1",
                BodyComposition(first, 92, percent_fat=20, muscle_mass=42),
                normalize_report(
                    {
                        "reportId": "report-secret-1",
                        "weight": 92,
                        "bodyfat": 20,
                        "sinew": 68,
                        "smmMass": 36,
                        "fatFreeWeight": 73.6,
                    },
                    first,
                ),
            ),
            RenphoMeasurement(
                "source-secret-2",
                BodyComposition(last, 90, percent_fat=18, muscle_mass=43),
                normalize_report(
                    {
                        "reportId": "report-secret-2",
                        "weight": 90,
                        "bodyfat": 18,
                        "sinew": 69,
                        "smmMass": 37,
                        "fatFreeWeight": 73.8,
                    },
                    last,
                ),
            ),
        ],
        available=["activities", "activity_details", "renpho"],
        unavailable=[],
    )


def test_context_has_strict_schema_dynamics_and_inferred_muscles() -> None:
    context = build_health_context(_report(), "30d")
    payload = json.loads(render_context_json(context))
    HealthContextExport.model_validate(payload)

    assert context.body_dynamics.weight_kg is not None
    assert context.body_dynamics.weight_kg.absolute_change == -2
    assert context.body_dynamics.body_fat_mass_kg is not None
    assert context.body_dynamics.body_fat_mass_kg.estimated
    assert context.training_summary.categories["strength"].sessions == 1
    assert context.training_summary.unmapped_exercises == ["Custom movement"]
    muscles = context.activities[0].exercise_sets[0].muscles
    assert muscles is not None and "chest" in muscles.primary_muscles
    assert context.activities[0].splits[0].duration_seconds == 900
    assert context.activities[0].activity_label == "Strength Training"
    assert context.activities[0].heart_rate_zones.zone1_minutes == 0
    assert context.body_measurements[0].muscle_mass_kg == 68
    assert context.body_measurements[0].skeletal_muscle_mass_kg == 36
    assert context.summary.exercise_progression[0].exercise_key == "bench_press"
    assert context.summary.exercise_progression[0].valid_sets == 1
    assert context.summary.exercise_progression[0].best_weight_x_reps == 640
    assert round(context.summary.exercise_progression[0].best_estimated_1rm_kg or 0, 2) == 101.33
    assert context.summary.exercise_progression[0].rir_status == "recorded"
    assert context.activities[0].exercise_sets[0].rir == 2
    assert context.activities[0].exercise_sets[0].set_number == 1
    assert context.activities[0].exercise_sets[0].exercise_key == "bench_press"
    assert context.activities[0].exercise_sets_status == "recorded"
    assert context.summary.strength_progress.exercises_tracked == 2
    assert "Epley" in context.summary.definitions.estimated_1rm
    assert context.summary.trends_7d.period_days == 7
    assert context.summary.trends_30d.period_days == 30


def test_current_uses_latest_body_as_dated_baseline_and_filters_events() -> None:
    report = _report()
    current = build_health_context(report, "current")
    assert current.period.start_date == date(2026, 9, 19)
    assert len(current.activities) == 1
    assert len(current.body_measurements) == 1
    assert not current.body_measurements[0].outside_period
    assert current.daily_health[0].day == date(2026, 9, 18)
    assert current.daily_health[0].outside_period
    assert current.daily_health[-1].day == date(2026, 9, 19)

    no_today = build_report(
        start_date=report.start_date,
        end_date=date(2026, 9, 20),
        garmin={},
        renpho=[
            RenphoMeasurement(
                "secret",
                BodyComposition(datetime(2026, 9, 19, 7, tzinfo=BERLIN), 90),
            )
        ],
        available=["renpho"],
        unavailable=[],
    )
    baseline = build_health_context(no_today, "current")
    assert baseline.body_measurements[0].outside_period
    assert baseline.body_measurements[0].measured_at.date() == date(2026, 9, 19)


def test_json_and_markdown_exclude_private_provider_fields() -> None:
    context = build_health_context(_report(), "30d")
    combined = render_context_json(context) + render_context_markdown(context)
    for forbidden in (
        "source-secret",
        "report-secret",
        "latitude",
        "longitude",
        "locationName",
        "oauth",
        "%PDF",
    ):
        assert forbidden not in combined
    assert "Bench Press" in combined
    assert "Upper body" not in combined
    assert "garmin-health-sync/ai-context@3" in combined
    payload = json.loads(render_context_json(context))
    assert "summary" in payload
    assert "raw_data" in payload
    assert "activities" not in payload
    assert "derived_insights" in payload["raw_data"]


def test_context_does_not_turn_goals_or_zero_hydration_into_consumption() -> None:
    report = build_report(
        start_date=date(2026, 9, 19),
        end_date=date(2026, 9, 19),
        garmin={
            "hydration": {"2026-09-19": {"valueInML": 0, "goalInML": 2500}},
            "nutrition": {
                "2026-09-19": {"dailyNutritionGoals": {"calories": 1610, "protein": 120}}
            },
        },
        renpho=[],
        available=["hydration", "nutrition"],
        unavailable=[],
    )
    daily = build_health_context(report, "current").daily_health[-1]
    assert daily.hydration_ml is None
    assert daily.hydration_status == "not_logged"
    assert daily.nutrition_calories_kcal is None
    assert daily.nutrition_status == "not_logged"
    assert daily.nutrition_goal_calories_kcal == 1610
    assert daily.protein_goal_g == 120
    quality = build_health_context(report, "current").summary.data_quality_flags
    assert quality.nutrition == "target_not_actual"
    assert quality.hydration == "not_logged"


def test_split_meters_body_dedup_and_multisport_components() -> None:
    measured = datetime(2026, 9, 19, 7, tzinfo=BERLIN)
    report = build_report(
        start_date=date(2026, 9, 19),
        end_date=date(2026, 9, 19),
        garmin={
            "activities": [
                {
                    "activityId": 7,
                    "activityName": "Munich private workout",
                    "activityType": {"typeKey": "multi_sport"},
                    "startTimeLocal": "2026-09-19T08:00:00",
                    "duration": 3600,
                }
            ],
            "activity_details": {
                "7": {
                    "splits": {"splits": [{"splitNumber": 1, "distance": 99.08}]},
                    "typedSplits": {
                        "splits": [
                            {"activityType": {"typeKey": "strength_training"}},
                            {"activityType": {"typeKey": "walking"}},
                        ]
                    },
                    "exerciseSets": {"exerciseSets": []},
                }
            },
            "body": {"dateWeightList": [{"timestampGMT": "2026-09-19T05:00:42Z", "weight": 90000}]},
        },
        renpho=[RenphoMeasurement("secret", BodyComposition(measured, 90))],
        available=["activities", "activity_details", "body", "renpho"],
        unavailable=[],
    )
    context = build_health_context(report, "current")
    activity = context.activities[0]
    assert activity.splits[0].distance_km == 0.09908
    assert activity.training_categories == ["strength", "cardio"]
    assert activity.exercise_sets_status == "not_recorded"
    assert "Munich" not in render_context_json(context)
    assert len(context.body_measurements) == 1
    assert context.body_measurements[0].source == "RENPHO + Garmin"
    assert not context.summary.data_quality_flags.duplicate_body_measurements
    assert not context.summary.data_quality_flags.activity_split_distance_anomalies
    assert context.summary.data_quality_flags.multisport_contains_strength


def test_strength_progression_normalizes_names_and_excludes_warmups() -> None:
    activities = []
    details: dict[str, object] = {}
    for activity_id, day, exercise_name, working_weight in (
        ("1", "2026-09-05", "Barbell Deadlift", 80000),
        ("2", "2026-09-19", "Conventional Deadlift", 90000),
    ):
        activities.append(
            {
                "activityId": activity_id,
                "activityType": {"typeKey": "strength_training"},
                "startTimeLocal": f"{day}T08:00:00",
                "duration": 1800,
            }
        )
        details[activity_id] = {
            "exerciseSets": {
                "exerciseSets": [
                    {
                        "exerciseName": exercise_name,
                        "setNumber": 1,
                        "reps": 8,
                        "weightGrams": 60000,
                        "setType": "WARMUP",
                    },
                    {
                        "exerciseName": exercise_name,
                        "setNumber": 2,
                        "reps": 6,
                        "weightGrams": working_weight,
                        "setType": "ACTIVE",
                    },
                ]
            }
        }
    report = build_report(
        start_date=date(2026, 8, 21),
        end_date=date(2026, 9, 19),
        garmin={"activities": activities, "activity_details": details},
        renpho=[],
        available=["activities", "activity_details"],
        unavailable=[],
    )
    context = build_health_context(report, "30d")
    progression = context.summary.exercise_progression
    assert len(progression) == 1
    deadlift = progression[0]
    assert deadlift.exercise_key == "deadlift"
    assert deadlift.exercise_names == ["Barbell Deadlift", "Conventional Deadlift"]
    assert deadlift.sessions == 2
    assert deadlift.valid_sets == 2
    assert deadlift.first_working_weight_kg == 80
    assert deadlift.latest_working_weight_kg == 90
    assert deadlift.best_weight_x_reps == 540
    assert deadlift.warmup_sets_excluded
    assert round(deadlift.trend_30d_change_pct or 0, 1) == 12.5
    assert round(deadlift.estimated_1rm_change_pct or 0, 1) == 12.5
    assert context.summary.strength_progress.exercises_with_weight_trend == 1


def test_strength_set_status_is_partial_without_recorded_performance() -> None:
    report = build_report(
        start_date=date(2026, 9, 19),
        end_date=date(2026, 9, 19),
        garmin={
            "activities": [
                {
                    "activityId": 9,
                    "activityType": {"typeKey": "strength_training"},
                    "startTimeLocal": "2026-09-19T08:00:00",
                    "duration": 1200,
                }
            ],
            "activity_details": {
                "9": {"exerciseSets": {"exerciseSets": [{"exerciseName": "Deadlift"}]}}
            },
        },
        renpho=[],
        available=["activities", "activity_details"],
        unavailable=[],
    )
    activity = build_health_context(report, "current").activities[0]
    assert activity.exercise_sets_status == "partial"
    assert activity.exercise_sets[0].reps is None
    assert activity.exercise_sets[0].weight_kg is None


def test_archive_writes_deterministic_private_context_files(tmp_path) -> None:
    archive = LocalHealthArchive(tmp_path / "archive")
    context = build_health_context(_report(), "30d")
    archive.write_context("30d", render_context_json(context), render_context_markdown(context))
    json_path = archive.profile_root / "context" / "LAST_30_DAYS.json"
    markdown_path = archive.profile_root / "context" / "LAST_30_DAYS.md"
    assert json_path.exists() and markdown_path.exists()
    assert stat.S_IMODE(os.stat(json_path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(json_path.parent).st_mode) == 0o700
    assert not list(json_path.parent.glob(".health-note-*.tmp"))
