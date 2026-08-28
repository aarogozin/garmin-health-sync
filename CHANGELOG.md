# Changelog

All notable changes to Garmin Health Sync are documented here. The project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Fixed

- Fixed chart SVGs being constrained to the global 20×20 icon size, which
  made populated ECharts panels appear empty.
- Dashboard snapshots are now queued automatically after startup instead of
  leaving every chart empty until a manual action succeeds. Background work is
  serialized in the Activity Center rather than rejected while startup loading
  is still in progress.

### Removed

- The unsupported experimental Garmin-to-RENPHO activity-summary integration,
  including its CLI commands, web API routes, Sync Center controls, scheduler
  direction and local synchronization state. Garmin activities remain available
  read-only in the dashboard and reports.

### Changed

- The daily LaunchAgent now performs only the verified RENPHO body-composition
  upload to Garmin.

## [1.0.0] - 2026-08-27

### Added

- A responsive React and TypeScript health cockpit with Overview, Training,
  Recovery, Body, Blood Pressure, Reports, Sync Center and Settings sections.
- Local Garmin login/MFA and optional RENPHO onboarding without requiring the CLI.
- Interactive locally bundled charts, accessible data tables, light/dark themes,
  reorderable dashboard cards and a unified background Activity Center.
- A versioned Flask JSON API with Pydantic request contracts and generated
  TypeScript declarations.

### Changed

- Replaced the string-rendered homepage with a production SPA while preserving
  the CLI, scheduler and verified application-service write paths.
- Docker now builds the frontend in a pinned Node stage and ships only static
  assets in the unprivileged Python runtime image.
- The browser opens only after startup checks and the secure store are ready.

### Security

- Health snapshots, chart data, GPS and PDFs remain memory-only and `no-store`.
- JSON mutations use the existing per-process CSRF token, strict Host/Origin
  validation, size limits and single-worker write serialization.
- Frontend scripts, fonts and styles are self-hosted; analytics, service workers
  and external runtime dependencies are not used.

## [0.11.0] - 2026-08-27

### Added

- Experimental Garmin-to-RENPHO activity-summary synchronization for the previous
  24 hours, 30 days or all available Garmin history.
- Preview, confirmation, duplicate detection and progress reporting in both the CLI
  and local web dashboard.
- A combined daily job that uploads the latest RENPHO weight to Garmin and imports
  the previous 24 hours of mapped Garmin activities into RENPHO.
- Cross-process write locking and privacy-preserving hashes for synchronized Garmin
  activity IDs.
- Continuous integration, dependency updates, secret scanning and an automated,
  checksum-producing GitHub release workflow.

### Changed

- The macOS LaunchAgent now runs the combined daily synchronization command. Existing
  weight-only jobs are detected and can be upgraded by reinstalling the schedule.
- The local GUI now sends additional browser isolation and permissions headers and
  validates Host and Origin values using strict URL parsing.
- Container base images are pinned by digest for reproducible builds.

### Security

- Added a private vulnerability-reporting policy, ownership rules and automated
  dependency, static-analysis and credential-leak gates.
- Sanitized the scheduled daily job output so activity names, timestamps, calories,
  durations and measurement dates are not written to its operational log.
- Reject RENPHO activity templates whose official flag or name no longer matches the
  versioned mapping, preserve absolute Garmin timestamps across DST folds, and stop
  safely if all-time Garmin pagination fails to advance.
- Re-audited the source tree and Git history for committed secrets. No known leaked
  credentials or known vulnerable production dependencies were found at release time.

[0.11.0]: https://github.com/aarogozin/garmin-health-sync/releases/tag/v0.11.0
[1.0.0]: https://github.com/aarogozin/garmin-health-sync/releases/tag/v1.0.0
