# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Changed
- The project is now called **VulnFlow**, with a new logo and favicon. Existing Docker deployments keep their data: the volumes, database name, and `RM_` settings are unchanged.

### Added
- **Backup and restore**: one `.tar.gz` archive with the database, uploaded scans, and generated reports. Admins can make, download, and delete backups under *Settings → Backups*, or turn on automatic daily or weekly backups that keep the newest *N*. CLI: `backup`, `list-backups`, and `restore`. Make targets: `make docker-backup` (now a full backup instead of a database dump only) and `make docker-restore FILE=…`. Restoring a backup from an older version upgrades it to the current schema, ends all sessions, and is recorded in the audit log. Docker stores archives in a new `vulnflow_backups` volume; set `RM_BACKUP_DIR` to put them elsewhere.
- **Software inventory** (*Software* page): every operating system, application, package, and network service Nessus detected, with its version, grouped by product with a host count per version. Search by product, vendor, or CPE. Filter by category, network, IP range, and version expressions such as `19.3`, `2.4.*`, `<2.17.1`, or `>=2.0 <2.17.1` to find the hosts a CVE affects. Export the matching hosts to CSV or Excel.
- Versions are read from the CPE plugin, SSH package lists (dpkg and rpm), Windows installed software, HTTP and SSH banners, the Oracle TNS listener, and the `Version :` blocks of detection plugins. The same install reported by several plugins is merged per host.
- A *Software* section on each asset page.
- The inventory is rebuilt after every import and scan deletion. Existing deployments build it once from stored findings during the upgrade, and admins can rebuild it from the page or with `python -m app.cli rebuild-software`.
- **By vendor** view, now the default on the *Software* page: Oracle, Microsoft, Apache, and so on, each with its products. Expand a vendor to see every version of each product and how many hosts run it.
- Software reported by name only (Windows installed software, detection plugins without a CPE) is matched to its vendor and product, and versions and architectures are taken out of the name. For example, `7-Zip 16.04 (x64)` and `7-Zip 23.01 (x64)` are one product with two versions, `Oracle Database 19c` joins *Oracle Database*, and `Java 8 Update 361` joins *Java* under Oracle. Linux packages such as `openssl`, `openssh-server`, and `java-*-openjdk` join their product too. After upgrading, click *Rebuild* on the *Software* page (or run `python -m app.cli rebuild-software`) to regroup existing data.
- Demo data includes software stacks, such as Oracle Database, Log4j, OpenSSH, and Apache, whose versions change between scans.

### Security
- Network-restricted users now see scan host and finding counts for their own networks only, not totals across all networks.
- The audit log is append-only in the database: a trigger rejects updates and deletes, except the scheduled retention purge.
- Failed reports and imports no longer show raw exception text (which could include server paths); details stay in the server logs.
- Signing out ends the session immediately: access tokens are tied to their sign-in and stop working on logout, password reset, or deactivation.
- A locked account gets the same "invalid username or password" answer as a wrong password, so it no longer reveals that the username exists.
- Failed sign-ins are throttled per IP address across all usernames (`RM_MAX_FAILED_LOGINS_PER_IP`, default 20 per lockout window).
- Client addresses can no longer be forged with `X-Forwarded-For`: the bundled nginx overwrites the header and the API no longer reads it directly. See `frontend/nginx.conf` for running behind a load balancer.
- Spreadsheet exports also neutralize cells starting with a tab or carriage return.

### Fixed
- When a scan's policy disables a plugin family, that scan no longer auto-fixes findings from the family on its first import. Before, the policy was read only after auto-fix ran.
- Out-of-order imports: a finding that only an older scan detected is now closed when a newer scan of that host, already imported, did not see it. An older scan imported late also no longer reopens a finding that a newer scan had fixed.
- RPM packages whose names contain version numbers (for example `java-1.8.0-openjdk`) keep their full name instead of being cut short.
- Findings, assets, scans, and vulnerabilities that don't exist or are outside the user's scope show a "not found" message instead of loading forever.
- Admin pages and My work show an access-denied message to users without permission, instead of an empty page.
- A missing Pango library now always produces a clear PDF error, including when it fails during rendering.
- Finding history shows the scan name and scan date for import events, and "First detected" matches the finding's first-seen date.
- The scans table fits medium-width screens without horizontal scrolling.
- Audit log details are shown as readable key/value pairs instead of raw JSON.
- Demo plugin descriptions no longer name a single host.

## [0.2.0]: remediation workflow

### Added
- SLA policies (default and per zone) with automatic due dates, overdue and due-soon badges, and "reset to SLA" for manual dates.
- Risk-acceptance requests with justification and expiry, a separate approver (four-eyes by default), revocation, and automatic expiry back to the previous status.
- False-positive rules that suppress a plugin on all hosts, a range, or a port, including in future imports. Deleting a rule reopens what it suppressed.
- Scan compare page listing new, fixed, and persisting findings between any two scans.
- Saved views on the findings page, personal or shared.
- My work page with assigned findings grouped by deadline.
- @mentions in comments and an in-app notification centre.
- Remediation metrics: SLA compliance, time to fix by severity, zone, and owner, and weekly velocity.
- Admin settings page; audit log date filters, CSV export, and retention.
- Scheduled jobs (Celery beat in the worker) for risk expiry and daily maintenance.

### Changed
- Findings can no longer be set to "Risk accepted" directly; use the request and approval flow.
- Analysts can request risk acceptance; only admins approve.

## [0.1.0]: first public release

### Added
- Import of Nessus `.nessus` (v2) files with streaming, XXE-safe parsing, background processing, and duplicate detection.
- Finding lifecycle across scans (new, fixed, reopened), with safeguards for uncredentialed scans and disabled plugin families.
- Scan history with per-host results and comparison against the previous scan.
- Findings explorer: filters (including IP/CIDR), grouping, drill-down, detail drawer, bulk actions, CSV/XLSX export.
- Assets with risk scoring, criticality, and tags; vulnerabilities view by plugin/CVE.
- Networks and zones with CSV import, automatic asset assignment, and an address-space heatmap.
- Dashboard with KPIs, trend, top risks, zone exposure, finding age, and MTTR.
- Reports: Executive Summary, Technical Detailed, and Network templates; custom branded templates; PDF, XLSX, CSV, HTML.
- Local authentication, three roles, network-scoped users, and an audit log.
- Docker Compose deployment, CI pipeline, and synthetic demo data.
