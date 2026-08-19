from datetime import UTC, date, datetime

from pypdf import PdfReader

from garmin_sync.models import BERLIN, BodyComposition
from garmin_sync.renpho import RenphoMeasurement
from garmin_sync.weekly_pdf import render_weekly_report_pdf
from garmin_sync.weekly_report import (
    LifestyleEvent,
    build_report,
    chart_payload,
    group_lifestyle_events,
    render_weekly_html,
)


def _raw() -> dict[str, object]:
    return {
        "activities": [
            {
                "startTimeLocal": "2026-08-10T07:30:00",
                "activityId": 123456789,
                "activityName": "Morning Run <fast>",
                "activityType": {"typeKey": "running"},
                "duration": 1800,
                "distance": 5000,
                "calories": 350,
                "averageHR": 145,
                "maxHR": 172,
                "activityTrainingLoad": 82,
            }
        ],
        "pressure": {
            "measurementSummaries": [
                {
                    "systolic": 128,
                    "diastolic": 79,
                    "pulse": 61,
                    "measurementTimestampGMT": "2026-08-10T06:00:00",
                },
                {
                    "systolic": 182,
                    "diastolic": 121,
                    "pulse": 70,
                    "measurementTimestampGMT": "2026-08-12T06:00:00",
                },
            ]
        },
        "body": {
            "dateWeightList": [
                {
                    "timestampGMT": datetime(2026, 8, 10, 5, tzinfo=UTC).timestamp() * 1000,
                    "weight": 90000,
                }
            ]
        },
        "stats": {
            "2026-08-10": {
                "totalSteps": 10000,
                "moderateIntensityMinutes": 30,
                "vigorousIntensityMinutes": 10,
                "averageStressLevel": 28,
            }
        },
        "sleep": {
            "2026-08-10": {
                "restingHeartRate": 52,
                "dailySleepDTO": {"sleepTimeSeconds": 27000, "sleepScore": 84},
            }
        },
        "readiness": {"2026-08-10": {"score": 77}},
    }


def test_weekly_mapping_deduplicates_body_and_normalizes_pressure_time() -> None:
    renpho = RenphoMeasurement(
        "r1",
        BodyComposition(
            datetime(2026, 8, 10, 7, tzinfo=BERLIN),
            90,
            percent_fat=18,
            muscle_mass=42,
        ),
    )
    report = build_report(
        start_date=date(2026, 8, 9),
        end_date=date(2026, 8, 15),
        garmin=_raw(),
        renpho=[renpho],
        available=["activities", "pressure", "body", "renpho"],
        unavailable=[],
        generated_at=datetime(2026, 8, 15, 12, tzinfo=BERLIN),
    )
    assert report.activities[0].duration_minutes == 30
    assert report.pressure.readings[0].measured_at.hour == 8
    assert report.pressure.has_extreme
    assert len(report.body) == 1
    assert report.body[0].source == "RENPHO + Garmin"
    assert report.body[0].body_fat_pct == 18


def test_weekly_html_escapes_values_and_pdf_is_vector_a4() -> None:
    report = build_report(
        start_date=date(2026, 8, 9),
        end_date=date(2026, 8, 15),
        garmin=_raw(),
        renpho=[],
        available=["activities"],
        unavailable=["sleep"],
        generated_at=datetime(2026, 8, 15, 12, tzinfo=BERLIN),
    )
    web = render_weekly_html(report, "csrf", "report-id")
    assert "Morning Run &lt;fast&gt;" in web
    assert "Morning Run <fast>" not in web
    assert "https://connect.garmin.com/modern/activity/123456789" in web
    assert "noreferrer noopener" in web
    pdf = render_weekly_report_pdf(report)
    assert pdf.startswith(b"%PDF-")
    reader = PdfReader(__import__("io").BytesIO(pdf))
    assert len(reader.pages) >= 2
    assert round(float(reader.pages[0].mediabox.width), 1) == 595.3
    text = "".join(page.extract_text() or "" for page in reader.pages)
    assert "7-day health report" in text
    assert "Blood pressure" in text
    resources = reader.pages[0].get("/Resources")
    assert resources is not None and resources.get("/XObject") is None


def test_sparse_data_produces_cautious_insight() -> None:
    report = build_report(
        start_date=date(2026, 8, 9),
        end_date=date(2026, 8, 15),
        garmin={},
        renpho=[],
        available=[],
        unavailable=["Garmin session", "renpho"],
    )
    assert report.availability.unavailable == ("Garmin session", "renpho")
    assert any("not enough data" in item.text for item in report.insights)


def test_activity_link_rejects_non_numeric_api_identifier() -> None:
    raw = _raw()
    activities = raw["activities"]
    assert isinstance(activities, list)
    activities[0]["activityId"] = "123' onclick='alert(1)"
    report = build_report(
        start_date=date(2026, 8, 9),
        end_date=date(2026, 8, 15),
        garmin=raw,
        renpho=[],
        available=["activities"],
        unavailable=[],
    )
    web = render_weekly_html(report, "csrf", "report")
    assert "connect.garmin.com/modern/activity" not in web
    assert "onclick" not in web


def test_rule_based_insights_require_coverage_and_include_sources() -> None:
    raw = _raw()
    raw["sleep"] = {
        f"2026-08-{day:02d}": {
            "dailySleepDTO": {"sleepTimeSeconds": 6 * 3600, "sleepScore": 70},
            "restingHeartRate": 54,
        }
        for day in range(9, 16)
    }
    raw["stats"] = {
        f"2026-08-{day:02d}": {"averageStressLevel": 60} for day in range(9, 16)
    }
    report = build_report(
        start_date=date(2026, 8, 9),
        end_date=date(2026, 8, 15),
        garmin=raw,
        renpho=[],
        available=["sleep", "stats"],
        unavailable=[],
    )
    sleep = next(item for item in report.insights if item.category == "Sleep")
    stress = next(item for item in report.insights if item.category == "Recovery")
    assert "6.0 hours" in sleep.text and sleep.source_url is not None
    assert "medium physiological stress" in stress.text
    html = render_weekly_html(report, "csrf", "report")
    assert "confidence" in html and "noreferrer noopener" in html
    assert "Practical next steps" in html


