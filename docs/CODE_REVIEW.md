# Code review — 2026-09-04

## Scope and approach

This review covered the Python adapters and application services, API/job lifecycle,
credential storage, archive persistence, CLI/scheduling, Docker launcher and host
helper, React data flows, packaging, tests, and documentation. It included static
inspection and synthetic regression tests. It is not a penetration-test certificate
or a guarantee that unofficial provider APIs will remain compatible.

No health records were uploaded or deleted. Tests must not reuse a live account or
commit personal fixtures. Existing unrelated working-tree changes were preserved.

## Findings addressed

| Area | Problem | Change |
| --- | --- | --- |
| Launcher | Inspection commands could replace runtime configuration or invalidate the running bridge token. | Separate initialization from command forwarding; preserve configuration for status, logs, sync, archive and schedule operations. |
| Launcher | Concurrent startup and a missing existing encryption key could compromise configuration consistency. | Serialize startup, write Compose configuration atomically, and require restoration rather than replacing a missing key. |
| Scheduling | Helper errors could escape as server errors; malformed input and arbitrary bridge targets were insufficiently constrained. | Safe unavailable states, fixed destinations, no redirects, strict payload validation and bounded subprocess timeouts. |
| Credentials | Concurrent encrypted-store read/modify/write operations could lose another process's update. | A dedicated filesystem transaction lock around local credential mutations. |
| Sessions | Account changes could retain stale snapshots or queued work; MFA timeout could leave the worker busy. | Session generations, cache invalidation, stale-job rejection and terminal MFA timeout cleanup. |
| Reports | Dashboard refreshes could replace weekly export state; displayed periods could disagree with collection periods. | Separate report purposes, preserve immutable exports, and derive titles from the actual date span. |
| CLI | Some unsuccessful sync outcomes could return a successful exit code. | Explicit nonzero outcomes while keeping archive collection independent of weight sync. |
| Archive | An incomplete refresh could overwrite a previously valid note. | Preserve existing daily, weekly and profile notes on partial collection; atomically create missing notes. |
| UI | Period controls, initial refresh and rejected asynchronous actions had gaps. | Connect period selection to collection, keep refresh available, and expose safe errors in the Activity Center. |
| Job contracts | Malformed job acknowledgments or polling payloads could crash the Activity Center. | Reject invalid acknowledgments safely; ignore malformed polls without changing the running job or repeating a write. Update stale browser mocks to follow the current API. |
| Provider checks | Duplicate-read errors did not consistently pass through the sanitized adapter boundary. | Use the shared read boundary and preserve authentication/rate-limit outcomes. |

Regression tests accompany these changes. Function docstrings and selected TypeScript
comments explain contracts, privacy boundaries, synchronization and failure behavior;
they intentionally do not narrate trivial statements.

## Vestiges and retained compatibility

- Removed an unused generic mapping helper and unused all-history activity reader
  left over from reverse activity synchronization. Garmin → RENPHO activity upload
  is not an advertised feature.
- Removed stale bidirectional-sync wording from current CLI/package documentation.
- The legacy HTML rendering paths are **not yet safe to delete**. React does not
  fully reproduce their route, lifestyle/association and reference-band presentation.
  Retire them only after functional-parity tests; maintaining both increases review
  and security-testing work.
- Generated frontend bundles are build artifacts, not independent implementations.
  Rebuild them from TypeScript; do not hand-edit hashed JavaScript.

## Remaining work and limitations

1. Complete React report parity before removing compatibility HTML. Test each
   supported report section, not just dashboard navigation and chart presence.
2. Improve partial archive merging. The conservative preservation policy avoids data
   loss but may leave an existing note stale when optional endpoints remain unavailable.
3. Reduce the lazy chart bundle (approximately 554 kB minified at this review).
   The production build succeeds, but emits a chunk-size warning.
4. Extend browser coverage for onboarding/MFA, archive backfill and all report
   sections. Current browser tests are synthetic smoke checks, not full live parity.
5. Verify the macOS LaunchAgent and Docker Desktop host-helper connection on a real
   installation before relying on unattended scheduling. Unit tests cannot establish
   Docker Desktop networking, macOS file-sharing or launchd behavior.
6. The host-helper checksum detects local artifact changes; it is not a signed or
   notarized release. Do not describe the helper as publisher-verified.

## Verification

The review run passed Ruff, strict mypy, 150 Python tests and the 80% coverage gate
(81.39% measured coverage). Frontend lint, TypeScript, eight Vitest tests, six
desktop/mobile Playwright tests (including an axe accessibility check) and the
production build passed. API schema regeneration produced identical files.
Host-helper Go tests, launcher shell syntax, lock-file
verification and whitespace checks passed. Python and npm dependency audits found
no known vulnerabilities; Bandit reported no security findings.

The current Docker build could not resolve Docker Hub's Dockerfile frontend image
because the registry request timed out. A fresh-image runtime smoke test is therefore
not verified by this review; rerun it when registry access is restored.

These checks do not establish correctness of live Garmin/RENPHO endpoints, medical
interpretations or every platform configuration. Audit results describe the tested
working tree, not a published release. No tag, commit or push is implied.
