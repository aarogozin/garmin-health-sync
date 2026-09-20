# Contributing

Garmin Health Sync is a local single-user application. Changes should preserve explicit upload confirmation, exact remote verification, and safe partial-data handling.

## Development setup

Use Python 3.12+, uv, and Node.js 24. Go is needed only when working on the macOS helper; ordinary users build it through Docker.

```bash
uv sync --frozen --group dev
npm --prefix frontend ci --ignore-scripts
npm --prefix frontend run build
uv run garmin-sync gui
```

For hot reload, start Flask with `GARMIN_SYNC_PORT=8080 uv run garmin-sync gui`, then run `npm --prefix frontend run dev`. Native Keychain sessions and Docker credentials are separate.

Create a focused branch. Preserve unrelated local changes and use synthetic measurements in fixtures.

## Checks

```bash
uv run ruff check .
uv run mypy
uv run pytest --cov=garmin_sync --cov-report=term --cov-fail-under=80
uv lock --check

npm --prefix frontend run schema
git diff --exit-code -- frontend/api-schema.json frontend/src/generated-api.ts
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build

(cd host_helper && go test ./...)
bash -n health-sync
```

Schema generation should change committed DTOs only when their contract intentionally changes. Generated web assets in `src/garmin_sync/web_dist` must match the current frontend source.

For browser and accessibility checks:

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

The E2E suite uses mocked API responses. It does not prove live provider behavior or every product workflow. Read-only integration smoke tests should be performed separately; any real weight or pressure upload requires explicit authorization.

## Docker checks

Build the application with `docker build -t garmin-health-sync:check .`. Build the helper separately using `docker build --target host-helper-export --output type=local,dest=/absolute/temporary/output .`. Its output is a Darwin binary; it is not part of the production image.

Compose requires archive and key paths. Validate it using dedicated temporary directories and a synthetic key, never real credentials in the source checkout. Bind only to loopback, keep the root filesystem read-only, and do not mount a Docker socket into the app.

## Code documentation

Write comments and docstrings in English. Document:

- public service and adapter functions, including their side effects and error semantics;
- canonical units, timezone assumptions, missing-data handling and source attribution;
- why writes are not retried and where duplicate checks or locks are required;
- privacy boundaries between live snapshots, archived notes, credentials and UI preferences;
- compatibility paths that cannot yet be removed.

Avoid narrating obvious statements or duplicating type annotations. Keep comments synchronized with behavior. New product UI belongs in React and `/api/v1`; remove legacy HTML only after confirming feature parity and replacing its regression coverage.

## Safety and testing

- Never automatically retry a vendor write after an ambiguous response.
- Verify uploads by reading the exact destination record.
- Keep passwords, tokens, health values and raw HTTP data out of diagnostic output.
- Keep credential-store transactions separate from cloud-write locks to avoid deadlocks.
- Do not overwrite good archive data when collection fails or loses coverage.
- Reject stale account snapshots and previews after login/logout or account changes.
- Do not commit private Compose files, keys, state, health notes, GPS, reports, or real API responses.
- Prefer behavior-based regressions for real failure modes over assertions that merely mirror implementation text.

CI runs Python/frontend checks, audits production dependencies, scans source and Git history, and validates distribution artifacts. Treat a failing coverage or security gate as an outstanding issue; do not lower it simply to obtain a passing build.

## Pull requests and releases

Explain the user-visible problem, resulting behavior, tests, and remaining limitations. Include screenshots only with synthetic data. Update README when commands or storage locations change, and add a concise Unreleased changelog entry.

Publishing a tag or release is a separate action. Before release, run the required checks, verify the exact container artifact, and review [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md) for known gaps.

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
