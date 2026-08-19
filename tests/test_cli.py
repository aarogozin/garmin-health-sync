from datetime import datetime, timedelta

from garmin_sync.cli import _confirm, body_wizard, pressure_wizard, renpho_sync
from garmin_sync.models import BERLIN, BodyComposition
from garmin_sync.renpho import RenphoMeasurement
from garmin_sync.state import SyncState


def answers(values: list[str]):
    iterator = iter(values)
    return lambda _: next(iterator)


def test_body_wizard_allows_optional_fields() -> None:
    item = body_wizard(answers(["2026-08-13 08:30", "80", "20", "", "", "", "", "", "", ""]))
    assert item.weight == 80
    assert item.percent_fat == 20
    assert item.bmi is None


def test_pressure_wizard() -> None:
    item = pressure_wizard(answers(["2026-08-13 08:30", "120", "80", "60", "morning"]))
    assert (item.systolic, item.diastolic, item.pulse) == (120, 80, 60)


def test_confirmation_defaults_to_cancel() -> None:
    assert not _confirm("", answers([""]))
    assert not _confirm("", answers(["no"]))
    assert _confirm("", answers(["yes"]))


class FakeGarmin:
    def __init__(self) -> None:
        self.uploaded: list[BodyComposition] = []

    def connect(self) -> str:
        return "Test User"

    def add_body_composition(self, item: BodyComposition) -> None:
        self.uploaded.append(item)

    def has_body_composition(self, item: BodyComposition) -> bool:
        return False

    def has_body_composition_on_date(self, item: BodyComposition) -> bool:
        return False


class FakeCloud:
    def __init__(self, measurements: list[RenphoMeasurement]) -> None:
        self.measurements = measurements

    def fetch(self) -> tuple[list[RenphoMeasurement], int]:
        return self.measurements, 0


def _renpho_items() -> list[RenphoMeasurement]:
    now = datetime(2026, 8, 13, tzinfo=BERLIN)
    return [
        RenphoMeasurement("new", BodyComposition(now, 79)),
        RenphoMeasurement("old", BodyComposition(now - timedelta(days=1), 80)),
    ]


def test_renpho_latest_uploads_only_newest(tmp_path) -> None:
    garmin = FakeGarmin()
    state = SyncState(tmp_path / "state.json")
    result = renpho_sync(garmin, FakeCloud(_renpho_items()), state, "latest", answers(["yes"]))
    assert result == 0
    assert [item.weight for item in garmin.uploaded] == [79]
    assert state.synced_ids() == {"new"}


def test_renpho_all_uploads_oldest_first_and_skips_synced(tmp_path) -> None:
    garmin = FakeGarmin()
    state = SyncState(tmp_path / "state.json")
    state.mark_synced("old")
    result = renpho_sync(garmin, FakeCloud(_renpho_items()), state, "all", answers(["yes"]))
    assert result == 0
    assert [item.weight for item in garmin.uploaded] == [79]


def test_renpho_sync_can_be_cancelled(tmp_path) -> None:
    garmin = FakeGarmin()
    result = renpho_sync(
        garmin,
        FakeCloud(_renpho_items()),
        SyncState(tmp_path / "state.json"),
        "all",
        answers(["no"]),
    )
    assert result == 0
    assert garmin.uploaded == []


def test_renpho_all_keeps_only_latest_measurement_per_day(tmp_path) -> None:
    garmin = FakeGarmin()
    now = datetime(2026, 8, 13, 8, 0, tzinfo=BERLIN)
    items = [
        RenphoMeasurement("latest", BodyComposition(now, 79)),
        RenphoMeasurement("earlier", BodyComposition(now - timedelta(minutes=10), 80)),
    ]
    result = renpho_sync(
        garmin,
        FakeCloud(items),
        SyncState(tmp_path / "state.json"),
        "all",
        answers(["yes"]),
    )
    assert result == 0
    assert [item.weight for item in garmin.uploaded] == [79]
