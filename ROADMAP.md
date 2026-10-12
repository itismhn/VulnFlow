# Roadmap

This is the living plan for Report Manager. Items move from 💡 → 📋 → 🚧 → ✅ as they progress, and shipped items are recorded in [CHANGELOG.md](CHANGELOG.md).

**Legend:** ✅ done · 🚧 in progress · 📋 planned · 💡 idea (needs discussion)

Have a suggestion? [Open a feature request](https://github.com/itismhn/report-management/issues/new?template=feature_request.yml). Describe the problem in your vulnerability-management workflow, not only the solution.

---

## Phase 0: Foundation ✅

- ✅ Monorepo: FastAPI backend, React frontend, Docker Compose deployment
- ✅ PostgreSQL schema with Alembic migrations
- ✅ Local accounts with Argon2id, lockout, forced password change, refresh-token rotation, and CSRF protection
- ✅ Roles: admin, analyst, viewer
- ✅ Network-scoped users (row-level filtering everywhere)
- ✅ Append-only audit log
- ✅ CI: lint, type check, tests, Docker build, Trivy image scan, CodeQL, Dependabot

## Phase 1: v0.1 MVP ✅

- ✅ Streaming `.nessus` parser (XXE-safe, large-file friendly), multi-file upload, duplicate detection
- ✅ Background import with progress
- ✅ Finding lifecycle across scans: new, fixed, reopened, with credential and policy safeguards
- ✅ Scan history: detail, hosts, comparison with the previous scan, archive, re-import, and delete with revert
- ✅ Findings explorer with URL filters, group-by, drill-down, detail drawer, bulk actions, and CSV/XLSX export
- ✅ Assets with risk score, criticality, tags, and scan timeline
- ✅ Vulnerabilities view (by plugin / CVE)
- ✅ Networks and zones: CRUD, CSV import, automatic assignment, address-space heatmap
- ✅ Dashboard: KPIs, trend, top risks, zones, age, status, MTTR
- ✅ Reports: three built-in templates, custom templates with branding; PDF, XLSX, CSV, HTML
- ✅ Command palette search, dark mode, responsive layout
- ✅ Synthetic demo data generator

## Phase 2: v0.2 Remediation workflow ✅

- ✅ **SLA policies**: days to remediate per severity, with a default policy and per-zone overrides; automatic due dates that follow policy changes; manual dates are kept; overdue and due-soon badges
- ✅ **Risk acceptance workflow**: request with justification and expiry → approval by a second admin (self-approval is a setting) → automatic revert when it expires or is revoked
- ✅ **Scan compare page**: lists (not just counts) new, fixed, and persisting findings between any two scans
- ✅ **Saved views**: personal and shared filter presets on the findings page
- ✅ **My work** page: findings assigned to me, grouped by deadline
- ✅ Comments with @mentions and in-app notifications (mentions, assignments, risk requests, decisions, expiries)
- ✅ False positive on all hosts for a plugin, optionally limited to a range or port; also applied to future imports
- ✅ Metrics: SLA compliance %, time to fix per severity, zone and owner team, weekly detected vs fixed
- ✅ Audit log date filters, CSV export, and retention setting with a daily clean-up job
- ✅ Admin settings page: SLA policies, false-positive rules, risk-acceptance limits, audit retention, branding defaults
- 📋 SLA overrides by asset criticality (in addition to zone)
- 📋 Email or chat alerts for overdue findings (in-app badges only today)
- 📋 Password policy and session lifetimes editable in the UI (environment variables today)

## Phase 3: v0.3 Reporting & intelligence 📋

- 📋 **Scheduled reports**: weekly or monthly generation, stored on the server, optional SMTP email
- 📋 DOCX output for editable reports
- 📋 Report sections: delta since last report, remediation plan grouped by owner team, methodology/appendix
- 📋 Logo upload for report branding
- 📋 **CISA KEV** enrichment ("known exploited" flag and filter), with offline file import for air-gapped sites
- 📋 **EPSS** enrichment and a combined priority score (severity × exploitability × asset criticality)
- 📋 Per-zone and per-owner dashboards
- 💡 Compliance mapping views (PCI DSS 11.3, ISO 27001 A.8.8) with evidence export

## Phase 4: v1.0 Enterprise & integrations 📋

- 📋 **Tenable API sync**: pull finished scans from Nessus Manager / Tenable.sc on a schedule
- 📋 **Ticketing**: create and sync Jira / ServiceNow tickets from findings; close on verified fix
- 📋 Outbound webhooks (new critical, SLA breach, scan imported)
- 📋 Personal API tokens for automation
- 📋 Optional **LDAP / Active Directory** and **OIDC / SAML SSO** with group-to-role mapping
- 📋 Optional MFA (TOTP) for deployments that use local accounts
- 📋 Additional parsers: OpenVAS / Greenbone, Qualys, Nmap XML (the parser interface already supports this)
- 📋 Internationalisation with RTL layout support
- 📋 Helm chart, backup/restore guide, high-availability notes

## Ideas / backlog 💡

- 💡 Asset ownership via CMDB CSV import and owner teams as first-class objects
- 💡 Exceptions that apply to a whole network range (e.g. lab subnets)
- 💡 Compensating-control notes attached to risk acceptances
- 💡 "What changed this week" digest for managers
- 💡 Scan coverage report: ranges and hosts not scanned in N days
- 💡 Plugin output diff between two occurrences of the same finding
- 💡 Public read-only demo instance for evaluation
