# Changelog

All notable changes to Garmin Health Sync are documented here. The project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
