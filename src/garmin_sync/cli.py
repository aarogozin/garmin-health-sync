from __future__ import annotations

import argparse
import getpass
import logging
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import cast

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
    activities = sub.add_parser(
        "activities", help="experimentally sync Garmin activities to RENPHO"
    )
    activities_sub = activities.add_subparsers(dest="activities_command", required=True)
    for action in ("preview", "sync"):
        activity_action = activities_sub.add_parser(action)
        activity_action.add_argument("--period", choices=("day", "month", "all"), default="day")
        if action == "sync":
            activity_action.add_argument("--yes", action="store_true")
    combined = sub.add_parser("sync", help="run combined synchronization jobs")
    combined_sub = combined.add_subparsers(dest="sync_command", required=True)
    combined_sub.add_parser("daily", help="sync latest weight and the last 24h of activities")
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
    args = build_parser().parse_args(argv)
    if args.diagnostic:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
        logging.info(
            "Safe diagnostics enabled; HTTP headers, bodies, credentials, and tokens are suppressed"
        )
    store, renpho_store = configured_stores()
    client = GarminClient(store)
    try:
        if args.command == "login":
            return login_command(client)
        if args.command == "add":
            return add_command(client)
        if args.command == "status":
            print(f"Connected as: {client.connect()}")
            return 0
        if args.command == "renpho":
            return renpho_command(args, client, renpho_store)
        if args.command == "activities":
            return activities_command(
                args, HealthSyncService(client, RenphoCloud(renpho_store), SyncState())
            )
        if args.command == "sync":
            return daily_sync(client, RenphoCloud(renpho_store), SyncState())
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
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2 if not isinstance(exc, UploadUncertain) else 3


def activities_command(
    args: argparse.Namespace,
    service: HealthSyncService,
    input_fn: Input = input,
) -> int:
    preview = service.preview_activities(args.period)
    _print_activity_preview(preview)
    if args.activities_command == "preview" or not preview.candidates:
        return 0
    if not args.yes and not _confirm("Upload these activities to RENPHO? [y/N]: ", input_fn):
        print("Cancelled; nothing was uploaded.")
        return 0
    results = service.sync_activities(preview)
    failed = False
    uncertain = False
    for index, result in enumerate(results, start=1):
        print(f"{index}/{preview.count} {result.status}: {result.message}")
        failed |= result.status == ResultStatus.ERROR.value
        uncertain |= result.status == ResultStatus.UNCERTAIN.value
    return 3 if uncertain else (2 if failed else 0)


def _print_activity_preview(preview: object) -> None:
    from .activities import ActivitySyncPreview

    if not isinstance(preview, ActivitySyncPreview):
        return
    print(
        f"Garmin → RENPHO preview ({preview.period}): {preview.count} candidate(s), "
        f"{preview.duplicate_count} duplicate(s), {len(preview.unknown)} unknown type(s), "
        f"{preview.invalid_count} invalid record(s)."
    )
    for item in preview.candidates:
        activity = item.activity
        warning = " (calories unavailable; using 0)" if activity.calories_missing else ""
        print(
            f"  {activity.started_at.isoformat(timespec='minutes')} {activity.name} → "
            f"{item.template.name}, {activity.duration_seconds}s, {activity.calories} kcal{warning}"
        )
    for unknown_item in preview.unknown:
        print(
            f"  skipped unknown type: {unknown_item.activity_type} ({unknown_item.name})"
        )


def daily_sync(garmin: GarminClient, cloud: RenphoCloud, state: SyncState) -> int:
    service = HealthSyncService(garmin, cloud, state)
    exit_code = 0
    print("Daily sync: RENPHO weight → Garmin")
    try:
        for result in service.sync_renpho(service.preview_renpho("latest")):
            print(f"  weight sync: {result.status.value}")
            if result.status in {ResultStatus.ERROR, ResultStatus.UNCERTAIN}:
                exit_code = max(exit_code, 3 if result.status == ResultStatus.UNCERTAIN else 2)
    except (GarminSyncError, RenphoError, SyncStateError, SyncBusyError) as exc:
        print(f"  error: {exc}", file=sys.stderr)
        exit_code = max(exit_code, 2)

    print("Daily sync: Garmin activities (last 24h) → RENPHO")
    try:
        preview = service.preview_activities("day")
        print(
            f"  candidates: {preview.count}; duplicates: {preview.duplicate_count}; "
            f"unknown: {len(preview.unknown)}; invalid: {preview.invalid_count}"
        )
        for index, activity_result in enumerate(service.sync_activities(preview), start=1):
            print(f"  activity {index}: {activity_result.status}")
            if activity_result.status in {
                ResultStatus.ERROR.value,
                ResultStatus.UNCERTAIN.value,
            }:
                exit_code = max(
                    exit_code,
                    3 if activity_result.status == ResultStatus.UNCERTAIN.value else 2,
                )
    except (GarminSyncError, RenphoError, SyncStateError, SyncBusyError) as exc:
        print(f"  error: {exc}", file=sys.stderr)
        exit_code = max(exit_code, 2)
    return exit_code


def login_command(client: GarminClient, input_fn: Input = input) -> int:
    email = _required("Garmin email: ", input_fn)
    password = getpass.getpass("Garmin password (not saved): ")
    if not password:
        raise ValidationError("Password is required")
    name = client.login(email, password, lambda: getpass.getpass("Garmin MFA code: "))
    print(f"Login successful: {name}")
    return 0


def add_command(client: GarminClient, input_fn: Input = input) -> int:
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
        if result.status == ResultStatus.ERROR:
            raise GarminSyncError(result.message)
    print("RENPHO sync completed.")
    return 0


def schedule_command(args: argparse.Namespace) -> int:
    from . import schedule

    if args.schedule_command == "install":
        target = schedule.install(hour=args.hour, minute=args.minute)
        print(f"Daily bidirectional sync installed for {args.hour:02d}:{args.minute:02d}.")
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
