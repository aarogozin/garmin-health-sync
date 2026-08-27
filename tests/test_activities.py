from datetime import UTC, datetime, timedelta

from garmin_sync.activities import (
    ActivitySyncCandidate,
    RenphoActivityRecord,
    RenphoActivityTemplate,
    exact_activity_match,
    mapped_template,
    normalize_garmin_activity,
    template_matches_mapping,
)
from garmin_sync.models import BERLIN
from garmin_sync.renpho import RenphoError
from garmin_sync.service import HealthSyncService, ResultStatus
from garmin_sync.state import SyncState


def raw_activity(
    activity_id: int = 1,
    kind: str = "running",
    started: str = "2026-08-22T08:00:00",
) -> dict[str, object]:
    return {
        "activityId": activity_id,
        "activityType": {"typeKey": kind},
        "activityName": "Morning Run",
        "startTimeLocal": started,
        "duration": 1800.4,
        "calories": 350.5,
    }


def test_normalize_and_mapping() -> None:
    activity = normalize_garmin_activity(raw_activity())
    assert activity is not None
    assert activity.started_at.tzinfo == BERLIN
    assert activity.duration_seconds == 1800
    assert activity.calories == 351
    assert mapped_template(activity) == RenphoActivityTemplate(52, "Running")
    ebike = normalize_garmin_activity(raw_activity(2, "e_bike_fitness"))
    assert ebike is not None
    assert mapped_template(ebike) == RenphoActivityTemplate(55, "Bicycling")
    assert normalize_garmin_activity({"activityId": 2, "duration": 0}) is None


def test_normalize_prefers_absolute_time_during_dst_fallback() -> None:
    second_0230 = datetime(2026, 10, 25, 2, 30, tzinfo=BERLIN, fold=1)
    raw = raw_activity(started="2026-10-25T02:30:00")
    raw["beginTimestamp"] = int(second_0230.timestamp() * 1000)
    activity = normalize_garmin_activity(raw)
    assert activity is not None
    assert activity.started_at.fold == 1
    assert activity.started_at.astimezone(UTC) == datetime(2026, 10, 25, 1, 30, tzinfo=UTC)


def test_template_mapping_requires_official_matching_name() -> None:
    expected = RenphoActivityTemplate(52, "Running")
    assert template_matches_mapping(expected, RenphoActivityTemplate(52, " running "))
    assert not template_matches_mapping(expected, RenphoActivityTemplate(52, "Cycling"))
    assert not template_matches_mapping(expected, RenphoActivityTemplate(52, "Running", 0))


def test_exact_match_uses_timestamp_type_duration_and_calories() -> None:
    activity = normalize_garmin_activity(raw_activity())
    assert activity is not None
    candidate = ActivitySyncCandidate(activity, RenphoActivityTemplate(52, "Running"))
    record = RenphoActivityRecord(None, 52, activity.started_at + timedelta(seconds=2), 1801, 351)
    assert exact_activity_match(candidate, record)
    assert not exact_activity_match(
        candidate, RenphoActivityRecord(None, 52, activity.started_at, 1801, 352)
    )
    first_0230 = datetime(2026, 10, 25, 2, 30, tzinfo=BERLIN, fold=0)
    second_0230 = first_0230.replace(fold=1)
    ambiguous_activity = activity.__class__(
        activity.source_id,
        activity.activity_type,
        activity.name,
        first_0230,
        activity.duration_seconds,
        activity.calories,
    )
    assert not exact_activity_match(
        ActivitySyncCandidate(ambiguous_activity, candidate.template),
        RenphoActivityRecord(None, 52, second_0230, 1800, 351),
    )


class ActivityGarmin:
    def connect(self) -> str:
        return "Test"

    def read_activities(self, start: str, end: str) -> list[dict[str, object]]:
        return [raw_activity(), raw_activity(2, "unsupported")]

    def read_all_activities(self) -> list[dict[str, object]]:
        return [raw_activity()]


