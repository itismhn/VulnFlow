# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
