from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import requests
from renpho import RenphoClient as CloudClient
from renpho.crypto import decrypt_response, encrypt_request

from .activities import RenphoActivityRecord, RenphoActivityTemplate
from .models import BERLIN, BodyComposition, ValidationError
from .renpho_report import RenphoReportData, normalize_report


class RenphoError(RuntimeError):
    """Safe user-facing RENPHO integration error."""


class RenphoWriteUncertain(RenphoError):
    """RENPHO may have accepted a write, so it must not be retried automatically."""


class RenphoCredentials(Protocol):
    def load(self) -> tuple[str, str] | None: ...


class SuppliedCredentials:
    def __init__(self, email: str, password: str) -> None:
        self._value = (email, password)

    def load(self) -> tuple[str, str]:
        return self._value


class RenphoAPI(Protocol):
    user_id: int | str | None

    def login(self) -> dict[str, Any]: ...
    def get_device_info(self) -> dict[str, Any]: ...
    def get_all_measurements(self) -> list[dict[str, Any]]: ...
    def _post(self, endpoint: str, body: dict[str, Any]) -> dict[str, Any]: ...


class RenphoMeasurement:
    __slots__ = ("source_id", "body", "report")

    def __init__(
        self,
        source_id: str,
        body: BodyComposition,
        report: RenphoReportData | None = None,
    ) -> None:
        self.source_id = source_id
        self.body = body
        self.report = report


@dataclass(frozen=True, slots=True)
class GirthValue:
    label: str
    value: float
    unit: str


@dataclass(frozen=True, slots=True)
class RenphoGirthMeasurement:
    measured_at: datetime
    values: tuple[GirthValue, ...]


class TimeoutSession(requests.Session):
    """Bound cloud calls so a vendor outage cannot hang the CLI forever."""

    def request(  # type: ignore[override]
        self, method: str, url: str, **kwargs: Any
    ) -> requests.Response:
        kwargs.setdefault("timeout", (10, 30))
        return super().request(method, url, **kwargs)


def _safe_client(email: str, password: str, *, debug: bool = False) -> RenphoAPI:
    client = CloudClient(email, password, debug=debug)
    client._transport.session = TimeoutSession()  # noqa: SLF001 -- upstream has no timeout hook
    return client


