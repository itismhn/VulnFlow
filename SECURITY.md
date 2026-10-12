# Security policy

Report Manager stores sensitive vulnerability data, so we take reports seriously.

## Reporting a vulnerability

Please **do not open a public issue.** Report privately through [GitHub Security Advisories](https://github.com/itismhn/report-management/security/advisories/new).

Include:
- the affected version or commit
- steps to reproduce, or a proof of concept
- the impact you believe it has

You can expect an acknowledgement within 5 working days. We will keep you informed while we work on a fix and credit you in the release notes unless you prefer otherwise.

## Supported versions

Security fixes go into the latest release. Please upgrade before reporting.

## Hardening your deployment

- Set a strong, unique `RM_SECRET_KEY` and database password. The API refuses to start in production with the default key.
- Serve over HTTPS and keep `RM_COOKIE_SECURE=true`.
- Restrict network access to the web port to your security team's networks.
- Back up the PostgreSQL volume and the `storage` volume. The `storage` volume holds the original scan files.
- Review the audit log periodically, especially `auth.login_failed`, `auth.refresh_reuse`, and `findings.exported`.
