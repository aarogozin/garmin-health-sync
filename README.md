# Garmin Health Sync

[![CI](https://github.com/aarogozin/garmin-health-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/aarogozin/garmin-health-sync/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/aarogozin/garmin-health-sync)](https://github.com/aarogozin/garmin-health-sync/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A privacy-first local CLI and web dashboard that brings health data from RENPHO and manual blood-pressure readings into Garmin Connect, then combines them with Garmin activity and recovery data in a seven-day report.

> [!WARNING]
> This project uses unofficial Garmin Connect and reverse-engineered RENPHO APIs. They may change without notice. The application is for personal tracking, not diagnosis or medical record keeping. Verify writes in Garmin Connect and consult a healthcare professional about medical measurements.

## What it does

- Uploads RENPHO weight and compatible body-composition metrics to Garmin Connect.
- Experimentally copies Garmin activity summaries to RENPHO (type, start time, duration and calories).
- Adds manual blood-pressure readings with exact duplicate detection.
- Shows RENPHO body-composition and circumference history.
- Produces an English web/PDF weekly report with activities, sleep, HR/HRV, stress, Body Battery, readiness, blood pressure, weight and other available Garmin domains.
- Provides rule-based, source-linked observations without claiming diagnosis or causation.
- Supports an English localhost GUI, CLI workflows and daily macOS `launchd` synchronization.

All report snapshots, PDFs, GPS routes and detailed health records remain in process memory. The application does not log API bodies, tokens, passwords or health values.

## Quick start on macOS

Requirements: macOS, Python 3.12+, and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/aarogozin/garmin-health-sync.git
cd garmin-health-sync
uv sync --frozen

uv run garmin-sync login
uv run garmin-sync renpho login
uv run garmin-sync gui
```

Garmin OAuth data and RENPHO credentials are stored in macOS Keychain under the `garmin-health-sync` service. The Garmin password is used only during login and is never saved.

## CLI reference

```bash
# Garmin
uv run garmin-sync login
uv run garmin-sync status
uv run garmin-sync add
uv run garmin-sync logout

# RENPHO
uv run garmin-sync renpho login
uv run garmin-sync renpho status
uv run garmin-sync renpho sync --latest
uv run garmin-sync renpho sync --all
uv run garmin-sync renpho sync --latest --yes
uv run garmin-sync renpho logout

# Experimental Garmin → RENPHO activity summaries
uv run garmin-sync activities preview --period day
uv run garmin-sync activities sync --period day
uv run garmin-sync activities sync --period month
uv run garmin-sync activities sync --period all

# Both directions: latest RENPHO weight and the last 24h of Garmin activities
uv run garmin-sync sync daily

# Local web dashboard
uv run garmin-sync gui

# Safe operational diagnostics (never request/response bodies or secrets)
uv run garmin-sync --diagnostic status
```

Uploads require confirmation unless `--yes` is explicitly used. Exit code `3` means Garmin or RENPHO returned an uncertain write result: inspect the destination before retrying to avoid a duplicate.

## Dashboard and reports

`garmin-sync gui` waits for initial account checks, opens a random `127.0.0.1` port in the system browser and runs until `Ctrl+C`.

The dashboard provides Garmin status and manual blood pressure; RENPHO sync, composition and circumference history; previewed Garmin → RENPHO activity sync for 24 hours, 30 days or all time; and a seven-day web/PDF report with a 30-day Lifestyle Logging context. Charts, activity links and optional GPS routes are available locally.

External scripts, fonts and analytics are blocked. Route maps are local by default. Enabling the OpenStreetMap background is an explicit opt-in that exposes your IP address and requested tile region to OpenStreetMap.

## Docker

Docker uses an encrypted persistent credential store because a Linux container cannot access macOS Keychain. The encrypted data volume and its key must be backed up together, but stored separately. Neither is committed to Git.

### 1. Create the local encryption key

```bash
mkdir -p docker
python3 -c 'import base64,secrets,pathlib; pathlib.Path("docker/secret.key").write_bytes(base64.urlsafe_b64encode(secrets.token_bytes(32)))'
chmod 600 docker/secret.key
```

`docker/secret.key` is ignored by both Git and the Docker build context. Never commit or paste it into Compose environment variables.

### 2. Build and authenticate

```bash
docker compose build
docker compose run --rm app login
docker compose run --rm app renpho login
docker compose run --rm app status
```

The interactive commands support Garmin MFA. Credentials are encrypted into the `garmin-sync-data` Docker volume using the mounted key.

### 3. Start the dashboard

```bash
docker compose up -d
open http://localhost:8080       # macOS
# Visit http://localhost:8080 on other platforms.

docker compose ps
docker compose logs --tail=50
docker compose down
```

Compose publishes only `127.0.0.1:8080`, drops Linux capabilities, enables `no-new-privileges`, uses a read-only root filesystem and runs as an unprivileged user. Do not expose this service through a public reverse proxy.

To update:

```bash
git pull --ff-only
docker compose build --pull
docker compose up -d
```

To remove container data, first run `docker compose down`, then explicitly remove the `garmin-sync-data` volume. That operation permanently deletes saved sessions and duplicate-protection state.

### Docker limitations

- macOS `schedule` commands use `launchd` and are unavailable inside Linux containers;
- the container does not open a browser automatically;
- changing or losing `docker/secret.key` makes the encrypted credential volume unreadable;
- Docker improves portability, not the stability of unofficial vendor APIs.

## Daily bidirectional sync on macOS

First verify `status` and `renpho status`, then install the job:

```bash
uv run garmin-sync schedule install                 # daily at 09:00
uv run garmin-sync schedule install --hour 7 --minute 30
uv run garmin-sync schedule status
uv run garmin-sync schedule run
uv run garmin-sync schedule uninstall
```

The job uploads the latest unsynchronized RENPHO measurement to Garmin, then copies mapped Garmin activities from the rolling previous 24 hours to RENPHO. Re-run `schedule install` after upgrading from a weight-only schedule. Its sanitized operational log is at `~/Library/Logs/GarminHealthSync/renpho-sync.log`. Duplicate state is stored with mode `0600` at `~/Library/Application Support/garmin-health-sync/state.json`; Garmin activity IDs are stored only as hashes and no activity values are persisted.

## Data behavior

- Naive timestamps use `Europe/Berlin`; decimal comma and decimal point are accepted.
- When RENPHO has several readings on one day, the last reading is selected because Garmin exposes one resulting body-composition record per calendar day.
- A conflicting Garmin weight is never overwritten automatically.
- RENPHO muscle and bone percentages are converted to kilograms. Metabolic age is displayed but not sent because Garmin FIT import corrupts that field.
- Blood-pressure duplicates match UTC timestamp, systolic, diastolic and pulse before any POST and are verified after a write.
- A network failure or ambiguous response never triggers an automatic write retry.
- Garmin → RENPHO is experimental and uses an undocumented endpoint. Unknown activity types are skipped; RENPHO receives only the mapped type, start time, duration and integer calories.
- Imported summaries appear in RENPHO's manual activity area (`Quick Log` / `Activity Management`), not in device workout history. The exact label may vary by RENPHO app version.

## Security model

- Native secrets: macOS Keychain.
- Container secrets: Fernet-encrypted `credentials.enc`, mode `0600`, with a separately mounted key.
- GUI: loopback only, per-process CSRF token, Host/Origin validation, POST-only mutations, request-size limits, CSP and output escaping.
- Dependencies are locked in `uv.lock`; containers install with `uv sync --frozen`.
- `.env`, secret keys, state, logs, generated PDFs, caches and virtual environments are ignored.

This is a single-user local application. It has no multi-user authorization layer and must not be exposed directly to a LAN or the internet.

Please report vulnerabilities privately as described in [SECURITY.md](SECURITY.md). Do not include credentials, tokens, health records or diagnostic dumps in a public issue.

## Troubleshooting

**No saved Garmin session** — run `garmin-sync login` in the same native environment or Docker volume used by the GUI.

**RENPHO unavailable** — run `garmin-sync renpho status`; vendor API changes may require a dependency update.

**Docker reports an invalid credential store** — confirm the same `docker/secret.key` is mounted. Do not overwrite the key if the existing volume contains credentials.

**Garmin rate limit or uncertain upload** — do not retry automatically. Wait, inspect Garmin Connect, then retry only if the record is absent.

**Report is partial** — unavailable device-specific domains are reported explicitly; data already collected remains usable.

## Development

```bash
uv sync --frozen --group dev
uv run ruff check .
uv run mypy
uv run pytest
uv lock --check
```

Tests use fake clients and do not contact real accounts. A manual smoke test should use disposable readings that can be checked and removed in the official Garmin interface.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution and release checks. Changes are documented in [CHANGELOG.md](CHANGELOG.md).

## Legal and attribution

This project is not affiliated with Garmin or RENPHO. Garmin, Garmin Connect and RENPHO are trademarks of their respective owners. Third-party asset attribution is documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
