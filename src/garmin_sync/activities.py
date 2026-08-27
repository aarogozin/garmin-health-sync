from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .models import BERLIN

ACTIVITY_MAPPING_VERSION = 1

# IDs are RENPHO's official activity templates observed in RENPHO Health 7.9.6.
RENPHO_ACTIVITY_MAPPING: dict[str, tuple[int, str]] = {
    "running": (52, "Running"),
    "trail_running": (52, "Running"),
    "treadmill_running": (72, "Treadmill Running"),
    "walking": (53, "Walking"),
    "casual_walking": (53, "Walking"),
    "hiking": (54, "Hiking"),
    "cycling": (55, "Bicycling"),
    "e_bike_fitness": (55, "Bicycling"),
    "road_biking": (55, "Bicycling"),
    "mountain_biking": (55, "Bicycling"),
    "indoor_cycling": (85, "Stationary Bike"),
    "badminton": (56, "Badminton"),
    "tennis": (58, "Tennis"),
    "yoga": (59, "Yoga"),
    "dance": (60, "Dancing"),
    "soccer": (57, "Soccer"),
    "basketball": (61, "Basketball"),
    "jump_rope": (63, "Jump Rope"),
    "volleyball": (64, "Volleyball"),
    "lap_swimming": (65, "Swimming"),
    "open_water_swimming": (65, "Swimming"),
    "swimming": (65, "Swimming"),
    "boxing": (66, "Boxing"),
    "rowing": (67, "Rowing"),
    "indoor_rowing": (67, "Rowing"),
    "triathlon": (68, "Triathlon"),
    "bowling": (69, "Bowling"),
    "resort_skiing": (70, "Skiing"),
    "cross_country_skiing": (70, "Skiing"),
    "skating": (71, "Skating"),
    "race_walking": (73, "Race Walking"),
    "baseball": (74, "Baseball"),
    "ice_hockey": (75, "Ice Hockey"),
    "surfing": (76, "Surfing"),
    "american_football": (77, "American Football"),
    "rugby": (78, "Rugby"),
    "golf": (79, "Golf"),
    "rock_climbing": (80, "Rock Climbing"),
    "bouldering": (80, "Rock Climbing"),
    "hockey": (81, "Hockey"),
    "handball": (82, "Handball"),
    "meditation": (84, "Meditation"),
    "elliptical": (90, "Elliptical"),
    "strength_training": (91, "Resistance (Weight) Training"),
    "cardio_training": (89, "Aerobics"),
    "circuit_training": (88, "Circuit Training"),
    "calisthenics": (87, "Calisthenics"),
    "stretching": (93, "Stretching"),
    "pilates": (94, "Pilates"),
    "fishing": (95, "Fishing"),
}


@dataclass(frozen=True, slots=True)
class GarminActivity:
    source_id: str
    activity_type: str
    name: str
    started_at: datetime
    duration_seconds: int
    calories: int
    calories_missing: bool = False


@dataclass(frozen=True, slots=True)
class RenphoActivityTemplate:
    template_id: int
    name: str
    is_official: int = 1


@dataclass(frozen=True, slots=True)
class RenphoActivityRecord:
    record_id: str | None
    template_id: int
    started_at: datetime
    duration_seconds: int
    calories: int


@dataclass(frozen=True, slots=True)
class ActivitySyncCandidate:
    activity: GarminActivity
    template: RenphoActivityTemplate


@dataclass(frozen=True, slots=True)
class ActivitySyncPreview:
    period: str
    candidates: tuple[ActivitySyncCandidate, ...]
    unknown: tuple[GarminActivity, ...]
    invalid_count: int
    duplicate_count: int

    @property
    def count(self) -> int:
        return len(self.candidates)


@dataclass(frozen=True, slots=True)
class ActivitySyncProgress:
    stage: str
    completed: int
    total: int
    uploaded: int = 0
    skipped: int = 0


@dataclass(frozen=True, slots=True)
class ActivitySyncResult:
    status: str
    activity_id: str
    message: str


def normalize_garmin_activity(raw: dict[str, Any]) -> GarminActivity | None:
    source = raw.get("activityId")
    if raw.get("beginTimestamp") is not None:
        started = _activity_datetime(raw["beginTimestamp"], naive_timezone=UTC)
    elif raw.get("startTimeGMT") is not None:
        started = _activity_datetime(raw["startTimeGMT"], naive_timezone=UTC)
    else:
        started = _activity_datetime(raw.get("startTimeLocal"), naive_timezone=BERLIN)
    duration = _number(raw.get("duration"))
    if source is None or started is None or duration is None:
        return None
    duration_seconds = int(Decimal(str(duration)).quantize(Decimal("1"), ROUND_HALF_UP))
    if duration_seconds <= 0:
        return None
    kind = raw.get("activityType")
    type_key = kind.get("typeKey") if isinstance(kind, dict) else kind
    if not type_key:
        type_key = "unknown"
    calories_value = _number(raw.get("calories"))
    calories = (
        0
        if calories_value is None
        else max(0, int(Decimal(str(calories_value)).quantize(Decimal("1"), ROUND_HALF_UP)))
    )
    return GarminActivity(
        str(source),
        str(type_key),
        str(raw.get("activityName") or type_key),
        started,
        duration_seconds,
        calories,
        calories_value is None,
    )


def mapped_template(activity: GarminActivity) -> RenphoActivityTemplate | None:
    mapping = RENPHO_ACTIVITY_MAPPING.get(activity.activity_type.lower())
    if mapping is None:
        return None
    return RenphoActivityTemplate(mapping[0], mapping[1])


def template_matches_mapping(
    expected: RenphoActivityTemplate, actual: RenphoActivityTemplate
) -> bool:
    return (
        expected.template_id == actual.template_id
        and actual.is_official == 1
        and _normalized_template_name(expected.name) == _normalized_template_name(actual.name)
    )


def exact_activity_match(
    candidate: ActivitySyncCandidate, record: RenphoActivityRecord
) -> bool:
    return (
        candidate.template.template_id == record.template_id
        and abs(candidate.activity.started_at.timestamp() - record.started_at.timestamp()) <= 2
        and abs(candidate.activity.duration_seconds - record.duration_seconds) <= 1
        and candidate.activity.calories == record.calories
    )


def _activity_datetime(value: Any, *, naive_timezone: tzinfo) -> datetime | None:
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if value > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=BERLIN)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=naive_timezone)
    return parsed.astimezone(BERLIN)


def _normalized_template_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
