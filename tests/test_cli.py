import argparse
from datetime import datetime, timedelta

import pytest

from garmin_sync.cli import (
    _choice,
    _confirm,
    _float_prompt,
    _int_prompt,
    add_command,
    body_wizard,
    daily_sync,
    login_command,
    logout_command,
    main,
    pressure_wizard,
    renpho_sync,
    schedule_command,
)
from garmin_sync.garmin import GarminSyncError, UploadUncertain
from garmin_sync.models import BERLIN, BloodPressure, BodyComposition, ValidationError
from garmin_sync.renpho import RenphoError, RenphoMeasurement
from garmin_sync.service import OperationResult, RenphoPreview, ResultStatus
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


def test_daily_sync_stops_after_weight_failure(monkeypatch, tmp_path) -> None:
    calls: list[str] = []

    class DailyService:
        def __init__(self, *args) -> None:
            pass

        def preview_renpho(self, mode: str):
            calls.append("weight")
            raise RenphoError("weight failed")

        def sync_renpho(self, preview):
            raise AssertionError("weight sync should not run")

    monkeypatch.setattr("garmin_sync.cli.HealthSyncService", DailyService)
    result = daily_sync(object(), object(), SyncState(tmp_path / "state.json"))  # type: ignore[arg-type]
    assert result == 2
    assert calls == ["weight"]


def test_daily_sync_output_excludes_health_values(monkeypatch, tmp_path, capsys) -> None:
    secret_name = "Private Evening Run"
    secret_date = "2026-08-22"

    class DailyService:
        def __init__(self, *args) -> None:
            pass

        def preview_renpho(self, mode: str):
            return object()

        def sync_renpho(self, preview):
            return [OperationResult(ResultStatus.SUCCESS, f"{secret_date}: uploaded")]

    monkeypatch.setattr("garmin_sync.cli.HealthSyncService", DailyService)
    assert daily_sync(object(), object(), SyncState(tmp_path / "state.json")) == 0  # type: ignore[arg-type]
    output = capsys.readouterr().out
    assert secret_name not in output
    assert secret_date not in output
    assert "700" not in output
    assert "3600" not in output
    assert "weight sync: success" in output


def test_numeric_prompts_retry_invalid_values(capsys) -> None:
    assert _float_prompt("", answers(["bad", "12,5"]), required=True) == 12.5
    assert _float_prompt("", answers(["bad", ""])) is None
    assert _int_prompt("", answers(["", "bad", "42"])) == 42
    assert _choice("", {"a", "b"}, answers(["x", "b"])) == "b"
    output = capsys.readouterr().out
    assert "Enter a number." in output
    assert "Enter a number or leave it blank." in output
    assert "Enter a whole number." in output
    assert "Choose one of: a, b" in output


class LoginClient:
    def __init__(self) -> None:
        self.credentials: tuple[str, str] | None = None

    def login(self, email: str, password: str, mfa) -> str:
        self.credentials = (email, password)
        assert mfa() == "654321"
        return "Test User"


def test_login_requires_password_and_supports_mfa(monkeypatch, capsys) -> None:
    client = LoginClient()
    secrets = iter(["secret", "654321"])
    monkeypatch.setattr("garmin_sync.cli.getpass.getpass", lambda _: next(secrets))
    assert login_command(client, answers(["", "person@example.test"])) == 0  # type: ignore[arg-type]
    assert client.credentials == ("person@example.test", "secret")
    assert "Login successful: Test User" in capsys.readouterr().out

    monkeypatch.setattr("garmin_sync.cli.getpass.getpass", lambda _: "")
    with pytest.raises(ValidationError, match="Password is required"):
        login_command(client, answers(["person@example.test"]))  # type: ignore[arg-type]


class AddClient:
    def __init__(self) -> None:
        self.uploaded: list[BodyComposition | BloodPressure] = []

    def connect(self) -> str:
        return "Test User"

    def add_body_composition(self, item: BodyComposition) -> None:
        self.uploaded.append(item)

    def add_blood_pressure(self, item: BloodPressure) -> None:
        self.uploaded.append(item)


