from datetime import datetime
from typing import Any

import pytest

from garmin_sync.models import BERLIN
from garmin_sync.renpho import (
    RenphoCloud,
    RenphoError,
    normalize_girth,
    normalize_measurement,
)


class Credentials:
    def __init__(self, value: tuple[str, str] | None = ("a@example.com", "secret")) -> None:
        self.value = value

    def load(self) -> tuple[str, str] | None:
        return self.value


class FakeAPI:
    user_id = 123

    def __init__(self, *_: Any, **__: Any) -> None:
        self.items: list[dict[str, Any]] = []

    def login(self) -> dict[str, Any]:
        return {"ok": True}

    def get_all_measurements(self) -> list[dict[str, Any]]:
        return self.items

    def get_device_info(self) -> dict[str, Any]:
        return {"girth": 0}

    def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("not used")


def test_normalize_maps_percentages_and_mass() -> None:
    raw = {
        "id": 42,
        "timeStamp": 1_786_588_200_000,
        "weight": 80,
        "bmi": 24.5,
        "bodyfat": 20,
        "water": 55,
        "muscle": 52.5,
        "bone": 4,
        "bmr": 1700,
        "visfat": 8,
        "bodyage": 35,
    }
    item = normalize_measurement(raw)
    assert item.source_id == "42"
    assert item.body.weight == 80
    assert item.body.muscle_mass == 42
    assert item.body.bone_mass == 3.2
    assert item.body.percent_hydration == 55
    assert item.body.measured_at.tzinfo == BERLIN
    assert item.report is not None
    assert item.report.bone_mass.value == 4
    assert item.body.garmin_kwargs()["bone_mass"] == 3.2


def test_normalize_requires_timestamp_and_weight() -> None:
    with pytest.raises(ValueError):
        normalize_measurement({"weight": 80})
    with pytest.raises(ValueError):
        normalize_measurement({"timeStamp": 1_786_588_200})


def test_fetch_sorts_newest_and_counts_bad_records() -> None:
    class Items(FakeAPI):
        def get_all_measurements(self) -> list[dict[str, Any]]:
            return [
                {"id": 1, "timeStamp": 1_700_000_000, "weight": 80},
                {"id": 2, "timeStamp": 1_800_000_000, "weight": 79},
                {"id": 3, "weight": 78},
            ]

    items, skipped = RenphoCloud(Credentials(), Items).fetch()
    assert [item.source_id for item in items] == ["2", "1"]
    assert skipped == 1


def test_authentication_requires_credentials() -> None:
    with pytest.raises(RenphoError, match="renpho login"):
        RenphoCloud(Credentials(None), FakeAPI).authenticate()


def test_epoch_is_converted_to_berlin() -> None:
    item = normalize_measurement({"timeStamp": 1_786_588_200, "weight": 80})
    assert isinstance(item.body.measured_at, datetime)
    assert item.body.measured_at.tzinfo == BERLIN


def test_normalize_girth_maps_available_body_parts_and_units() -> None:
    item = normalize_girth(
        {
            "timeStamp": 1_786_588_200_000,
            "waistValue": 91.2,
            "waistUnit": 0,
            "leftArmValue": 14.5,
            "leftArmUnit": 1,
            "whrValue": 0.84,
            "chestValue": 0,
        }
    )
    assert [(value.label, value.value, value.unit) for value in item.values] == [
        ("Waist", 91.2, "cm"),
        ("Left arm", 14.5, "in"),
        ("Waist-to-hip ratio", 0.84, "ratio"),
    ]
