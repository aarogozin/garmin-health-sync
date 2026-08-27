# Contributing

Thanks for helping improve Garmin Health Sync. This project handles sensitive personal
health data and uses unofficial vendor APIs, so conservative changes and explicit failure
states are more important than automatic retries.

## Development setup

Requirements: Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/aarogozin/garmin-health-sync.git
cd garmin-health-sync
uv sync --frozen --group dev
```

Create a branch, keep each change focused, and add regression tests. Tests must use fake
clients and must not contact Garmin or RENPHO accounts by default.

## Required checks

```bash
uv run ruff check .
uv run mypy
uv run pytest --cov=garmin_sync --cov-report=term --cov-fail-under=80
uv lock --check
uv build
```

CI also audits locked production dependencies, scans Python code and checks the complete
Git history for credentials. Never commit Keychain exports, `.env` files, Docker secret
keys, API responses, health-data snapshots, generated reports, GPS tracks or logs.

## Safety rules

- Never retry a write automatically after an ambiguous vendor response.
- Verify a write by reading the exact destination record whenever the endpoint permits it.
- Keep tokens, passwords, HTTP bodies and personal health values out of logs and errors.
- Keep the GUI loopback-only. Do not add a public bind option without a real authorization
  and deployment design.
- Treat vendor payloads as untrusted and tolerate missing or changed optional fields.
- Clearly label unofficial or experimental integrations.

Live smoke tests are opt-in and should use a disposable record that can be verified and
removed in the official app. Never place real credentials in test fixtures or issues.

## Security reports

Do not open a public issue for a suspected vulnerability. Follow [SECURITY.md](SECURITY.md)
and use GitHub's private security advisory form.