class RenphoCloud:
    def __init__(
        self,
        credentials: RenphoCredentials,
        factory: Callable[..., RenphoAPI] = _safe_client,
    ) -> None:
        self._credentials = credentials
        self._factory = factory
        self._api: RenphoAPI | None = None

    def authenticate(self) -> RenphoAPI:
        if self._api is not None:
            return self._api
        credentials = self._credentials.load()
        if not credentials:
            raise RenphoError("No saved RENPHO credentials. Run 'garmin-sync renpho login'.")
        email, password = credentials
        api = self._factory(email, password, debug=False)
        try:
            api.login()
            transport = getattr(api, "_transport", None)
            session = getattr(transport, "session", None)
            if session is not None:
                session.headers.setdefault("language", "en")
                session.headers.setdefault("timeZone", str(BERLIN))
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in {401, 403}:
                raise RenphoError("RENPHO rejected the saved credentials") from exc
            if status == 429:
                raise RenphoError("RENPHO rate-limited the request; wait before retrying") from exc
            raise RenphoError("RENPHO cloud could not be reached") from exc
        except requests.RequestException as exc:
            raise RenphoError("RENPHO cloud could not be reached") from exc
        except Exception as exc:
            raise RenphoError("RENPHO login failed") from exc
        self._api = api
        return api

    def fetch_activity_templates(self) -> tuple[RenphoActivityTemplate, ...]:
        raw = self._activity_call(
            "RenphoHealth/healthManage/selectActivityTemplate", {}, write=False
        )
        templates: list[RenphoActivityTemplate] = []
        for item in _activity_items(raw):
            template_id = _first_int(item, "sportTypeId", "id", "activityId")
            name = _first_text(item, "title", "sportName", "name", "activityName")
            if template_id is not None and name:
                official = _first_int(item, "isOfficial")
                templates.append(
                    RenphoActivityTemplate(template_id, name, 1 if official is None else official)
                )
        if not templates:
            raise RenphoError("RENPHO returned no readable activity templates")
        return tuple(templates)

    def fetch_activities(self) -> tuple[RenphoActivityRecord, ...]:
        raw = self._activity_call("RenphoHealth/healthManage/getActivity", {}, write=False)
        records: list[RenphoActivityRecord] = []
        for item in _activity_items(raw):
            template_id = _first_int(item, "sportTypeId", "activityId")
            record_time = _first_int(item, "recordTime", "timeStamp")
            duration = _first_int(item, "duration")
            calories = _first_int(item, "cal", "calories")
            if (
                template_id is None
                or record_time is None
                or duration is None
                or calories is None
            ):
                continue
            seconds = record_time / 1000 if record_time > 10_000_000_000 else record_time
            records.append(
                RenphoActivityRecord(
                    _first_text(item, "id", "recordId"),
                    template_id,
                    datetime.fromtimestamp(seconds, tz=BERLIN),
                    duration,
                    calories,
                )
            )
        return tuple(records)

    def create_activity(
        self,
        *,
        template: RenphoActivityTemplate,
        started_at: datetime,
        duration_seconds: int,
        calories: int,
    ) -> str | None:
        raw = self._activity_call(
            "RenphoHealth/healthManage/recordActivity",
            {
                "duration": duration_seconds,
                "sportTypeId": template.template_id,
                "isOfficial": template.is_official,
                "cal": calories,
                "recordTime": int(started_at.timestamp() * 1000),
            },
            write=True,
        )
        return _first_text(raw, "id", "recordId") if isinstance(raw, dict) else None

    def _activity_call(self, endpoint: str, payload: dict[str, Any], *, write: bool) -> Any:
        api = self.authenticate()
        if api.user_id is None:
            raise RenphoError("RENPHO login returned no user identifier")
        body = {"userId": str(api.user_id), **payload}
        try:
            response = api._post(endpoint, encrypt_request(body))
            code = response.get("code") if isinstance(response, dict) else None
            if code not in {None, 101, "101"}:
                raise RenphoError("RENPHO rejected the activity request")
            data = response.get("data") if isinstance(response, dict) else None
            if isinstance(data, str):
                return decrypt_response(data)
            return data if data is not None else response
        except RenphoError:
            raise
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in {401, 403}:
                raise RenphoError("RENPHO rejected the saved credentials") from exc
            if status == 429:
                raise RenphoError("RENPHO rate-limited the request; wait before retrying") from exc
            if write:
                raise RenphoWriteUncertain(
                    "RENPHO activity upload may have succeeded; check RENPHO before retrying"
                ) from exc
            raise RenphoError("Could not read RENPHO activities") from exc
        except Exception as exc:
            if write:
                raise RenphoWriteUncertain(
                    "RENPHO returned an unreadable upload response; check RENPHO before retrying"
                ) from exc
            raise RenphoError("RENPHO returned unreadable activity data") from exc

    def fetch(self) -> tuple[list[RenphoMeasurement], int]:
        api = self.authenticate()
        try:
            raw_items = api.get_all_measurements()
        except requests.RequestException as exc:
            raise RenphoError("Could not download measurements from RENPHO") from exc
        except Exception as exc:
            raise RenphoError("RENPHO returned an unreadable measurement response") from exc

        result: list[RenphoMeasurement] = []
        skipped = 0
        for raw in raw_items:
            try:
                result.append(normalize_measurement(raw))
            except (TypeError, ValueError, ValidationError):
                skipped += 1
        return sorted(result, key=lambda item: item.body.measured_at, reverse=True), skipped

    def girth_record_count(self) -> int | None:
        """Return RENPHO's cloud-side girth count without exposing record contents."""
        api = self.authenticate()
        try:
            value = api.get_device_info().get("girth")
        except requests.RequestException as exc:
            raise RenphoError("Could not read RENPHO device metadata") from exc
        except Exception as exc:
            raise RenphoError("RENPHO returned unreadable device metadata") from exc
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def fetch_girth(self) -> list[RenphoGirthMeasurement]:
        """Read circumference history from RENPHO's undocumented app endpoint."""
        api = self.authenticate()
        if api.user_id is None:
            raise RenphoError("RENPHO login returned no user identifier")
        try:
            # Upstream does not expose the tape endpoint, so the adapter uses its
            # authenticated/encrypted transport while keeping it out of UI code.
            result = api._post(
                "RenphoHealth/renpho/girth/queryAllGirthsDataList",
                encrypt_request({"userId": str(api.user_id)}),
            )
            raw_items = decrypt_response(result["data"])
        except requests.RequestException as exc:
            raise RenphoError("Could not download body measurements from RENPHO") from exc
        except Exception as exc:
            raise RenphoError("RENPHO returned unreadable body measurements") from exc
        if not isinstance(raw_items, list):
            raise RenphoError("RENPHO returned unreadable body measurements")
        measurements: list[RenphoGirthMeasurement] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                measurements.append(normalize_girth(raw))
            except (TypeError, ValueError, ValidationError):
                continue
        return sorted(measurements, key=lambda item: item.measured_at, reverse=True)