def test_comprehensive_domains_lifestyle_associations_and_private_route() -> None:
    raw = _raw()
    raw.update(
        {
            "stats": {
                f"2026-08-{day:02d}": {
                    "averageStressLevel": 20 + day,
                    "minHeartRate": 48,
                    "maxHeartRate": 166,
                    "burnedKilocalories": 2400,
                    "floorsAscended": day,
                }
                for day in range(9, 16)
            },
            "sleep": {
                f"2026-08-{day:02d}": {
                    "restingHeartRate": 50 + day % 2,
                    "dailySleepDTO": {
                        "sleepScore": 70 + day,
                        "deepSleepSeconds": 5400,
                        "lightSleepSeconds": 14400,
                        "remSleepSeconds": 5400,
                    },
                }
                for day in range(9, 16)
            },
            "hrv": {
                f"2026-08-{day:02d}": {"hrvSummary": {"lastNightAvg": 45 + day}}
                for day in range(9, 16)
            },
            "stress": {
                f"2026-08-{day:02d}": {"avgStressLevel": 20 + day}
                for day in range(9, 16)
            },
            "lifestyle": {
                f"2026-08-{day:02d}": {
                    "dailyLogsReport": [
                        {
                            "name": "Coffee",
                            "category": "Caffeine",
                            "logStatus": 1,
                            "sleepRelated": True,
                        }
                    ]
                    if day in {9, 10, 11}
                    else []
                }
                for day in range(9, 16)
            },
            "hydration": {"2026-08-15": {"valueInML": 2100, "goalInML": 2500}},
            "nutrition": {
                "2026-08-15": {
                    "mealDetails": [{"calories": 800, "protein": 45, "carbohydrates": 90}]
                }
            },
            "activity_details": {
                "42": {
                    "summaryDTO": {"locationName": "Private trail", "elevationGain": 120},
                    "geoPolylineDTO": {
                        "polyline": [
                            {"latitude": 52.5, "longitude": 13.4},
                            {"latitude": 52.51, "longitude": 13.42},
                        ]
                    },
                }
            },
            "include_routes": True,
            "map_tiles_enabled": True,
            "extended": {"devices": [{"name": "Watch"}], "golf": []},
        }
    )
    report = build_report(
        start_date=date(2026, 8, 9),
        end_date=date(2026, 8, 15),
        garmin=raw,
        renpho=[],
        available=list(raw),
        unavailable=[],
    )
    assert report.comprehensive.sleep[-1].deep_hours == 1.5
    assert report.comprehensive.hydration_nutrition[-1].hydration_ml == 2100
    assert any(item.behavior == "Coffee" for item in report.comprehensive.associations)
    assert report.comprehensive.activity_details[0].route[1].longitude == 13.42
    payload = chart_payload(report)
    assert payload["routes"][0]["points"] == [[52.5, 13.4], [52.51, 13.42]]
    assert payload["map_tiles_enabled"] is True
    assert "Private trail" not in repr(report.availability)


def test_lifestyle_association_requires_three_days_in_each_group() -> None:
    raw = _raw()
    raw["lifestyle"] = {
        "2026-08-10": {
            "dailyLogsReport": [{"name": "Alcohol", "category": "Alcohol", "logStatus": 1}]
        }
    }
    report = build_report(
        start_date=date(2026, 8, 9),
        end_date=date(2026, 8, 15),
        garmin=raw,
        renpho=[],
        available=[],
        unavailable=[],
    )
    assert report.comprehensive.associations == ()


def test_lifestyle_ignores_quantity_options_when_behavior_was_not_logged() -> None:
    raw = _raw()
    raw["lifestyle"] = {
        "2026-08-10": {
            "dailyLogsReport": [
                {"name": "Unused", "logStatus": None, "details": []},
                {
                    "name": "Alcohol",
                    "category": "Alcohol",
                    "logStatus": None,
                    "measurementType": "QUANTITY",
                    "details": [
                        {"subTypeName": "Beer"},
                        {"subTypeName": "Wine"},
                        {"subTypeName": "Spirits"},
                        {"subTypeName": "Other"},
                    ],
                },
                {"name": "Coffee", "logStatus": "2", "measurementType": "QUANTITY"},
            ]
        }
    }
    report = build_report(
        start_date=date(2026, 8, 9),
        end_date=date(2026, 8, 15),
        garmin=raw,
        renpho=[],
        available=[],
        unavailable=[],
    )
    assert [(item.name, item.value) for item in report.comprehensive.lifestyle] == [
        ("Coffee", 2.0)
    ]


def test_lifestyle_display_groups_all_behaviors_into_one_row_per_day() -> None:
    events = (
        LifestyleEvent(date(2026, 8, 10), "Alcohol", "Alcohol", None, True),
        LifestyleEvent(date(2026, 8, 10), "Coffee", "Caffeine", 4, True),
        LifestyleEvent(date(2026, 8, 11), "Late meal", "Custom", None, True),
    )
    assert group_lifestyle_events(events) == (
        (date(2026, 8, 10), ("Alcohol", "Coffee × 4")),
        (date(2026, 8, 11), ("Late meal",)),
    )
