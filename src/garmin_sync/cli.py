from __future__ import annotations

import argparse
import getpass
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import cast

from .ai_context import ContextPeriod
from .archive import ArchiveError
from .garmin import GarminClient, GarminSyncError, UploadUncertain
from .models import BloodPressure, BodyComposition, ValidationError, parse_local_datetime
from .operation_lock import SyncBusyError
from .renpho import RenphoCloud, RenphoError, SuppliedCredentials
from .schedule import ScheduleError
from .secrets import (
    RenphoStore,
    SecretStoreError,
    TokenStore,
    configured_stores,
)
from .service import HealthSyncService, ResultStatus
from .state import SyncState, SyncStateError

Input = Callable[[str], str]


def build_parser() -> argparse.ArgumentParser:
    """Define terminal commands independently of secure-store initialization."""
    parser = argparse.ArgumentParser(
        prog="garmin-sync", description="Manually log health data to Garmin Connect"
    )
    parser.add_argument(
        "--diagnostic", action="store_true", help="show safe operational diagnostics"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="authenticate and save an OAuth session securely")
    sub.add_parser("add", help="open the measurement wizard")
    sub.add_parser("status", help="verify the saved Garmin session")
    sub.add_parser("logout", help="remove the saved session")
    sub.add_parser("gui", help="open the local web interface")
    renpho = sub.add_parser("renpho", help="sync body composition from RENPHO cloud")
    renpho_sub = renpho.add_subparsers(dest="renpho_command", required=True)
    renpho_sub.add_parser("login", help="verify and save RENPHO credentials")
    renpho_sub.add_parser("status", help="verify RENPHO credentials")
    renpho_sub.add_parser("logout", help="remove RENPHO credentials")
    sync = renpho_sub.add_parser("sync", help="download and upload RENPHO measurements")
    mode = sync.add_mutually_exclusive_group()
    mode.add_argument("--latest", dest="sync_mode", action="store_const", const="latest")
    mode.add_argument("--all", dest="sync_mode", action="store_const", const="all")
    sync.add_argument("--yes", action="store_true", help="run without an interactive confirmation")
    sync.set_defaults(sync_mode="latest")
    combined = sub.add_parser("sync", help="run synchronization jobs")
    combined_sub = combined.add_subparsers(dest="sync_command", required=True)
    combined_sub.add_parser("daily", help="sync the latest RENPHO measurement to Garmin")
    archive = sub.add_parser("archive", help="manage the private local Markdown health archive")
    archive_sub = archive.add_subparsers(dest="archive_command", required=True)
    archive_sub.add_parser("setup", help="create the local Markdown archive")
    backfill = archive_sub.add_parser(
        "backfill", help="collect and archive previous health history"
    )
    backfill.add_argument(
        "--days", type=int, default=90, help="history window (1-365, default: 90)"
    )
    archive_sub.add_parser("refresh", help="collect and archive today's health snapshot")
    archive_sub.add_parser("status", help="show the local archive status")
    context = sub.add_parser("context", help="generate AI-ready health context files")
    context_sub = context.add_subparsers(dest="context_command", required=True)
    generate = context_sub.add_parser("generate", help="collect JSON and Markdown context")
    generate.add_argument("period_value", nargs="?", choices=("current", "7d", "30d"))
    generate.add_argument(
        "--period", dest="period_option", choices=("current", "7d", "30d")
    )
    schedule = sub.add_parser("schedule", help="manage daily RENPHO sync with macOS launchd")
    schedule_sub = schedule.add_subparsers(dest="schedule_command", required=True)
    install = schedule_sub.add_parser("install", help="install or update the daily schedule")
    install.add_argument("--hour", type=int, default=9)
    install.add_argument("--minute", type=int, default=0)
    schedule_sub.add_parser("status", help="show whether the schedule is loaded")
    schedule_sub.add_parser("run", help="trigger the scheduled job now")
    schedule_sub.add_parser("uninstall", help="remove the daily schedule")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a CLI operation and translate known failures into safe messages and exit codes."""
    args = build_parser().parse_args(argv)
    if args.diagnostic:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
        logging.info(
            "Safe diagnostics enabled; HTTP headers, bodies, credentials, and tokens are suppressed"
        )
    try:
        store, renpho_store = configured_stores()
        client = GarminClient(store)
        if args.command == "login":
            return login_command(client)
        if args.command == "add":
            return add_command(client)
        if args.command == "status":
            print(f"Connected as: {client.connect()}")
            return 0
        if args.command == "renpho":
            return renpho_command(args, client, renpho_store)
        if args.command == "sync":
            return daily_sync(client, RenphoCloud(renpho_store), SyncState())
        if args.command == "archive":
            return archive_command(
                args, HealthSyncService(client, RenphoCloud(renpho_store), SyncState())
            )
        if args.command == "context":
            return context_command(
                args, HealthSyncService(client, RenphoCloud(renpho_store), SyncState())
            )
        if args.command == "gui":
            from .gui import run_gui

            run_gui()
            return 0
        if args.command == "schedule":
            return schedule_command(args)
        return logout_command(store)
    except (
        GarminSyncError,
        RenphoError,
        SecretStoreError,
        SyncStateError,
        ScheduleError,
        ValidationError,
        SyncBusyError,
        ArchiveError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2 if not isinstance(exc, UploadUncertain) else 3


def daily_sync(garmin: GarminClient, cloud: RenphoCloud, state: SyncState) -> int:
    """Run an unattended weight upload, then refresh an enabled archive independently."""
    service = HealthSyncService(garmin, cloud, state)
    exit_code = 0
    print("Daily sync: RENPHO weight → Garmin")
    try:
        for result in service.sync_renpho(service.preview_renpho("latest")):
            print(f"  weight sync: {result.status.value}")
            if result.status not in {ResultStatus.SUCCESS, ResultStatus.ALREADY_EXISTS}:
                exit_code = max(exit_code, 3 if result.status == ResultStatus.UNCERTAIN else 2)
    except (GarminSyncError, RenphoError, SyncStateError, SyncBusyError) as exc:
        print(f"  error: {exc}", file=sys.stderr)
        exit_code = max(exit_code, 2)

    print("Daily archive: normalized Garmin and RENPHO health snapshot")
    try:
        refresh = getattr(service, "archive_refresh", None)
        if not callable(refresh):
            print("  archive: unavailable")
            return exit_code
        archive_result = refresh()
        print(f"  archive: {archive_result.status.value}")
        if archive_result.status in {
            ResultStatus.ERROR,
            ResultStatus.UNCERTAIN,
            ResultStatus.AUTH_REQUIRED,
            ResultStatus.RATE_LIMITED,
        }:
            exit_code = max(exit_code, 3 if archive_result.status == ResultStatus.UNCERTAIN else 2)
    except (GarminSyncError, RenphoError, SyncBusyError, ArchiveError) as exc:
        print(f"  archive error: {exc}", file=sys.stderr)
        exit_code = max(exit_code, 2)

    return exit_code


def archive_command(args: argparse.Namespace, service: HealthSyncService) -> int:
    """Manage the optional Markdown workspace using the same service as the GUI."""
    if args.archive_command == "setup":
        result = service.archive_initialize()
        print(result.message)
        return 0 if result.status in {ResultStatus.SUCCESS, ResultStatus.PARTIAL} else 2
    if args.archive_command == "status":
        status = service.archive_status()
        print(f"Archive: {status.root}")
        print(f"Daily notes: {status.daily_documents}")
        print(f"Weekly notes: {status.weekly_documents}")
        print(f"Last update: {status.last_updated or 'not available'}")
        return 0
    result = (
        service.archive_backfill(args.days)
        if args.archive_command == "backfill"
        else service.archive_refresh()
    )
    print(result.message)
    return 0 if result.status in {ResultStatus.SUCCESS, ResultStatus.PARTIAL} else 2


def context_command(args: argparse.Namespace, service: HealthSyncService) -> int:
    """Generate synchronized JSON/Markdown files in the private local archive."""
    period = args.period_option or args.period_value or "30d"
    result = service.build_health_context(cast(ContextPeriod, period))
    print(
        f"AI health context {period}: {result.status.value}; "
        + ("archived" if result.archived else "available in memory only")
    )
    return 0 if result.status in {ResultStatus.SUCCESS, ResultStatus.PARTIAL} else 2


def login_command(client: GarminClient, input_fn: Input = input) -> int:
    """Collect transient Garmin credentials and persist only the authenticated session."""
    email = _required("Garmin email: ", input_fn)
    password = getpass.getpass("Garmin password (not saved): ")
    if not password:
        raise ValidationError("Password is required")
    name = client.login(email, password, lambda: getpass.getpass("Garmin MFA code: "))
    print(f"Login successful: {name}")
    return 0


def add_command(client: GarminClient, input_fn: Input = input) -> int:
    """Validate and preview a measurement before a single confirmed Garmin write."""
    client.connect()
    kind = _choice("Measurement [1 body composition, 2 blood pressure]: ", {"1", "2"}, input_fn)
    measurement = body_wizard(input_fn) if kind == "1" else pressure_wizard(input_fn)
    print("\nReview:")
    for label, value in measurement.summary():
        print(f"  {label}: {value}")
    if not _confirm("Upload to Garmin Connect? [y/N]: ", input_fn):
        print("Cancelled; nothing was uploaded.")
        return 0
    if isinstance(measurement, BodyComposition):
        client.add_body_composition(measurement)
    else:
        client.add_blood_pressure(measurement)
    print("Uploaded and verified in Garmin Connect.")
    return 0


def logout_command(store: TokenStore, input_fn: Input = input) -> int:
    """Remove the selected local Garmin session only after terminal confirmation."""
    if not _confirm("Remove the saved Garmin session? [y/N]: ", input_fn):
        print("Cancelled.")
        return 0
    print("Saved session removed." if store.delete() else "No saved session was found.")
    return 0


def renpho_command(
    args: argparse.Namespace,
    garmin: GarminClient,
    store: RenphoStore,
    input_fn: Input = input,
) -> int:
    """Authenticate RENPHO, inspect its session, or dispatch a confirmed body sync."""
    if args.renpho_command == "login":
        email = _required("RENPHO email: ", input_fn)
        password = getpass.getpass("RENPHO password: ")
        if not password:
            raise ValidationError("Password is required")
        RenphoCloud(SuppliedCredentials(email, password)).authenticate()
        store.save(email, password)
        print("RENPHO login successful; credentials saved securely.")
        return 0
    if args.renpho_command == "status":
        RenphoCloud(store).authenticate()
        print("RENPHO credentials are valid.")
        return 0
    if args.renpho_command == "logout":
        if not _confirm("Remove saved RENPHO credentials? [y/N]: ", input_fn):
            print("Cancelled.")
            return 0
        print("RENPHO credentials removed." if store.delete() else "No credentials found.")
        return 0
    return renpho_sync(
        garmin,
        RenphoCloud(store),
        SyncState(),
        args.sync_mode,
        input_fn,
        assume_yes=args.yes,
    )


def renpho_sync(
    garmin: GarminClient,
    cloud: RenphoCloud,
    state: SyncState,
    mode: str,
    input_fn: Input = input,
    *,
    assume_yes: bool = False,
) -> int:
    """Preview normalized candidates and fail the command when any upload is unverified."""
    service = HealthSyncService(garmin, cloud, state)
    preview = service.preview_renpho(mode)
    candidates = list(preview.candidates)
    if preview.skipped:
        print(f"Warning: skipped {preview.skipped} malformed or unsupported RENPHO record(s).")
    if not candidates:
        print("Nothing to sync; selected RENPHO measurements were already uploaded.")
        return 0

    first = candidates[0].body.measured_at.isoformat(timespec="minutes")
    last = candidates[-1].body.measured_at.isoformat(timespec="minutes")
    print(f"Ready to upload {len(candidates)} measurement(s), from {first} to {last}.")
    print("Latest selected measurement:")
    for label, value in candidates[-1].body.summary():
        print(f"  {label}: {value}")
    confirmed = assume_yes or _confirm(
        "Upload these measurements to Garmin Connect? [y/N]: ", input_fn
    )
    if not confirmed:
        print("Cancelled; nothing was uploaded.")
        return 0

    results = service.sync_renpho(preview)
    for index, result in enumerate(results, start=1):
        print(f"{index}/{len(candidates)} {result.status.value}: {result.message}")
        if result.status == ResultStatus.UNCERTAIN:
            raise UploadUncertain(result.message)
        if result.status not in {ResultStatus.SUCCESS, ResultStatus.ALREADY_EXISTS}:
            raise GarminSyncError(result.message)
    print("RENPHO sync completed.")
    return 0


def schedule_command(args: argparse.Namespace) -> int:
    """Manage the native development LaunchAgent; Docker uses the root launcher bridge."""
    from . import schedule

    if args.schedule_command == "install":
        target = schedule.install(hour=args.hour, minute=args.minute)
        print(f"Daily weight sync installed for {args.hour:02d}:{args.minute:02d}.")
        print(f"LaunchAgent: {target}")
        print(f"Log: {schedule.log_path()}")
        return 0
    if args.schedule_command == "status":
        installed = schedule.plist_path().exists()
        loaded = schedule.is_loaded() if installed else False
        print(f"Installed: {'yes' if installed else 'no'}")
        print(f"Loaded: {'yes' if loaded else 'no'}")
        if installed:
            print(f"Log: {schedule.log_path()}")
            if schedule.is_legacy():
                print("Legacy weight-only job detected; run 'garmin-sync schedule install'.")
        return 0 if loaded else 1
    if args.schedule_command == "run":
        schedule.run_now()
        print(f"Scheduled RENPHO sync started. Log: {schedule.log_path()}")
        return 0
    print("Daily RENPHO sync removed." if schedule.uninstall() else "No schedule was installed.")
    return 0


def body_wizard(input_fn: Input = input) -> BodyComposition:
    """Collect body values in canonical units; the model validates physiological bounds."""
    measured_at = _datetime_prompt(input_fn)
    return BodyComposition(
        measured_at=measured_at,
        weight=cast(float, _float_prompt("Weight, kg: ", input_fn, required=True)),
        percent_fat=_float_prompt("Body fat, % (optional): ", input_fn),
        bmi=_float_prompt("BMI (optional): ", input_fn),
        percent_hydration=_float_prompt("Hydration, % (optional): ", input_fn),
        muscle_mass=_float_prompt("Muscle mass, kg (optional): ", input_fn),
        bone_mass=_float_prompt("Bone mass, kg (optional): ", input_fn),
        visceral_fat_rating=_float_prompt("Visceral fat rating 1-59 (optional): ", input_fn),
        basal_met=_float_prompt("Basal metabolism, kcal (optional): ", input_fn),
        metabolic_age=_float_prompt("Metabolic age, years (optional): ", input_fn),
    )


def pressure_wizard(input_fn: Input = input) -> BloodPressure:
    """Collect one local-time blood-pressure reading for later review and confirmation."""
    measured_at = _datetime_prompt(input_fn)
    return BloodPressure(
        measured_at=measured_at,
        systolic=_int_prompt("Systolic, mmHg: ", input_fn),
        diastolic=_int_prompt("Diastolic, mmHg: ", input_fn),
        pulse=_int_prompt("Pulse, bpm: ", input_fn),
        notes=input_fn("Notes (optional): ").strip(),
    )


def _datetime_prompt(input_fn: Input) -> datetime:
    return parse_local_datetime(input_fn("Local date/time [now, or YYYY-MM-DD HH:MM]: "))


def _required(prompt: str, input_fn: Input) -> str:
    while not (value := input_fn(prompt).strip()):
        print("A value is required.")
    return value


def _float_prompt(prompt: str, input_fn: Input, *, required: bool = False) -> float | None:
    while True:
        raw = input_fn(prompt).strip().replace(",", ".")
        if not raw and not required:
            return None
        try:
            return float(raw)
        except ValueError:
            print("Enter a number." if required else "Enter a number or leave it blank.")


def _int_prompt(prompt: str, input_fn: Input) -> int:
    while True:
        try:
            return int(_required(prompt, input_fn))
        except ValueError:
            print("Enter a whole number.")


def _choice(prompt: str, choices: set[str], input_fn: Input) -> str:
    while (value := input_fn(prompt).strip()) not in choices:
        print(f"Choose one of: {', '.join(sorted(choices))}")
    return value


def _confirm(prompt: str, input_fn: Input) -> bool:
    return input_fn(prompt).strip().lower() in {"y", "yes"}


if __name__ == "__main__":
    raise SystemExit(main())
