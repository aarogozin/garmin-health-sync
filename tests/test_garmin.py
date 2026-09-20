from datetime import UTC, datetime
from typing import Any

import pytest
from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

from garmin_sync.garmin import (
    AuthenticationRequired,
    GarminClient,
    GarminSyncError,
    RateLimited,
    UploadUncertain,
)
from garmin_sync.models import BERLIN, BloodPressure, BodyComposition


class MemoryStore:
    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def load(self) -> str | None:
        return self.token

    def save(self, token: str) -> None:
        self.token = token

    def delete(self) -> bool:
        self.token = None
        return True


class FakeSession:
    def dumps(self) -> str:
        return "x" * 600


class FakeAPI:
    def __init__(self, *_: Any, **__: Any) -> None:
        self.client = FakeSession()
        self.full_name = "Test User"
        self.body: dict[str, Any] = {}
        self.last_body_kwargs: dict[str, Any] = {}
        self.pressure: dict[str, Any] = {}

    def login(self, tokenstore: str | None = None):
        return None, None

    def get_full_name(self):
        return self.full_name

    def add_body_composition(self, **kwargs: Any):
        self.last_body_kwargs = kwargs
        return {"ok": True}

    def set_blood_pressure(self, **kwargs: Any):
        timestamp = datetime.fromisoformat(kwargs["timestamp"]).astimezone(UTC)
        self.pressure = {
            "measurements": [
                {
                    "systolic": kwargs["systolic"],
                    "diastolic": kwargs["diastolic"],
                    "pulse": kwargs["pulse"],
                    "measurementTimestampGMT": timestamp.replace(tzinfo=None).isoformat(),
                }
            ]
        }
        return {"ok": True}

    def get_body_composition(self, startdate: str, enddate: str | None = None):
        if self.body:
            return self.body
        timestamp = datetime.fromisoformat(self.last_body_kwargs["timestamp"])
        return {
            "dateWeightList": [
                {
                    "weight": self.last_body_kwargs["weight"] * 1000,
                    "timestampGMT": timestamp.timestamp() * 1000,
                }
            ]
        }

    def get_blood_pressure(self, startdate: str, enddate: str | None = None):
        return self.pressure

    def get_max_metrics(self, cdate: str):
        return {"generic": {"vo2MaxValue": 48.7}}

def test_login_saves_tokens_not_password() -> None:
    store = MemoryStore()
    client = GarminClient(store, FakeAPI)
    assert client.login("me@example.com", "secret", lambda: "123456") == "Test User"
    assert store.token == "x" * 600
    assert "secret" not in store.token


def test_connect_requires_saved_session() -> None:
    with pytest.raises(AuthenticationRequired):
        GarminClient(MemoryStore(), FakeAPI).connect()


def test_max_metrics_are_cached_as_a_read_only_garmin_request() -> None:
    client = GarminClient(MemoryStore("token"), FakeAPI)
    assert client.read_max_metrics("2026-08-15")["generic"]["vo2MaxValue"] == 48.7


def test_activity_exercise_sets_and_splits_are_read_once_without_retry() -> None:
    class Activities(FakeAPI):
        calls = 0

        def get_activity_exercise_sets(self, activity_id: int | str) -> dict[str, Any]:
            self.calls += 1
            return {"exerciseSets": [{"exerciseName": "Bench Press"}]}

        def get_activity_splits(self, activity_id: str) -> dict[str, Any]:
            self.calls += 1
            return {"splits": [{"splitNumber": 1}]}

    client = GarminClient(MemoryStore("token"), Activities)
    assert client.read_activity_exercise_sets("42")["exerciseSets"]
    assert client.read_activity_splits("42")["splits"]
    api = client._api
    assert isinstance(api, Activities) and api.calls == 2


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GarminConnectAuthenticationError("401"), AuthenticationRequired),
        (GarminConnectTooManyRequestsError("429"), RateLimited),
    ],
)
def test_activity_exercise_read_errors_are_safe_and_not_retried(error, expected) -> None:
    class Broken(FakeAPI):
        calls = 0

        def get_activity_exercise_sets(self, activity_id: int | str) -> dict[str, Any]:
            self.calls += 1
            raise error

    client = GarminClient(MemoryStore("token"), Broken)
    with pytest.raises(expected):
        client.read_activity_exercise_sets("42")
    api = client._api
    assert isinstance(api, Broken) and api.calls == 1


def test_successful_account_login_discards_cached_health_reads() -> None:
    class AccountAPI(FakeAPI):
        def __init__(self, email: str = "old", *_: Any, **__: Any) -> None:
            super().__init__()
            self.email = email

        def get_stress_data(self, cdate: str) -> dict[str, str]:
            return {"account": self.email}

    client = GarminClient(MemoryStore(), AccountAPI)
    client.login("old", "secret", lambda: "1")
    assert client.read_stress("2026-08-12") == {"account": "old"}
    client.login("new", "secret", lambda: "1")
    assert client.read_stress("2026-08-12") == {"account": "new"}


def test_clear_session_discards_api_and_cached_reads() -> None:
    client = GarminClient(MemoryStore(), FakeAPI)
    client.login("old", "secret", lambda: "1")
    client._read_cache["example"] = (0, {"private": True})
    client.clear_session()
    assert client._api is None
    assert client._read_cache == {}


