from __future__ import annotations

import asyncio
import json
import sys
from typing import Any
from unittest.mock import Mock

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_ai_context import _report

from garmin_sync import health_mcp
from garmin_sync.ai_context import build_health_context
from garmin_sync.service import ResultStatus, WeeklyReportResult


def test_tool_collection_is_read_only_and_filters_sections(monkeypatch: Any) -> None:
    context = {
        "generated_at": "2026-11-02T12:00:00+01:00",
        "period": {"days": 7},
        "availability": {"unavailable": []},
        "limitations": [],
        "summary": {"exercise_progression": []},
        "raw_data": {
            "training_summary": {}, "activities": [], "body_measurements": [],
            "body_dynamics": {}, "blood_pressure": {}, "daily_health": [],
            "unrequested_secret": "must-not-appear",
        },
    }
    mock_service = Mock()
    mock_service.build_health_context.return_value = Mock(
        status=ResultStatus.SUCCESS, context=Mock(model_dump=Mock(return_value=context))
    )
    monkeypatch.setattr(health_mcp, "configured_stores", lambda: (Mock(), Mock()))
    monkeypatch.setattr(health_mcp, "HealthSyncService", lambda *_: mock_service)
    sections = ("summary", "activities", "strength", "body", "pressure", "recovery", "availability")
    for section in sections:
        result = health_mcp.collect(section, "7d")
        assert "must-not-appear" not in str(result)
        assert result["status"] == "success"
    assert mock_service.build_health_context.call_count == 7
    mock_service.build_health_context.assert_called_with("7d", persist_archive=False)


def test_stdio_exposes_only_read_only_tools() -> None:
    async def run() -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from garmin_sync.health_mcp import main; main()"],
        )
        async with stdio_client(params) as (reader, writer):  # noqa: SIM117
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = (await client.list_tools()).tools
                assert len(tools) == 10
                for tool in tools:
                    assert tool.annotations
                    assert tool.annotations.readOnlyHint == (tool.name != "save_health_snapshot")
                result = await client.call_tool("get_health_summary", {"period": "90d"})
                assert result.isError
                result = await client.call_tool("refresh_health_snapshot", {"days": 91})
                assert result.isError
                result = await client.call_tool("refresh_health_snapshot", {"days": True})
                assert result.isError

    asyncio.run(run())


def test_collection_does_not_expose_secret_store_errors(monkeypatch: Any) -> None:
    def fail() -> None:
        raise ValueError("sensitive-secret")

    monkeypatch.setattr(health_mcp, "configured_stores", fail)
    with pytest.raises(RuntimeError, match="Health data collection failed") as exc_info:
        health_mcp.get_health_summary()
    assert "sensitive-secret" not in str(exc_info.value)


def test_legacy_tools_also_filter_free_text(monkeypatch: Any) -> None:
    context = build_health_context(_report(), "30d")
    context.raw_data.blood_pressure.readings[0].notes = "private location"
    svc = Mock()
    svc.build_health_context.return_value = Mock(status=ResultStatus.SUCCESS, context=context)
    monkeypatch.setattr(health_mcp, "configured_stores", lambda: (Mock(), Mock()))
    monkeypatch.setattr(health_mcp, "HealthSyncService", lambda *_: svc)
    assert "private location" not in str(health_mcp.get_blood_pressure("30d"))
    assert "Custom movement" not in str(health_mcp.get_activities("30d"))


def test_snapshot_is_reused_and_explicit_save_is_atomic(
    monkeypatch: Any, tmp_path: Any
) -> None:
    archive = health_mcp.LocalHealthArchive(tmp_path / "archive")
    archive.setup()
    svc = Mock()
    svc.build_comprehensive_report.return_value = WeeklyReportResult(
        ResultStatus.SUCCESS, _report(), b""
    )
    monkeypatch.setattr(health_mcp, "_snapshot", None)
    monkeypatch.setattr(health_mcp, "configured_stores", lambda: (Mock(), Mock()))
    monkeypatch.setattr(health_mcp, "HealthSyncService", lambda *_: svc)
    monkeypatch.setattr(health_mcp, "LocalHealthArchive", lambda: archive)

    result = health_mcp.refresh_health_snapshot(15)
    assert result["period"]["days"] == 15
    assert result["schema_version"] == "garmin-health-sync/ai-context@4"
    assert isinstance(result["stale"], bool)
    for section in ("summary", "activities", "body", "pressure", "recovery"):
        assert health_mcp.get_snapshot_section(section)["period"]["days"] == 15
    assert svc.build_comprehensive_report.call_count == 1
    assert not (archive.profile_root / "context" / "exports").exists()

    saved = health_mcp.save_health_snapshot()
    from pathlib import Path

    files = list(Path(saved["directory"]).iterdir())
    assert sorted(x.suffix for x in files) == [".json", ".md"]
    data = json.loads(next(x for x in files if x.suffix == ".json").read_text())
    markdown = next(x for x in files if x.suffix == ".md").read_text()
    assert data["period"]["days"] == 15
    assert 'period: "custom"\ndays: 15' in markdown
    assert all(x.stat().st_mode & 0o777 == 0o600 for x in files)
    second = health_mcp.save_health_snapshot()
    assert saved["directory"] != second["directory"]


def test_failed_refresh_does_not_leave_a_previous_snapshot(monkeypatch: Any) -> None:
    monkeypatch.setattr(health_mcp, "_snapshot", {"old": "data"})
    monkeypatch.setattr(health_mcp, "configured_stores", Mock(side_effect=RuntimeError("secret")))
    with pytest.raises(RuntimeError, match="Health data collection failed"):
        health_mcp.refresh_health_snapshot(10)
    with pytest.raises(ValueError, match="No snapshot available"):
        health_mcp.get_snapshot_section()


@pytest.mark.parametrize("status", [ResultStatus.PARTIAL, ResultStatus.AUTH_REQUIRED,
                                     ResultStatus.RATE_LIMITED, ResultStatus.ERROR])
def test_snapshot_returns_collection_status_without_retry(monkeypatch: Any, status: Any) -> None:
    svc = Mock()
    svc.build_comprehensive_report.return_value = WeeklyReportResult(status, _report(), b"")
    monkeypatch.setattr(health_mcp, "_snapshot", None)
    monkeypatch.setattr(health_mcp, "configured_stores", lambda: (Mock(), Mock()))
    monkeypatch.setattr(health_mcp, "HealthSyncService", lambda *_: svc)
    assert health_mcp.refresh_health_snapshot(10)["status"] == status.value
    assert svc.build_comprehensive_report.call_count == 1