class ActivityRenpho:
    def __init__(self) -> None:
        self.records: list[RenphoActivityRecord] = []

    def fetch_activity_templates(self) -> tuple[RenphoActivityTemplate, ...]:
        return (RenphoActivityTemplate(52, "Running"),)

    def fetch_activities(self) -> tuple[RenphoActivityRecord, ...]:
        return tuple(self.records)

    def create_activity(self, **kwargs: object) -> str:
        self.records.append(
            RenphoActivityRecord(
                "new",
                kwargs["template"].template_id,  # type: ignore[union-attr]
                kwargs["started_at"],  # type: ignore[arg-type]
                kwargs["duration_seconds"],  # type: ignore[arg-type]
                kwargs["calories"],  # type: ignore[arg-type]
            )
        )
        return "new"


def test_service_previews_and_syncs_with_verification(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GARMIN_SYNC_DATA_DIR", str(tmp_path))
    state = SyncState(tmp_path / "state.json")
    renpho = ActivityRenpho()
    service = HealthSyncService(ActivityGarmin(), renpho, state)  # type: ignore[arg-type]
    preview = service.preview_activities(
        "day", now=datetime(2026, 8, 22, 12, 0, tzinfo=BERLIN)
    )
    assert preview.count == 1
    assert [item.activity_type for item in preview.unknown] == ["unsupported"]
    results = service.sync_activities(preview)
    assert [item.status for item in results] == [ResultStatus.SUCCESS.value]
    assert state.activity_synced("1")
    assert service.preview_activities(
        "day", now=datetime(2026, 8, 22, 12, 0, tzinfo=BERLIN)
    ).duplicate_count == 1


def test_service_skips_reassigned_or_unofficial_renpho_template(monkeypatch, tmp_path) -> None:
    class Reassigned(ActivityRenpho):
        def fetch_activity_templates(self) -> tuple[RenphoActivityTemplate, ...]:
            return (RenphoActivityTemplate(52, "Bicycling", 1),)

    monkeypatch.setenv("GARMIN_SYNC_DATA_DIR", str(tmp_path))
    service = HealthSyncService(  # type: ignore[arg-type]
        ActivityGarmin(), Reassigned(), SyncState(tmp_path / "state.json")
    )
    preview = service.preview_activities(
        "day", now=datetime(2026, 8, 22, 12, 0, tzinfo=BERLIN)
    )
    assert preview.candidates == ()
    assert {item.activity_type for item in preview.unknown} == {"running", "unsupported"}


def test_rolling_day_is_24_absolute_hours_across_dst(monkeypatch, tmp_path) -> None:
    class DSTGarmin(ActivityGarmin):
        def read_activities(self, start: str, end: str) -> list[dict[str, object]]:
            return [
                raw_activity(1, started="2026-10-24T12:30:00+02:00"),
                raw_activity(2, started="2026-10-24T13:30:00+02:00"),
            ]

    monkeypatch.setenv("GARMIN_SYNC_DATA_DIR", str(tmp_path))
    service = HealthSyncService(  # type: ignore[arg-type]
        DSTGarmin(), ActivityRenpho(), SyncState(tmp_path / "state.json")
    )
    preview = service.preview_activities(
        "day", now=datetime(2026, 10, 25, 12, 0, tzinfo=BERLIN)
    )
    assert [item.activity.source_id for item in preview.candidates] == ["2"]


def test_verification_failure_after_post_is_uncertain(monkeypatch, tmp_path) -> None:
    class VerificationFailure(ActivityRenpho):
        def __init__(self) -> None:
            super().__init__()
            self.reads = 0

        def fetch_activities(self) -> tuple[RenphoActivityRecord, ...]:
            self.reads += 1
            if self.reads >= 2:
                raise RenphoError("read failed")
            return super().fetch_activities()

    monkeypatch.setenv("GARMIN_SYNC_DATA_DIR", str(tmp_path))
    renpho = VerificationFailure()
    service = HealthSyncService(  # type: ignore[arg-type]
        ActivityGarmin(), renpho, SyncState(tmp_path / "state.json")
    )
    preview = service.preview_activities(
        "day", now=datetime(2026, 8, 22, 12, 0, tzinfo=BERLIN)
    )
    # Preview performs the first history read; reset so sync's preflight succeeds.
    renpho.reads = 0
    results = service.sync_activities(preview)
    assert [item.status for item in results] == [ResultStatus.UNCERTAIN.value]
    assert not service.state.activity_synced("1")
