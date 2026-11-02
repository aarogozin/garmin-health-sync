"""MCP access to health snapshots, with explicit private-archive export."""

from __future__ import annotations

import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .ai_context import (
    HealthContextExport,
    build_custom_health_context,
    sanitize_mcp_health_context,
)
from .archive import LocalHealthArchive
from .garmin import GarminClient
from .models import BERLIN
from .renpho import RenphoCloud
from .secrets import configured_stores
from .service import HealthSyncService
from .state import SyncState

Period = Literal["current", "7d", "30d"]
Section = Literal[
    "summary", "activities", "strength", "body", "pressure", "recovery", "availability"
]
Days = Annotated[int, Field(strict=True, ge=1, le=90)]
server = FastMCP("Garmin Health Sync", json_response=True)
_lock = threading.Lock()
_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
_snapshot: dict[str, Any] | None = None


@server.tool(annotations=_READ_ONLY)
def refresh_health_snapshot(days: Days = 30) -> dict[str, Any]:
    """Fetch a fresh in-memory snapshot for the last 1–90 Berlin calendar days."""
    global _snapshot
    if isinstance(days, bool) or not 1 <= days <= 90:
        raise ValueError("days must be between 1 and 90")
    with _lock:
        _snapshot = None
        try:
            garmin_store, renpho_store = configured_stores()
            service = HealthSyncService(
                GarminClient(garmin_store),
                RenphoCloud(renpho_store, retry_rejected_reads=False),
                SyncState(),
            )
            report = service.build_comprehensive_report(
                period=max(30, days), lifestyle_context=max(30, days),
                include_routes=False, map_tiles_enabled=False,
            )
            context, markdown = build_custom_health_context(report.report, days)
            _snapshot = {
                "status": report.status.value,
                "context": context.model_dump(mode="json"),
                "json": context.model_dump_json(indent=2, exclude_none=False) + "\n",
                "markdown": markdown,
            }
        except Exception:
            raise RuntimeError("Health data collection failed; check account connections") from None
        return _snapshot_metadata(_snapshot)


def _snapshot_metadata(snapshot: dict[str, Any]) -> dict[str, Any]:
    context = snapshot["context"]
    generated = datetime.fromisoformat(context["generated_at"])
    age_seconds = max(0, int((datetime.now(BERLIN) - generated).total_seconds()))
    stale = age_seconds > 900
    return {
        "status": snapshot["status"], "generated_at": context["generated_at"],
        "schema_version": context["schema_version"], "age_seconds": age_seconds, "stale": stale,
        "period": context["period"], "availability": context["availability"],
        "limitations": context["limitations"],
        "freshness": ("Snapshot is over 15 minutes old; refresh for current data." if stale else
                      "Captured at generated_at; refresh explicitly for newer data."),
    }


@server.tool(annotations=_READ_ONLY)
def get_snapshot_section(section: Section = "summary") -> dict[str, Any]:
    """Read a section from the current snapshot without contacting providers again."""
    with _lock:
        if _snapshot is None:
            raise ValueError("No snapshot available; call refresh_health_snapshot first")
        context = _snapshot["context"]
        raw = context["raw_data"]
        selections = {
            "summary": context["summary"],
            "activities": {
                "training_summary": raw["training_summary"], "activities": raw["activities"]
            },
            "strength": context["summary"]["exercise_progression"],
            "body": {"measurements": raw["body_measurements"], "dynamics": raw["body_dynamics"]},
            "pressure": raw["blood_pressure"], "recovery": raw["daily_health"],
            "availability": context["availability"],
        }
        return {**_snapshot_metadata(_snapshot), "data": selections[section]}


