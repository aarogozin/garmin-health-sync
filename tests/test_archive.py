from __future__ import annotations

import os
import stat
from datetime import datetime

from garmin_sync.archive import LocalHealthArchive
from garmin_sync.models import BERLIN, BodyComposition
from garmin_sync.renpho import RenphoMeasurement
from garmin_sync.renpho_report import normalize_report
from garmin_sync.service import HealthSyncService, ResultStatus, WeeklyReportResult
from garmin_sync.weekly_report import build_report


def _report():
    return build_report(
        start_date=datetime(2026, 8, 10).date(),
        end_date=datetime(2026, 8, 16).date(),
        garmin={
            "activities": [
                {
                    "startTimeLocal": "2026-08-12T07:00:00",
                    "activityType": {"typeKey": "running"},
                    "activityName": "Private | place\nname",
                    "duration": 3600,
                    "distance": 10000,
                }
            ],
            "pressure": {"bloodPressureReadings": []},
        },
        renpho=[
            RenphoMeasurement(
                "private-record-id",
                BodyComposition(datetime(2026, 8, 12, 7, 30, tzinfo=BERLIN), 80.5),
                normalize_report(
                    {"reportId": "private-report-id", "weight": 80.5, "bone": 3.3, "bmr": 1800},
                    datetime(2026, 8, 12, 7, 30, tzinfo=BERLIN),
                ),
            )
        ],
        available=["activities", "renpho"],
        unavailable=["sleep"],
    )


def test_archive_creates_private_git_ignored_markdown_workspace(tmp_path) -> None:
    archive = LocalHealthArchive(tmp_path / "health")
    status = archive.write_report(_report())

    assert status.daily_documents == 7
    assert status.weekly_documents == 1
    assert (archive.root / ".gitignore").read_text() == "*\n!.gitignore\n"
    assert "garmin-health-sync/health-note@1" in (archive.profile_root / "PROFILE.md").read_text()
    daily = archive.profile_root / "daily" / "2026" / "08" / "2026-08-12.md"
    content = daily.read_text()
    assert "running" in content
    assert "Private | place" not in content
    assert "private-record-id" not in content
    assert "private-report-id" not in content
    assert "BMR" in content
    assert "GPS" not in content
    assert stat.S_IMODE(os.stat(daily).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(archive.profile_root).st_mode) == 0o700


def test_archive_replaces_daily_note_atomically_and_keeps_stable_paths(tmp_path) -> None:
    archive = LocalHealthArchive(tmp_path / "health")
    report = _report()
    archive.write_report(report)
    daily = archive.profile_root / "daily" / "2026" / "08" / "2026-08-12.md"
    first = daily.read_text()
    archive.write_report(report)
    assert daily.read_text() == first
    assert not list(daily.parent.glob(".health-note-*.tmp"))


def test_unsuccessful_report_never_replaces_existing_archive(tmp_path) -> None:
    class Garmin:
        pass

    class Cloud:
        pass

    archive = LocalHealthArchive(tmp_path / "health")
    service = HealthSyncService(Garmin(), Cloud(), object(), archive=archive)  # type: ignore[arg-type]
    report = _report()
    successful = service.archive_report(WeeklyReportResult(ResultStatus.SUCCESS, report, b"%PDF"))
    assert successful.status == ResultStatus.SUCCESS
    profile = archive.profile_root / "PROFILE.md"
    before = profile.read_text()
    result = service.archive_report(WeeklyReportResult(ResultStatus.AUTH_REQUIRED, report, b"%PDF"))
    assert result.status == ResultStatus.AUTH_REQUIRED
    assert profile.read_text() == before


def test_partial_report_preserves_existing_health_notes_and_profile(tmp_path) -> None:
    archive = LocalHealthArchive(tmp_path / "health")
    service = HealthSyncService(object(), object(), object(), archive=archive)  # type: ignore[arg-type]
    original = _report()
    service.archive_report(WeeklyReportResult(ResultStatus.SUCCESS, original, b"%PDF"))
    paths = [
        archive.profile_root / "daily/2026/08/2026-08-12.md",
        archive.profile_root / "weekly/2026/2026-W33.md",
        archive.profile_root / "PROFILE.md",
    ]
    before = [path.read_text() for path in paths]
    partial = build_report(
        start_date=original.start_date,
        end_date=original.end_date,
        garmin={}, renpho=[], available=[], unavailable=["activities", "renpho"],
    )
    result = service.archive_report(WeeklyReportResult(ResultStatus.PARTIAL, partial, b"%PDF"))
    assert result.status == ResultStatus.PARTIAL
    assert "preserved" in result.message
    assert [path.read_text() for path in paths] == before
    assert not list(archive.root.rglob(".health-note-*.tmp"))


def test_partial_report_can_seed_missing_notes(tmp_path) -> None:
    archive = LocalHealthArchive(tmp_path / "health")
    service = HealthSyncService(object(), object(), object(), archive=archive)  # type: ignore[arg-type]
    result = service.archive_report(WeeklyReportResult(ResultStatus.PARTIAL, _report(), b"%PDF"))
    assert result.status == ResultStatus.PARTIAL
    assert archive.status().daily_documents == 7
    assert (archive.profile_root / "PROFILE.md").exists()
