# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