def test_add_command_uploads_pressure_and_can_cancel_body(capsys) -> None:
    client = AddClient()
    assert add_command(
        client, answers(["2", "2026-08-13 08:30", "120", "80", "60", "morning", "yes"])
    ) == 0  # type: ignore[arg-type]
    assert isinstance(client.uploaded[0], BloodPressure)

    assert add_command(
        client,
        answers(
            ["1", "2026-08-13 08:30", "80", "", "", "", "", "", "", "", "", "no"]
        ),
    ) == 0  # type: ignore[arg-type]
    assert len(client.uploaded) == 1
    output = capsys.readouterr().out
    assert "Uploaded and verified" in output
    assert "Cancelled; nothing was uploaded." in output


class DeleteStore:
    def __init__(self, deleted: bool) -> None:
        self.deleted = deleted
        self.calls = 0

    def delete(self) -> bool:
        self.calls += 1
        return self.deleted


def test_logout_confirmation_and_missing_session(capsys) -> None:
    store = DeleteStore(False)
    assert logout_command(store, answers(["no"])) == 0  # type: ignore[arg-type]
    assert store.calls == 0
    assert logout_command(store, answers(["yes"])) == 0  # type: ignore[arg-type]
    assert store.calls == 1
    assert "No saved session was found." in capsys.readouterr().out


def test_renpho_sync_empty_and_uncertain_results(monkeypatch, tmp_path, capsys) -> None:
    class EmptyService:
        def __init__(self, *args) -> None:
            pass

        def preview_renpho(self, mode: str) -> RenphoPreview:
            return RenphoPreview(mode, (), 2)

    monkeypatch.setattr("garmin_sync.cli.HealthSyncService", EmptyService)
    assert (
        renpho_sync(object(), object(), SyncState(tmp_path / "state.json"), "latest") == 0  # type: ignore[arg-type]
    )
    output = capsys.readouterr().out
    assert "skipped 2" in output
    assert "Nothing to sync" in output

    item = _renpho_items()[0]

    class UncertainService(EmptyService):
        def preview_renpho(self, mode: str) -> RenphoPreview:
            return RenphoPreview(mode, (item,), 0)

        def sync_renpho(self, preview: RenphoPreview) -> list[OperationResult]:
            return [OperationResult(ResultStatus.UNCERTAIN, "verify manually")]

    monkeypatch.setattr("garmin_sync.cli.HealthSyncService", UncertainService)
    with pytest.raises(UploadUncertain, match="verify manually"):
        renpho_sync(
            object(), object(), SyncState(tmp_path / "state.json"), "latest", assume_yes=True
        )  # type: ignore[arg-type]


def test_schedule_command_dispatches_all_actions(monkeypatch, tmp_path, capsys) -> None:
    from garmin_sync import schedule

    target = tmp_path / "job.plist"
    monkeypatch.setattr(schedule, "install", lambda **_: target)
    monkeypatch.setattr(schedule, "log_path", lambda: tmp_path / "job.log")
    monkeypatch.setattr(schedule, "plist_path", lambda: target)
    monkeypatch.setattr(schedule, "is_loaded", lambda: True)
    monkeypatch.setattr(schedule, "is_legacy", lambda: True)
    monkeypatch.setattr(schedule, "run_now", lambda: None)
    monkeypatch.setattr(schedule, "uninstall", lambda: True)
    target.touch()

    assert schedule_command(argparse.Namespace(schedule_command="install", hour=7, minute=5)) == 0
    assert schedule_command(argparse.Namespace(schedule_command="status")) == 0
    assert schedule_command(argparse.Namespace(schedule_command="run")) == 0
    assert schedule_command(argparse.Namespace(schedule_command="uninstall")) == 0
    output = capsys.readouterr().out
    assert "07:05" in output
    assert "Legacy weight-only job detected" in output
    assert "Scheduled RENPHO sync started" in output
    assert "Daily RENPHO sync removed" in output


def test_main_reports_known_errors_without_traceback(monkeypatch, capsys) -> None:
    class BrokenClient:
        def __init__(self, store) -> None:
            pass

        def connect(self) -> str:
            raise GarminSyncError("safe failure")

    monkeypatch.setattr("garmin_sync.cli.configured_stores", lambda: (object(), object()))
    monkeypatch.setattr("garmin_sync.cli.GarminClient", BrokenClient)
    assert main(["--diagnostic", "status"]) == 2
    assert "Error: safe failure" in capsys.readouterr().err

    monkeypatch.setattr(
        BrokenClient,
        "connect",
        lambda self: (_ for _ in ()).throw(UploadUncertain("check")),
    )
    assert main(["status"]) == 3