@pytest.mark.parametrize("method", [
    "has_body_composition", "has_body_composition_on_date", "has_blood_pressure",
])
@pytest.mark.parametrize("error,expected", [
    (GarminConnectAuthenticationError("401 private diagnostic"), AuthenticationRequired),
    (GarminConnectTooManyRequestsError("429 private diagnostic"), RateLimited),
    (RuntimeError("private diagnostic"), GarminSyncError),
])
def test_duplicate_reads_translate_vendor_errors(method, error, expected) -> None:
    class Broken(FakeAPI):
        def get_body_composition(self, *args):
            raise error

        def get_blood_pressure(self, *args):
            raise error

    client = GarminClient(MemoryStore("x" * 600), Broken)
    measured_at = datetime(2026, 8, 12, tzinfo=BERLIN)
    measurement = (
        BloodPressure(measured_at, 120, 80, 60) if method == "has_blood_pressure"
        else BodyComposition(measured_at, 80)
    )
    with pytest.raises(expected) as caught:
        getattr(client, method)(measurement)
    assert "private diagnostic" not in str(caught.value)


def test_profile_prefers_human_name_over_social_profile_uuid() -> None:
    class ProfileSession(FakeSession):
        def connectapi(self, _path: str) -> dict[str, str]:
            return {
                "displayName": "123e4567-e89b-42d3-a456-426614174000",
                "fullName": "Different Name",
            }

    class ProfileAPI(FakeAPI):
        def __init__(self, *_: Any, **__: Any) -> None:
            super().__init__()
            self.client = ProfileSession()

    client = GarminClient(MemoryStore("x" * 600), ProfileAPI)
    profile = client.profile()
    assert profile.display_name == "Test User"
    assert profile.initials == "TU"


@pytest.mark.parametrize(
    "error,expected",
    [
        (GarminConnectAuthenticationError("401"), AuthenticationRequired),
        (GarminConnectTooManyRequestsError("429"), RateLimited),
    ],
)
def test_login_translates_safe_errors(error: Exception, expected: type[Exception]) -> None:
    class Broken(FakeAPI):
        def login(self, tokenstore: str | None = None):
            raise error

    with pytest.raises(expected):
        GarminClient(MemoryStore(), Broken).login("a", "b", lambda: "1")


def test_body_upload_is_verified() -> None:
    client = GarminClient(MemoryStore("x" * 600), FakeAPI)
    item = BodyComposition(datetime(2026, 8, 13, tzinfo=BERLIN), 80)
    client.add_body_composition(item)


def test_body_upload_accepts_garmin_weight_in_grams() -> None:
    class Grams(FakeAPI):
        def get_body_composition(self, startdate: str, enddate: str | None = None):
            timestamp = datetime.fromisoformat(self.last_body_kwargs["timestamp"])
            return {
                "dateWeightList": [
                    {"weight": 80000.0, "timestampGMT": timestamp.timestamp() * 1000}
                ]
            }

    client = GarminClient(MemoryStore("x" * 600), Grams)
    client.add_body_composition(BodyComposition(datetime.now(BERLIN), 80))


def test_pressure_upload_is_verified() -> None:
    client = GarminClient(MemoryStore("x" * 600), FakeAPI)
    item = BloodPressure(datetime(2026, 8, 13, tzinfo=BERLIN), 120, 80, 60)
    client.add_blood_pressure(item)


def test_pressure_duplicate_requires_exact_timestamp() -> None:
    measured_at = datetime(2026, 8, 13, 8, 0, tzinfo=BERLIN)

    class Existing(FakeAPI):
        def __init__(self, *_: Any, **__: Any) -> None:
            super().__init__()
            other = measured_at.astimezone(UTC).replace(tzinfo=None, minute=1)
            self.pressure = {
                "measurements": [
                    {
                        "systolic": 120,
                        "diastolic": 80,
                        "pulse": 60,
                        "measurementTimestampGMT": other.isoformat(),
                    }
                ]
            }

    client = GarminClient(MemoryStore("x" * 600), Existing)
    assert not client.has_blood_pressure(BloodPressure(measured_at, 120, 80, 60))


def test_pressure_exact_duplicate_is_detected() -> None:
    measured_at = datetime(2026, 8, 13, 8, 0, tzinfo=BERLIN)

    class Existing(FakeAPI):
        def __init__(self, *_: Any, **__: Any) -> None:
            super().__init__()
            exact = measured_at.astimezone(UTC).replace(tzinfo=None)
            self.pressure = {
                "measurements": [
                    {
                        "systolic": 120,
                        "diastolic": 80,
                        "pulse": 60,
                        "measurementTimestampGMT": exact.isoformat(),
                    }
                ]
            }

    client = GarminClient(MemoryStore("x" * 600), Existing)
    assert client.has_blood_pressure(BloodPressure(measured_at, 120, 80, 60))


def test_unverified_upload_is_not_retried() -> None:
    class Missing(FakeAPI):
        def get_body_composition(self, startdate: str, enddate: str | None = None):
            return {}

    client = GarminClient(MemoryStore("x" * 600), Missing)
    with pytest.raises(UploadUncertain):
        client.add_body_composition(BodyComposition(datetime.now(BERLIN), 80))


def test_different_record_on_same_day_is_conflict_not_exact_match() -> None:
    measured_at = datetime(2026, 8, 6, 15, 27, 21, tzinfo=BERLIN)

    class Nearby(FakeAPI):
        def get_body_composition(self, startdate: str, enddate: str | None = None):
            return {
                "dateWeightList": [
                    {
                        "weight": 92790.0,
                        "timestampGMT": measured_at.timestamp() * 1000 + 52_000,
                    }
                ]
            }

    client = GarminClient(MemoryStore("x" * 600), Nearby)
    item = BodyComposition(measured_at, 92.7)
    assert not client.has_body_composition(item)
    assert client.has_body_composition_on_date(item)
