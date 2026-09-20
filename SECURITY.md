# Security policy

## Supported version

Security fixes are provided for the latest release only. This project depends on
unofficial Garmin Connect and RENPHO interfaces, so compatibility fixes may require
upgrading promptly.

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/aarogozin/garmin-health-sync/security/advisories/new).
Do not open a public issue containing credentials, tokens, health data, report IDs,
API responses, or reproduction steps that expose another account.

Include the affected version, impact, minimal reproduction steps, and any suggested
mitigation. Reports should use synthetic data whenever possible.

## Security boundary

The GUI is designed for a single local user and must remain bound to loopback. Running
it behind a public reverse proxy, sharing the Docker secret key, or committing local
state is unsupported. Garmin and RENPHO credentials must be revoked independently if
the host or its secret store is compromised.

The optional Markdown archive is **plaintext health data**, not a credential store.
Its private filesystem permissions do not prevent access by other applications
running as the same user. A Documents folder may also be synchronized by iCloud or
backup software. Choose an appropriate location and review files before sharing
them with an AI service. Never put the archive in a public repository.

Docker credentials are encrypted in the data volume using a separate host-side
key. Back up the volume and its matching key together; keep both separate from
shared Markdown notes. The macOS helper permits only fixed scheduling and archive
folder actions and requires a local capability token. It is not a general-purpose
remote administration service. Its checksum is not a publisher signature.
