from datetime import datetime

import pytest

from garmin_sync.models import (
    BERLIN,
    BloodPressure,
    BodyComposition,
    ValidationError,
    parse_local_datetime,
)


def test_parse_local_datetime_adds_berlin_timezone() -> None:
    value = parse_local_datetime("2026-08-13 08:30")
    assert value.isoformat() == "2026-08-13T08:30:00+02:00"


def test_empty_datetime_uses_supplied_now() -> None:
    now = datetime(2026, 1, 2, 3, 4, tzinfo=BERLIN)
    assert parse_local_datetime("", now=now) is now


@pytest.mark.parametrize(
    "field,value", [("weight", 0), ("percent_fat", 80), ("bmi", 3), ("bone_mass", 40)]
)
def test_body_composition_rejects_invalid_values(field: str, value: float) -> None:
    values = {"measured_at": datetime.now(BERLIN), "weight": 80.0, field: value}
    with pytest.raises(ValidationError):
        BodyComposition(**values)


def test_body_composition_only_sends_supported_fields() -> None:
    item = BodyComposition(datetime(2026, 8, 13, 8, 30, tzinfo=BERLIN), 80, percent_fat=20)
    assert item.garmin_kwargs()["weight"] == 80
    assert item.garmin_kwargs()["percent_fat"] == 20
    assert item.garmin_kwargs()["metabolic_age"] is None


@pytest.mark.parametrize("systolic,diastolic,pulse", [(60, 40, 60), (120, 160, 60), (120, 80, 300)])
def test_pressure_rejects_invalid_values(systolic: int, diastolic: int, pulse: int) -> None:
    with pytest.raises(ValidationError):
        BloodPressure(datetime.now(BERLIN), systolic, diastolic, pulse)