def normalize_measurement(raw: dict[str, Any]) -> RenphoMeasurement:
    weight = _required_float(raw, "weight")
    measured_at = _timestamp(raw)
    muscle_percent = _optional_float(raw, "muscle")
    bone_percent = _optional_float(raw, "bone")
    body = BodyComposition(
        measured_at=measured_at,
        weight=weight,
        bmi=_optional_float(raw, "bmi"),
        percent_fat=_optional_float(raw, "bodyfat"),
        percent_hydration=_optional_float(raw, "water"),
        muscle_mass=round(weight * muscle_percent / 100, 2) if muscle_percent else None,
        bone_mass=round(weight * bone_percent / 100, 2) if bone_percent else None,
        basal_met=_optional_float(raw, "bmr"),
        visceral_fat_rating=_optional_float(raw, "visfat"),
        metabolic_age=_optional_float(raw, "bodyage"),
    )
    raw_id = raw.get("id")
    source_id = str(raw_id) if raw_id is not None else _stable_id(raw, body)
    return RenphoMeasurement(source_id, body, normalize_report(raw, measured_at))


def _activity_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    for key in ("list", "records", "activityList", "data", "rows"):
        nested = value.get(key)
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    return []


def _first_int(raw: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, bool) or value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _first_text(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


GIRTH_FIELDS = (
    ("neck", "Neck"),
    ("shoulder", "Shoulders"),
    ("chest", "Chest"),
    ("waist", "Waist"),
    ("abdomen", "Abdomen"),
    ("hip", "Hips"),
    ("leftArm", "Left arm"),
    ("rightArm", "Right arm"),
    ("leftThigh", "Left thigh"),
    ("rightThigh", "Right thigh"),
    ("leftCalf", "Left calf"),
    ("rightCalf", "Right calf"),
    ("arm", "Arm"),
    ("thigh", "Thigh"),
    ("calf", "Calf"),
)


def normalize_girth(raw: dict[str, Any]) -> RenphoGirthMeasurement:
    measured_at = _timestamp(raw)
    values: list[GirthValue] = []
    for prefix, label in GIRTH_FIELDS:
        value = _optional_float(raw, f"{prefix}Value")
        if value is None or value <= 0:
            continue
        unit_code = raw.get(f"{prefix}Unit", raw.get("measureUnit", 0))
        unit = "in" if unit_code == 1 else "cm"
        values.append(GirthValue(label, value, unit))
    whr = _optional_float(raw, "whrValue")
    if whr is not None and whr > 0:
        values.append(GirthValue("Waist-to-hip ratio", whr, "ratio"))
    if not values:
        raise ValidationError("RENPHO body measurement has no values")
    return RenphoGirthMeasurement(measured_at, tuple(values))


def _timestamp(raw: dict[str, Any]) -> datetime:
    value = raw.get("timeStamp") or raw.get("time_stamp")
    if value is None:
        raise ValidationError("RENPHO measurement has no timestamp")
    timestamp = float(value)
    if timestamp > 1_000_000_000_000:
        timestamp /= 1000
    return datetime.fromtimestamp(timestamp, tz=BERLIN)


def _required_float(raw: dict[str, Any], key: str) -> float:
    value = _optional_float(raw, key)
    if value is None:
        raise ValidationError(f"RENPHO measurement has no {key}")
    return value


def _optional_float(raw: dict[str, Any], key: str) -> float | None:
    value = raw.get(key)
    if value is None or value == "":
        return None
    return float(value)


def _stable_id(raw: dict[str, Any], body: BodyComposition) -> str:
    material = json.dumps(
        {"timestamp": body.measured_at.isoformat(), "weight": body.weight, "raw": raw},
        sort_keys=True,
        default=str,
    ).encode()
    return hashlib.sha256(material).hexdigest()
