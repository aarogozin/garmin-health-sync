# Changelog

All notable changes to Garmin Health Sync are documented here. The project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-09-20

- Add schema-versioned Current, 7-day and 30-day AI health context exports as
  synchronized JSON and Markdown files, available from Reports, CLI and Docker.
- Include privacy-filtered training/recovery history, body-composition dynamics,
  pressure readings, Garmin strength sets/splits and conservative inferred muscle groups.
- Show Garmin VO₂ max on the Overview dashboard when the connected device exposes it.
- Reconcile the latest RENPHO measurement during GUI startup using existing duplicate,
  conflict and exact verification protections.

### Fixed

- Preserve existing Markdown health notes when a partial collection loses data.
- Serialize encrypted credential updates across GUI and scheduled processes.
- Finish expired MFA jobs, isolate account caches, preserve weekly-report links
  during dashboard refresh, and honor domain period controls.
- Preserve the running host-helper capability during status/log/schedule commands;
  rebuild helpers after source changes and preserve custom schedule storage paths.
- Return safe CLI errors for invalid credential setup and failed upload outcomes.

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

- Docker is the primary runtime through `./health-sync`; Markdown notes mount
  separately from encrypted credentials and synchronization state.
- The daily LaunchAgent performs the verified RENPHO body-composition upload to
  Garmin, then independently refreshes the enabled Markdown archive.
- Rewrote setup, migration, storage, contribution and troubleshooting documentation
  in English and documented service/adapter function contracts.

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
[1.1.0]: https://github.com/aarogozin/garmin-health-sync/releases/tag/v1.1.0
