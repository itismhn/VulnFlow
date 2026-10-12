# Architecture

## Components

| Component | Role |
|---|---|
| `web` (nginx) | Serves the built React app and proxies `/api` to the API. Sets security headers and rate-limits login. |
| `api` (FastAPI) | REST API under `/api/v1`, authentication, permissions, and audit. |
| `worker` (Celery) | Parses uploaded scans and renders reports, so large files never block requests. |
| `db` (PostgreSQL) | All application data. Uses `inet`/`cidr` types with GiST indexes for range queries. |
| `redis` | Task queue. |
| `storage` volume | Original `.nessus` files (for re-import) and generated report files. |

## Data model

```
users ──< user_networks >── networks (cidr, zone, criticality, owner)
                                 ▲ most-specific match (assets.network_id)
scans ──< scan_hosts >── assets (ip inet, hostname, os, criticality, tags)
  │                          │
  │                          └──< findings (asset, plugin, port, protocol) ── plugins
  │                                    │  status, first/last seen, assignee, due date
  └──────────< finding_occurrences >───┘  (one row per finding per scan)
                                       └──< finding_events (timeline: detected, status, assign, comment)

report_templates ──< report_jobs        audit_logs (append-only)
```

- A **finding** is unique per `(asset, plugin, port, protocol)`, so the same vulnerability on two ports is two findings.
- A **finding occurrence** records that a finding was observed in a particular scan, together with that scan's plugin output.
- A **scan host** records that a scan covered an asset, and whether it was credentialed. The lifecycle and scan comparisons depend on this.

## Import and lifecycle

Imports run in one database transaction and are serialised with a Postgres advisory lock. For each batch of hosts the importer:

1. Upserts assets (new non-empty host details win; `first_seen`/`last_seen` widen).
2. Records scan coverage in `scan_hosts`.
3. Upserts plugin definitions.
4. Applies the following rules to each observed finding:

   | Situation | Result |
   |---|---|
   | Never seen before | create as `open` |
   | Seen again in a scan newer than `last_seen` | bump `last_seen`; `fixed` becomes `reopened` |
   | Seen in an older scan | only move `first_seen` earlier |

5. Writes occurrences and timeline events.

After all hosts are processed, **auto-fix** closes active findings on covered hosts that this scan did not report, unless:
- the scan is older than the finding's last sighting;
- the finding's plugin family was disabled in this scan's policy;
- this host scan was uncredentialed but the finding was last seen by a credentialed scan.

`risk_accepted` and `false_positive` are never changed by imports.

Deleting a scan reverts the status changes it caused, removes findings that only it observed, and recomputes seen-dates from the remaining occurrences.

## Access control

- **Roles** map to permissions in `app/core/permissions.py`, and endpoints declare `require(Perm.X)`.
- **Scope**: when `user.scope_restricted` is set, `scoping.asset_scope_clause` limits every asset and finding query to addresses inside the user's networks (`ip <<= cidr`, including nested ranges). Dashboards, exports, and reports reuse the same query builder, so scope cannot be bypassed through another view.
- **Audit**: write actions and sensitive reads (exports, downloads) call `audit()` in the same transaction as the change.

## Filters

`FindingFilters` (in `schemas/finding.py`) is the single filter model, and `services/findings_query.apply_filters` is the single place it becomes SQL. The findings list, groups, exports, vulnerability list, dashboard, and reports all use it, so a filter behaves identically everywhere.
