from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GarminLoginRequest(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class MfaRequest(ApiModel):
    job_id: str = Field(min_length=16, max_length=64)
    code: str = Field(min_length=4, max_length=16, pattern=r"^[0-9A-Za-z-]+$")


class RenphoLoginRequest(ApiModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class PressureRequest(ApiModel):
    measured_at: datetime
    systolic: int = Field(ge=70, le=260)
    diastolic: int = Field(ge=40, le=150)
    pulse: int = Field(ge=20, le=250)
    notes: str = Field(default="", max_length=500)


class SyncPreviewRequest(ApiModel):
    mode: Literal["latest", "all"]


class WeeklyReportRequest(ApiModel):
    include_routes: bool = False
    map_tiles_enabled: bool = False


class DashboardRefreshRequest(ApiModel):
    period_days: Literal[1, 7, 30] = 7


class ScheduleRequest(ApiModel):
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)


class ApiError(ApiModel):
    code: str
    message: str


class ApiEnvelope(ApiModel):
    status: str
    data: dict[str, Any] | list[Any] | None = None
    error: ApiError | None = None


def exported_schema() -> dict[str, Any]:
    models = (
        GarminLoginRequest,
        MfaRequest,
        RenphoLoginRequest,
        PressureRequest,
        SyncPreviewRequest,
        WeeklyReportRequest,
        DashboardRefreshRequest,
        ScheduleRequest,
        ApiEnvelope,
    )
    definitions: dict[str, Any] = {}
    for model in models:
        schema = model.model_json_schema(ref_template="#/$defs/{model}")
        definitions.update(schema.pop("$defs", {}))
        definitions[model.__name__] = schema
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "GarminHealthSyncApi",
        "$defs": definitions,
    }
