from datetime import datetime
from typing import Any

import pytest
import requests

from garmin_sync.activities import RenphoActivityTemplate
from garmin_sync.models import BERLIN
from garmin_sync.renpho import (
    RenphoCloud,
    RenphoError,
    RenphoWriteUncertain,
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


def test_authentication_adds_required_activity_headers() -> None:
    class Session:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

    class Headers(FakeAPI):
        def __init__(self, *_: Any, **__: Any) -> None:
            super().__init__()
            self._transport = type("Transport", (), {"session": Session()})()

    api = RenphoCloud(Credentials(), Headers).authenticate()
    assert api._transport.session.headers["language"] == "en"  # type: ignore[attr-defined]
    assert api._transport.session.headers["timeZone"] == "Europe/Berlin"  # type: ignore[attr-defined]


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


def test_activity_templates_history_and_write_use_app_endpoints(monkeypatch) -> None:
    class Activities(FakeAPI):
        def __init__(self, *_: Any, **__: Any) -> None:
            super().__init__()
            self.calls: list[tuple[str, dict[str, Any]]] = []

        def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
            self.calls.append((endpoint, body))
            if endpoint.endswith("selectActivityTemplate"):
                return {
                    "code": 101,
                    "data": {
                        "list": [
                            {"sportTypeId": 52, "sportName": "Running", "isOfficial": 0}
                        ]
                    },
                }
            if endpoint.endswith("getActivity"):
                return {
                    "code": 101,
                    "data": {
                        "list": [
                            {
                                "id": 7,
                                "sportTypeId": 52,
                                "recordTime": 1_776_000_000_000,
                                "duration": 1800,
                                "cal": 300,
                            }
                        ]
                    },
                }
            return {"code": 101, "data": {"id": 8}}

    monkeypatch.setattr("garmin_sync.renpho.encrypt_request", lambda value: value)
    cloud = RenphoCloud(Credentials(), Activities)
    assert cloud.fetch_activity_templates()[0] == RenphoActivityTemplate(52, "Running", 0)
    assert cloud.fetch_activities()[0].calories == 300
    template = cloud.fetch_activity_templates()[0]
    assert (
        cloud.create_activity(
            template=template,
            started_at=datetime(2026, 8, 22, tzinfo=BERLIN),
            duration_seconds=1800,
            calories=300,
        )
        == "8"
    )
    api = cloud.authenticate()
    assert isinstance(api, Activities)
    endpoint, payload = api.calls[-1]
    assert endpoint.endswith("recordActivity")
    assert payload["userId"] == "123"
    assert payload["sportTypeId"] == 52


def test_activity_write_timeout_is_uncertain(monkeypatch) -> None:
    class Timeout(FakeAPI):
        def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]:
            raise requests.Timeout("timeout")

    monkeypatch.setattr("garmin_sync.renpho.encrypt_request", lambda value: value)
    cloud = RenphoCloud(Credentials(), Timeout)
    with pytest.raises(RenphoWriteUncertain):
        cloud.create_activity(
            template=RenphoActivityTemplate(52, "Running"),
            started_at=datetime(2026, 8, 22, tzinfo=BERLIN),
            duration_seconds=1800,
            calories=300,
        )
