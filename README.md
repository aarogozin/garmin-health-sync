# Garmin Health Sync

[![CI](https://github.com/aarogozin/garmin-health-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/aarogozin/garmin-health-sync/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/aarogozin/garmin-health-sync)](https://github.com/aarogozin/garmin-health-sync/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A privacy-first local health cockpit that connects Garmin, RENPHO and manual blood-pressure readings, with a full React dashboard, verified synchronization and seven-day reports.

![Garmin Health Sync v1 dashboard](docs/images/product-dashboard.png)

_Anonymized product preview; the application does not ship or persist these sample values._

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
uv run garmin-sync gui
```

The browser opens only after the local server and secure stores are ready. The onboarding flow connects Garmin, handles MFA and optionally connects RENPHO without requiring terminal commands. Garmin OAuth data and RENPHO credentials are stored in macOS Keychain under the `garmin-health-sync` service. The Garmin password is used only during login and is never saved.

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

## Product dashboard and reports

`garmin-sync gui` waits for initial account checks, opens a random `127.0.0.1` port in the system browser and runs until `Ctrl+C`.

The v1 dashboard is organized into `Overview`, `Training`, `Recovery`, `Body`, `Blood Pressure`, `Reports`, `Sync Center` and `Settings`. It provides:

- a Today dashboard with seven-day sleep, stress, Body Battery and heart-rate context;
- interactive charts with keyboard-accessible data tables;
- manual blood-pressure review and exact duplicate protection;
- RENPHO composition and circumference history;
- previewed synchronization in both directions;
- an Activity Center for running, verified, partial and uncertain operations;
- light/dark themes and reorderable dashboard cards;
- seven-day web/PDF reports with 30-day Lifestyle Logging context.

The responsive interface supports desktop, tablet and mobile screens. Only theme and card-order preferences are stored in browser storage; health data is not.

External scripts, fonts and analytics are blocked. Route maps are local by default. Enabling the OpenStreetMap background is an explicit opt-in that exposes your IP address and requested tile region to OpenStreetMap.

## Docker

Docker uses an encrypted persistent credential store because a Linux container cannot access macOS Keychain. The encrypted data volume and its key must be backed up together, but stored separately. Neither is committed to Git.

### One-line Docker kickstart (macOS)

For a new machine with Docker Desktop, this clones the project, creates a local
encryption key with restrictive permissions, builds the image, starts the
loopback-only dashboard, and opens it:

```bash
git clone https://github.com/aarogozin/garmin-health-sync.git && cd garmin-health-sync && mkdir -p docker && (umask 077; openssl rand -base64 32 > docker/secret.key) && docker compose up --build -d && open http://localhost:8080
```

At `http://localhost:8080`, use the **Connect Garmin** and **Connect RENPHO**
forms in onboarding. Garmin MFA is requested in the Activity Center. The
browser sends credentials only to the local loopback container; the Garmin
password is cleared after the login job, and only the OAuth session plus RENPHO
credentials are retained in the encrypted Docker volume.

### Manual setup and recovery

```bash
mkdir -p docker
python3 -c 'import base64,secrets,pathlib; pathlib.Path("docker/secret.key").write_bytes(base64.urlsafe_b64encode(secrets.token_bytes(32)))'
chmod 600 docker/secret.key
```

`docker/secret.key` is ignored by both Git and the Docker build context. Never commit or paste it into Compose environment variables.

Build and start the dashboard:

```bash
docker compose build
docker compose up -d
open http://localhost:8080       # macOS
# Visit http://localhost:8080 on other platforms.

docker compose ps
docker compose logs --tail=50
docker compose down
```

Use the browser onboarding or **Settings** to authenticate. The optional CLI
remains available for terminal-only use:

```bash
docker compose run --rm app login
docker compose run --rm app renpho login
docker compose run --rm app status
```

CLI Garmin login supports MFA. Credentials are encrypted into the
`garmin-sync-data` Docker volume using the mounted key.

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
cd frontend && npm ci && cd ..

# Backend
uv run ruff check .
uv run mypy
uv run pytest
uv lock --check

# Frontend contract, quality and production bundle
cd frontend
npm run schema
npm run lint
npm test
npm run build
```

For live frontend development, run Flask on port `8080`, then `npm run dev` in `frontend/`. Vite proxies `/api` and `/assets` to Flask. Production and Docker serve hashed assets from the Python package, and the final container contains no Node runtime.

The versioned internal API lives under `/api/v1`. Request/response models are defined with Pydantic; `npm run schema` regenerates `frontend/api-schema.json` and TypeScript declarations. The API is loopback-only and is not a supported internet-facing integration surface.

Tests use fake clients and do not contact real accounts. A manual smoke test should use disposable readings that can be checked and removed in the official Garmin interface.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution and release checks. Changes are documented in [CHANGELOG.md](CHANGELOG.md).

## Legal and attribution

This project is not affiliated with Garmin or RENPHO. Garmin, Garmin Connect and RENPHO are trademarks of their respective owners. Third-party asset attribution is documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
