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
