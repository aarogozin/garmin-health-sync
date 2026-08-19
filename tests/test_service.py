from datetime import datetime

import pytest

from garmin_sync.garmin import (
    AuthenticationRequired,
    GarminSyncError,
    RateLimited,
    UploadUncertain,
)
from garmin_sync.models import BERLIN, BloodPressure, BodyComposition
from garmin_sync.renpho import RenphoMeasurement
from garmin_sync.service import HealthSyncService, ResultStatus


class State:
    def __init__(self) -> None:
        self.ids: set[str] = set()

    def synced_ids(self) -> set[str]:
        return set(self.ids)

    def mark_synced(self, value: str) -> None:
        self.ids.add(value)


class Cloud:
    def __init__(self, items=None) -> None:
        self.items = items or []

    def fetch(self):
        return self.items, 0


class Garmin:
    def __init__(self) -> None:
        self.pressure_exists = False
        self.body_exists = False
        self.body_conflict = False
        self.fail_uncertain = False

    def connect(self) -> str:
        return "Test User"

    def has_blood_pressure(self, measurement) -> bool:
        return self.pressure_exists

    def add_blood_pressure(self, measurement) -> None:
        if self.fail_uncertain:
            raise UploadUncertain("check Garmin")

    def has_body_composition(self, measurement) -> bool:
        return self.body_exists

    def has_body_composition_on_date(self, measurement) -> bool:
        return self.body_conflict

    def add_body_composition(self, measurement) -> None:
        if self.fail_uncertain:
            raise UploadUncertain("check Garmin")

    def read_activities(self, startdate, enddate):
        return []

    def read_blood_pressure(self, startdate, enddate):
        return {}

    def read_body_composition(self, startdate, enddate):
        return {}

    def read_training_status(self, enddate):
        return {}

    def read_body_battery(self, startdate, enddate):
        return []

    def read_daily_stats(self, cdate):
        return {}

    def read_sleep(self, cdate):
        return {}

    def read_training_readiness(self, cdate):
        return []


def service(garmin=None, items=None):
    return HealthSyncService(garmin or Garmin(), Cloud(items), State())  # type: ignore[arg-type]


def test_pressure_duplicate_is_not_uploaded() -> None:
    garmin = Garmin()
    garmin.pressure_exists = True
    result = service(garmin).add_pressure(
        BloodPressure(datetime(2026, 8, 13, tzinfo=BERLIN), 120, 80, 60)
    )
    assert result.status == ResultStatus.ALREADY_EXISTS


def test_pressure_uncertain_is_preserved() -> None:
    garmin = Garmin()
    garmin.fail_uncertain = True
    result = service(garmin).add_pressure(
        BloodPressure(datetime(2026, 8, 13, tzinfo=BERLIN), 120, 80, 60)
    )
    assert result.status == ResultStatus.UNCERTAIN


def test_renpho_history_keeps_latest_per_day() -> None:
    day = datetime(2026, 8, 13, tzinfo=BERLIN)
    items = [
        RenphoMeasurement("new", BodyComposition(day.replace(hour=9), 79)),
        RenphoMeasurement("old", BodyComposition(day.replace(hour=8), 80)),
    ]
    preview = service(items=items).preview_renpho("all")
    assert [item.source_id for item in preview.candidates] == ["new"]


def test_renpho_conflict_is_reported_without_marking_synced() -> None:
    garmin = Garmin()
    garmin.body_conflict = True
    item = RenphoMeasurement("record", BodyComposition(datetime(2026, 8, 13, tzinfo=BERLIN), 80))
    app = service(garmin, [item])
    preview = app.preview_renpho("latest")
    result = app.sync_renpho(preview)
    assert result[0].status == ResultStatus.CONFLICT
    assert app.state.synced_ids() == set()


@pytest.mark.parametrize(
    "error,expected",
    [
        (AuthenticationRequired("login"), ResultStatus.AUTH_REQUIRED),
        (RateLimited("wait"), ResultStatus.RATE_LIMITED),
        (GarminSyncError("offline"), ResultStatus.ERROR),
    ],
)
def test_weekly_report_preserves_terminal_garmin_status(
    error: Exception, expected: ResultStatus
) -> None:
    class Broken(Garmin):
        def connect(self) -> str:
            raise error

    result = service(Broken()).build_weekly_report(datetime(2026, 8, 15).date())
    assert result.status == expected
    assert result.pdf.startswith(b"%PDF-")
    assert "renpho" in result.report.availability.available
