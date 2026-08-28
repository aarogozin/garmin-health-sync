from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, TypeVar

import requests
from renpho import RenphoAPIError
from renpho import RenphoClient as CloudClient
from renpho.crypto import decrypt_response, encrypt_request

from .models import BERLIN, BodyComposition, ValidationError
from .renpho_report import RenphoReportData, normalize_report

T = TypeVar("T")


class RenphoError(RuntimeError):
    """Safe user-facing RENPHO integration error."""


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

    def fetch(self) -> tuple[list[RenphoMeasurement], int]:
        raw_items = self._fetch_measurements()

        result: list[RenphoMeasurement] = []
        skipped = 0
        for raw in raw_items:
            try:
                result.append(normalize_measurement(raw))
            except (TypeError, ValueError, ValidationError):
                skipped += 1
        return sorted(result, key=lambda item: item.body.measured_at, reverse=True), skipped

    def _fetch_measurements(self) -> list[dict[str, Any]]:
        return self._read_with_reauth(
            lambda api: api.get_all_measurements(),
            "RENPHO rejected the refreshed measurement session",
            request_error="Could not download measurements from RENPHO",
            response_error="RENPHO returned an unreadable measurement response",
        )

    def _read_with_reauth(
        self,
        operation: Callable[[RenphoAPI], T],
        rejected_message: str,
        *,
        request_error: str = "Could not read data from RENPHO",
        response_error: str = "RENPHO returned unreadable data",
    ) -> T:
        """Retry one rejected *read* with a fresh session, never a cloud write."""
        for attempt in range(2):
            api = self.authenticate()
            try:
                return operation(api)
            except RenphoAPIError as exc:
                if attempt == 0:
                    self._api = None
                    continue
                raise RenphoError(rejected_message) from exc
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in {401, 403} and attempt == 0:
                    self._api = None
                    continue
                if status == 429:
                    raise RenphoError(
                        "RENPHO rate-limited the request; wait before retrying"
                    ) from exc
                if status in {401, 403}:
                    raise RenphoError(rejected_message) from exc
                raise RenphoError(request_error) from exc
            except requests.RequestException as exc:
                raise RenphoError(request_error) from exc
            except Exception as exc:
                raise RenphoError(response_error) from exc
        raise RenphoError(response_error)

    def girth_record_count(self) -> int | None:
        """Return RENPHO's cloud-side girth count without exposing record contents."""
        value = self._read_with_reauth(
            lambda api: api.get_device_info().get("girth"),
            "RENPHO rejected the refreshed device session",
            request_error="Could not read RENPHO device metadata",
            response_error="RENPHO returned unreadable device metadata",
        )
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def fetch_girth(self) -> list[RenphoGirthMeasurement]:
        """Read circumference history from RENPHO's undocumented app endpoint."""
        def fetch(api: RenphoAPI) -> Any:
            if api.user_id is None:
                raise RenphoError("RENPHO login returned no user identifier")
            result = api._post(
                "RenphoHealth/renpho/girth/queryAllGirthsDataList",
                encrypt_request({"userId": str(api.user_id)}),
            )
            return decrypt_response(result["data"])

        raw_items = self._read_with_reauth(
            fetch,
            "RENPHO rejected the refreshed body-measurement session",
            request_error="Could not download body measurements from RENPHO",
            response_error="RENPHO returned unreadable body measurements",
        )
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