@server.tool(annotations=_WRITE)
def save_health_snapshot() -> dict[str, Any]:
    """Save the current snapshot to the private archive only when explicitly requested."""
    with _lock:
        if _snapshot is None:
            raise ValueError("No snapshot available; call refresh_health_snapshot first")
        archive = LocalHealthArchive()
        if not archive.profile_root.is_dir():
            raise ValueError("Private archive is not set up")
        root = archive.profile_root / "context" / "exports"
        archive._mkdir(root)
        context = _snapshot["context"]
        period = context["period"]
        stamp = datetime.now(BERLIN).strftime("%Y-%m-%d_%H-%M-%S-%f")
        name = (
            f"health-context-{period['start_date']}-to-{period['end_date']}-{stamp}-{uuid4().hex}"
        )
        stage = Path(tempfile.mkdtemp(prefix=".pending-", dir=root))
        try:
            archive._write(stage / f"{name}.json", _snapshot["json"])
            archive._write(stage / f"{name}.md", _snapshot["markdown"])
            destination = root / name
            os.rename(stage, destination)
        except Exception:
            for item in stage.iterdir():
                item.unlink()
            stage.rmdir()
            raise RuntimeError("Could not save snapshot to the private archive") from None
        return {**_snapshot_metadata(_snapshot), "saved": True, "directory": str(destination)}


def collect(section: str, period: Period) -> dict[str, Any]:
    """Collect an in-memory context and expose only the requested normalized section."""
    with _lock:
        try:
            garmin_store, renpho_store = configured_stores()
            service = HealthSyncService(
                GarminClient(garmin_store), RenphoCloud(renpho_store), SyncState()
            )
            result = service.build_health_context(period, persist_archive=False)
            if isinstance(result.context, HealthContextExport):
                sanitize_mcp_health_context(result.context)
            context = result.context.model_dump(mode="json")
        except Exception:
            raise RuntimeError("Health data collection failed; check account connections") from None
    raw = context["raw_data"]
    selections = {
        "summary": context["summary"],
        "activities": {
            "training_summary": raw["training_summary"], "activities": raw["activities"]
        },
        "strength": context["summary"]["exercise_progression"],
        "body": {"measurements": raw["body_measurements"], "dynamics": raw["body_dynamics"]},
        "pressure": raw["blood_pressure"],
        "recovery": raw["daily_health"],
        "availability": context["availability"],
    }
    return {
        "status": result.status.value,
        "generated_at": context["generated_at"],
        "period": context["period"],
        "availability": context["availability"],
        "limitations": context["limitations"],
        "data": selections[section],
    }


@server.tool(annotations=_READ_ONLY)
def get_health_summary(period: Period = "7d") -> dict[str, Any]:
    """Return compact health trends, data-quality flags, and strength summary."""
    return collect("summary", period)


@server.tool(annotations=_READ_ONLY)
def get_activities(period: Period = "7d") -> dict[str, Any]:
    """Return normalized Garmin training summaries and recorded exercises."""
    return collect("activities", period)


@server.tool(annotations=_READ_ONLY)
def get_strength_progression(period: Period = "30d") -> dict[str, Any]:
    """Return strength progression derived from recorded exercise sets."""
    return collect("strength", period)


@server.tool(annotations=_READ_ONLY)
def get_body_measurements(period: Period = "30d") -> dict[str, Any]:
    """Return body composition and weight from Garmin and RENPHO."""
    return collect("body", period)


@server.tool(annotations=_READ_ONLY)
def get_blood_pressure(period: Period = "30d") -> dict[str, Any]:
    """Return recorded blood pressure and coverage."""
    return collect("pressure", period)


@server.tool(annotations=_READ_ONLY)
def get_recovery(period: Period = "7d") -> dict[str, Any]:
    """Return daily sleep, stress, HRV, activity, and recovery metrics."""
    return collect("recovery", period)


@server.tool(annotations=_READ_ONLY)
def get_data_availability(period: Period = "7d") -> dict[str, Any]:
    """Return current source coverage and unavailable data."""
    return collect("availability", period)


def main() -> None:
    """Serve MCP over stdio; no network port is opened."""
    server.run(transport="stdio")
