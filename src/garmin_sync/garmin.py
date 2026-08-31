from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic, sleep
from typing import Any, Protocol, TypeVar, cast
from uuid import UUID

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from .models import BloodPressure, BodyComposition
from .secrets import TokenStore

T = TypeVar("T")


class GarminSyncError(RuntimeError):
    """Safe, user-facing Garmin integration error."""


class AuthenticationRequired(GarminSyncError):
    pass


class RateLimited(GarminSyncError):
    pass


class UploadUncertain(GarminSyncError):
    """The write may have succeeded and must not be retried automatically."""


@dataclass(frozen=True, slots=True)
class GarminProfile:
    display_name: str
    initials: str
    avatar_url: str | None


class GarminAPI(Protocol):
    client: Any
    full_name: str | None

    def login(self, tokenstore: str | None = None) -> tuple[str | None, str | None]: ...
    def get_full_name(self) -> str | None: ...
    def add_body_composition(self, **kwargs: Any) -> dict[str, Any]: ...
    def set_blood_pressure(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_body_composition(
        self, startdate: str, enddate: str | None = None
    ) -> dict[str, Any]: ...
    def get_blood_pressure(self, startdate: str, enddate: str | None = None) -> dict[str, Any]: ...
    def get_activities_by_date(self, startdate: str, enddate: str) -> list[dict[str, Any]]: ...
    def get_activities(self, start: int = 0, limit: int = 20) -> Any: ...
    def get_stats_and_body(self, cdate: str) -> dict[str, Any]: ...
    def get_sleep_data(self, cdate: str) -> dict[str, Any]: ...
    def get_training_readiness(self, cdate: str) -> list[dict[str, Any]]: ...
    def get_training_status(self, cdate: str) -> dict[str, Any]: ...
    def get_body_battery(self, startdate: str, enddate: str) -> list[dict[str, Any]]: ...
    def get_stress_data(self, cdate: str) -> dict[str, Any]: ...
    def get_hrv_data(self, cdate: str) -> dict[str, Any] | None: ...
    def get_spo2_data(self, cdate: str) -> dict[str, Any]: ...
    def get_respiration_data(self, cdate: str) -> dict[str, Any]: ...
    def get_hydration_data(self, cdate: str) -> dict[str, Any]: ...
    def get_nutrition_daily_food_log(self, cdate: str) -> dict[str, Any]: ...
    def get_lifestyle_logging_data(self, cdate: str) -> dict[str, Any]: ...
    def get_all_day_events(self, cdate: str) -> dict[str, Any]: ...
    def get_activity_details(self, activity_id: str) -> dict[str, Any]: ...
    def get_endurance_score(self, startdate: str, enddate: str) -> dict[str, Any]: ...
    def get_hill_score(self, startdate: str, enddate: str) -> dict[str, Any]: ...
    def get_race_predictions(self, startdate: str, enddate: str) -> dict[str, Any]: ...
    def get_running_tolerance(
        self, startdate: str, enddate: str
    ) -> list[dict[str, Any]]: ...
    def get_devices(self) -> list[dict[str, Any]]: ...
    def get_goals(self) -> list[dict[str, Any]]: ...
    def get_personal_record(self) -> dict[str, Any]: ...
    def get_earned_badges(self) -> list[dict[str, Any]]: ...
    def get_training_plans(self) -> dict[str, Any]: ...
    def get_adhoc_challenges(self, start: int, limit: int) -> dict[str, Any]: ...
    def get_badge_challenges(self, start: int, limit: int) -> dict[str, Any]: ...
    def get_inprogress_virtual_challenges(self, start: int, limit: int) -> dict[str, Any]: ...
    def get_golf_summary(self, start: int = 0, limit: int = 100) -> list[dict[str, Any]]: ...
    def get_device_last_used(self) -> dict[str, Any]: ...


class GarminClient:
    def __init__(self, token_store: TokenStore, factory: Callable[..., GarminAPI] = Garmin) -> None:
        self._token_store = token_store
        self._factory = factory
        self._api: GarminAPI | None = None
        self._read_cache: dict[str, tuple[float, Any]] = {}

    def login(self, email: str, password: str, mfa_prompt: Callable[[], str]) -> str:
        api = self._factory(email, password, prompt_mfa=mfa_prompt)
        try:
            api.login()
            self._token_store.save(api.client.dumps())
            self._api = api
            return api.full_name or api.get_full_name() or email
        except Exception as exc:
            raise self._translate(exc, "Login failed") from exc

    def connect(self) -> str:
        token = self._token_store.load()
        if not token:
            raise AuthenticationRequired("No saved Garmin session. Run 'garmin-sync login'.")
        api = self._factory()
        try:
            api.login(token)
            self._token_store.save(api.client.dumps())
            self._api = api
            return api.full_name or api.get_full_name() or "Garmin user"
        except Exception as exc:
            raise self._translate(exc, "Saved Garmin session is no longer valid") from exc

    def profile(self) -> GarminProfile:
        """Read minimal profile data without exposing Garmin's image URL to the UI."""
        api = self._connected_api()
        try:
            raw = api.client.connectapi("/userprofile-service/socialProfile")
        except Exception as exc:
            raise self._translate(exc, "Could not read Garmin profile") from exc
        if not isinstance(raw, dict):
            raise GarminSyncError("Garmin returned an unreadable profile")
        display_name = _profile_display_name(
            api.full_name,
            raw.get("fullName"),
            raw.get("displayName"),
        )
        words = [word for word in display_name.split() if word]
        initials = "".join(word[0] for word in words[:2]).upper() or "G"
        avatar = raw.get("profileImageUrlMedium") or raw.get("profileImageUrlSmall")
        return GarminProfile(display_name, initials, avatar if isinstance(avatar, str) else None)

    def add_body_composition(self, measurement: BodyComposition) -> None:
        api = self._connected_api()
        try:
            upload = api.add_body_composition(**measurement.garmin_kwargs())
        except Exception as exc:
            raise self._translate_write(exc) from exc
        if not _upload_processed(upload):
            raise GarminSyncError("Garmin rejected the FIT file before creating a measurement")
        if not self._verify_body_upload(api, measurement):
            raise UploadUncertain(
                "Garmin processed the FIT file but did not return the exact timestamp and weight; "
                "check Garmin Connect before retrying"
            )

    @staticmethod
    def _verify_body_upload(api: GarminAPI, measurement: BodyComposition) -> bool:
        """Allow Garmin's read model to catch up without issuing another FIT upload."""
        for delay in (0, 1, 3):
            if delay:
                sleep(delay)
            try:
                data = api.get_body_composition(measurement.measured_at.date().isoformat())
            except Exception as exc:
                raise UploadUncertain(
                    "Upload returned, but verification failed; check Garmin Connect before retrying"
                ) from exc
            if _has_exact_body_record(data, measurement):
                return True
        return False

    def has_body_composition(self, measurement: BodyComposition) -> bool:
        api = self._connected_api()
        data = api.get_body_composition(measurement.measured_at.date().isoformat())
        return _has_exact_body_record(data, measurement)

    def has_body_composition_on_date(self, measurement: BodyComposition) -> bool:
        api = self._connected_api()
        data = api.get_body_composition(measurement.measured_at.date().isoformat())
        return bool(_body_records(data))

    def add_blood_pressure(self, measurement: BloodPressure) -> None:
        api = self._connected_api()
        if self.has_blood_pressure(measurement):
            return
        try:
            api.set_blood_pressure(
                systolic=measurement.systolic,
                diastolic=measurement.diastolic,
                pulse=measurement.pulse,
                timestamp=measurement.measured_at.isoformat(),
                notes=measurement.notes,
            )
        except Exception as exc:
            raise self._translate_write(exc) from exc
        try:
            data = api.get_blood_pressure(measurement.measured_at.date().isoformat())
        except Exception as exc:
            raise UploadUncertain(
                "Upload returned, but verification failed; check Garmin Connect before retrying"
            ) from exc
        if not _has_exact_pressure_record(data, measurement):
            raise UploadUncertain(
                "Garmin did not return the new pressure reading; "
                "check Garmin Connect before retrying"
            )

    def has_blood_pressure(self, measurement: BloodPressure) -> bool:
        api = self._connected_api()
        data = api.get_blood_pressure(measurement.measured_at.date().isoformat())
        return _has_exact_pressure_record(data, measurement)

    def read_activities(self, startdate: str, enddate: str) -> list[dict[str, Any]]:
        return self._read(lambda api: api.get_activities_by_date(startdate, enddate), "activities")

    def read_all_activities(self, *, page_size: int = 100) -> list[dict[str, Any]]:
        api = self._connected_api()
        result: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_pages: set[str] = set()
        start = 0
        while True:
            try:
                response = api.get_activities(start, page_size)
            except Exception as exc:
                raise self._translate(exc, "Could not read all-time activities") from exc
            page_value = (
                response.get("activityList", []) if isinstance(response, dict) else response
            )
            page = (
                [item for item in page_value if isinstance(item, dict)]
                if isinstance(page_value, list)
                else []
            )
            if not page:
                break
            signature = hashlib.sha256(
                json.dumps(page, sort_keys=True, default=str).encode()
            ).hexdigest()
            if signature in seen_pages:
                raise GarminSyncError("Garmin activity pagination did not advance")
            seen_pages.add(signature)
            new_items: list[dict[str, Any]] = []
            for item in page:
                activity_id = item.get("activityId")
                if activity_id is not None:
                    normalized_id = str(activity_id)
                    if normalized_id in seen_ids:
                        continue
                    seen_ids.add(normalized_id)
                new_items.append(item)
            if not new_items:
                raise GarminSyncError("Garmin activity pagination did not advance")
            result.extend(new_items)
            start += len(page)
            if len(page) < page_size:
                break
        return result

    def read_blood_pressure(self, startdate: str, enddate: str) -> dict[str, Any]:
        return self._read(lambda api: api.get_blood_pressure(startdate, enddate), "blood pressure")

    def read_body_composition(self, startdate: str, enddate: str) -> dict[str, Any]:
        return self._read(
            lambda api: api.get_body_composition(startdate, enddate), "body composition"
        )

    def read_daily_stats(self, cdate: str) -> dict[str, Any]:
        return self._read(lambda api: api.get_stats_and_body(cdate), "daily activity")

    def read_sleep(self, cdate: str) -> dict[str, Any]:
        return self._read(lambda api: api.get_sleep_data(cdate), "sleep")

    def read_training_readiness(self, cdate: str) -> list[dict[str, Any]]:
        return self._read(lambda api: api.get_training_readiness(cdate), "training readiness")

    def read_training_status(self, cdate: str) -> dict[str, Any]:
        return self._read(lambda api: api.get_training_status(cdate), "training status")

    def read_body_battery(self, startdate: str, enddate: str) -> list[dict[str, Any]]:
        return self._read(lambda api: api.get_body_battery(startdate, enddate), "Body Battery")

    def read_stress(self, cdate: str) -> dict[str, Any]:
        return self._cached(f"stress:{cdate}", lambda api: api.get_stress_data(cdate), "stress")

    def read_hrv(self, cdate: str) -> dict[str, Any] | None:
        return self._cached(f"hrv:{cdate}", lambda api: api.get_hrv_data(cdate), "HRV")

    def read_spo2(self, cdate: str) -> dict[str, Any]:
        return self._cached(f"spo2:{cdate}", lambda api: api.get_spo2_data(cdate), "SpO2")

    def read_respiration(self, cdate: str) -> dict[str, Any]:
        return self._cached(
            f"respiration:{cdate}", lambda api: api.get_respiration_data(cdate), "respiration"
        )

    def read_hydration(self, cdate: str) -> dict[str, Any]:
        return self._cached(
            f"hydration:{cdate}", lambda api: api.get_hydration_data(cdate), "hydration"
        )

    def read_nutrition(self, cdate: str) -> dict[str, Any]:
        return self._cached(
            f"nutrition:{cdate}",
            lambda api: api.get_nutrition_daily_food_log(cdate),
            "nutrition",
        )

    def read_lifestyle(self, cdate: str) -> dict[str, Any]:
        return self._cached(
            f"lifestyle:{cdate}",
            lambda api: api.get_lifestyle_logging_data(cdate),
            "lifestyle logging",
        )

    def read_daily_events(self, cdate: str) -> dict[str, Any]:
        return self._cached(
            f"events:{cdate}", lambda api: api.get_all_day_events(cdate), "daily events"
        )

    def read_activity_detail(self, activity_id: str) -> dict[str, Any]:
        return self._cached(
            f"activity:{activity_id}",
            lambda api: api.get_activity_details(activity_id),
            "activity details",
        )

    def read_extended(self, startdate: str, enddate: str) -> tuple[dict[str, Any], list[str]]:
        operations: dict[str, Callable[[GarminAPI], Any]] = {
            "endurance_score": lambda api: api.get_endurance_score(startdate, enddate),
            "hill_score": lambda api: api.get_hill_score(startdate, enddate),
            "race_predictions": lambda api: api.get_race_predictions(startdate, enddate),
            "running_tolerance": lambda api: api.get_running_tolerance(startdate, enddate),
            "devices": lambda api: api.get_devices(),
            "goals": lambda api: api.get_goals(),
            "personal_records": lambda api: api.get_personal_record(),
            "badges": lambda api: api.get_earned_badges(),
            "training_plans": lambda api: api.get_training_plans(),
            "adhoc_challenges": lambda api: api.get_adhoc_challenges(0, 100),
            "badge_challenges": lambda api: api.get_badge_challenges(0, 100),
            "virtual_challenges": lambda api: api.get_inprogress_virtual_challenges(0, 100),
            "golf": lambda api: api.get_golf_summary(0, 100),
            "last_used_device": lambda api: api.get_device_last_used(),
        }
        values: dict[str, Any] = {}
        unavailable: list[str] = []
        for name, operation in operations.items():
            try:
                values[name] = self._cached(
                    f"extended:{name}:{startdate}:{enddate}", operation, name
                )
            except (AuthenticationRequired, RateLimited):
                raise
            except GarminSyncError:
                unavailable.append(name)
        return values, unavailable

    def _cached(self, key: str, operation: Callable[[GarminAPI], T], section: str) -> T:
        cached = self._read_cache.get(key)
        if cached is not None and monotonic() - cached[0] < 900:
            return cast(T, cached[1])
        value = self._read(operation, section)
        self._read_cache[key] = (monotonic(), value)
        return value

    def _read(self, operation: Callable[[GarminAPI], T], section: str) -> T:
        api = self._connected_api()
        try:
            return operation(api)
        except Exception as exc:
            raise self._translate(exc, f"Could not read Garmin {section}") from exc

    def _connected_api(self) -> GarminAPI:
        if self._api is None:
            self.connect()
        if self._api is None:
            raise AuthenticationRequired("Garmin session is unavailable. Run 'garmin-sync login'.")
        return self._api

    @staticmethod
    def _translate(exc: Exception, prefix: str) -> GarminSyncError:
        if isinstance(exc, GarminConnectTooManyRequestsError) or "429" in str(exc):
            return RateLimited("Garmin rate-limited login. Wait before trying again.")
        if isinstance(exc, GarminConnectAuthenticationError) or "401" in str(exc):
            return AuthenticationRequired(f"{prefix}. Run 'garmin-sync login'.")
        if isinstance(exc, GarminConnectConnectionError):
            return GarminSyncError(f"{prefix} because Garmin Connect could not be reached")
        return GarminSyncError(prefix)

    def _translate_write(self, exc: Exception) -> GarminSyncError:
        translated = self._translate(exc, "Garmin rejected the request")
        if isinstance(translated, AuthenticationRequired | RateLimited):
            return translated
        return UploadUncertain("The upload result is unknown; check Garmin Connect before retrying")


def _profile_display_name(*candidates: Any) -> str:
    """Prefer Garmin's human name and never expose its opaque profile UUID."""
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        value = candidate.strip()
        if not value:
            continue
        try:
            UUID(value)
        except ValueError:
            return value
    return "Garmin user"


def _body_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    records = data.get("dateWeightList", [])
    return [record for record in records if isinstance(record, dict)]


def _has_exact_body_record(data: dict[str, Any], measurement: BodyComposition) -> bool:
    target_ms = measurement.measured_at.timestamp() * 1000
    target_grams = measurement.weight * 1000
    return any(
        abs(float(record.get("timestampGMT", -1)) - target_ms) <= 2_000
        and abs(float(record.get("weight", -1)) - target_grams) <= 50
        for record in _body_records(data)
    )


def _upload_processed(upload: dict[str, Any]) -> bool:
    result = upload.get("detailedImportResult", upload)
    if not isinstance(result, dict) or result.get("failures"):
        return False
    successes = result.get("successes")
    return successes is None or bool(successes)


def _contains_mapping(value: Any, expected: dict[str, int]) -> bool:
    """Find one nested record containing all expected fields and values."""
    if isinstance(value, dict):
        normalized = {str(key).lower(): item for key, item in value.items()}
        if all(normalized.get(key) == item for key, item in expected.items()):
            return True
        return any(_contains_mapping(item, expected) for item in value.values())
    if isinstance(value, list | tuple):
        return any(_contains_mapping(item, expected) for item in value)
    return False


def _pressure_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        records: list[dict[str, Any]] = []
        if {"systolic", "diastolic", "pulse"} <= {str(key) for key in value}:
            records.append(value)
        for item in value.values():
            records.extend(_pressure_records(item))
        return records
    if isinstance(value, list | tuple):
        return [record for item in value for record in _pressure_records(item)]
    return []


def _has_exact_pressure_record(data: dict[str, Any], measurement: BloodPressure) -> bool:
    target = measurement.measured_at.timestamp()
    for record in _pressure_records(data):
        raw_timestamp = record.get("measurementTimestampGMT")
        if not isinstance(raw_timestamp, str):
            continue
        try:
            timestamp = datetime.fromisoformat(raw_timestamp).replace(tzinfo=UTC).timestamp()
        except ValueError:
            continue
        if (
            abs(timestamp - target) <= 1
            and record.get("systolic") == measurement.systolic
            and record.get("diastolic") == measurement.diastolic
            and record.get("pulse") == measurement.pulse
        ):
            return True
    return False
