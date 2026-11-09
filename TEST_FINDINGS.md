# VulnFlow full-test findings (2026-11-09)

How it was tested: isolated stack (own Postgres DB `rm_e2e`, API, Celery worker, Vite UI), demo scans from
`app.cli demo-files`, then API/functional scenarios (scripted, as admin / analyst / viewer / network-scoped analyst /
scoped viewer with no networks) and browser scenarios (admin, then viewer). Existing `pytest` suite: all pass.

## Flaws to implement (ordered by severity)

### ✅ FIXED 1. [HIGH] Network-scoped users can edit/delete networks outside their scope
- `PATCH /networks/{id}` and `DELETE /networks/{id}` (`backend/app/api/v1/networks.py`, `update_network`, `delete_network`)
  only check the `networks:manage` permission, never the user's scope. `GET /networks/{id}` correctly returns 404 for the
  same network, so the user cannot even see it, yet can change criticality/CIDR or delete it.
- Repro: user `scoped1` (analyst, restricted to DMZ) sent `PATCH /networks/1 {"criticality":1}` -> 200 and
  `DELETE /networks/1` -> 204 (Core Banking, outside scope). Audit log records it.
- Also check `POST /networks` and `POST /networks/import`: a scoped analyst can create ranges anywhere, which re-assigns
  assets to a new "most specific" network and so changes what other scoped users see.
- Fix: in update/delete, load the network through the same scope filter used by GET (404 if not visible). For
  create/import, either require an unscoped user (same approach as `_unscoped()` in `suppressions.py`) or require the
  CIDR to sit inside the user's scope. Add tests in `tests/test_workflow.py` / `test_auth.py`.

### ✅ FIXED 2. [MEDIUM] Duplicate network names are allowed
- Two networks named "Core Banking" (different CIDRs) were created (201). They show up identically in every dropdown
  (findings filter, software filter) and cannot be told apart.
- Fix: unique (case-insensitive) constraint on `networks.name` (migration + 409 "A network with this name already exists",
  also in CSV import).

### ✅ FIXED 3. [LOW-MEDIUM] Logout does not require the CSRF token
- `POST /auth/logout` with only the cookies (no `X-CSRF-Token`) returns 204. A cross-site request can force-logout a user.
  SameSite=Strict limits it, so impact is low, but every other state-changing call enforces CSRF.
- Fix: do not exempt logout from the double-submit check in `core/deps.py` / `auth.py` (or revoke the session only when the header matches).

### ✅ FIXED 4. [LOW] Inflated "new" count on the first scan
- First scan: `finding_count` = 310 (info excluded) but `new_count` = 753 (info included). Scan history shows
  "+753 new" next to a severity mix totalling 310. Later scans show small numbers, so it looks like a bug.
- Fix: count new/fixed/reopened on the same basis (exclude info, or show info separately) in `services/ingest.py`
  and in the scans list column.

### ⚪ NOT A CODE BUG 5. [LOW] App name and version mismatch
- `GET /api/v1/meta` returns `{"app_name":"Report Manager","version":"0.2.0"}` while the UI, README and config say VulnFlow.
- Re-check: the code already returns `settings.app_name` (default VulnFlow) and `__version__`; could not reproduce from the source. Likely a stale or differently configured API process during the test.

### ✅ FIXED 6. [LOW] Audit export records empty details
- The `audit.exported` event stores `{"actor": null, "action": null}`; useful details (filters used, row count) are missing.

### ✅ FIXED 7. [LOW] Mobile layout: dashboard chart overflows
- At 375 px width the "Open findings over time" card is wider than the viewport (cut off on the right, horizontal scroll).
- Fix: make the chart container `min-w-0` / responsive width.

### ✅ FIXED 8. [LOW] Add-user form validation is toast-only
- Empty submit and invalid email only produce a toast with the raw backend text
  ("email: value is not a valid email address: An email address must have an @-sign."). No inline field errors, no required markers.

### 9. [INFO / design to confirm]
- Any analyst can create a global false-positive rule ("fp everywhere" suppressed 24 findings immediately) with no approval,
  while risk acceptance needs an admin. Consider requiring admin (or approval) for global rules.
- Manual status "Fixed" can be set by an analyst; the next scan that still detects it reopens it. Fine, but worth a note in the UI.
- `GET /settings` is readable by viewers (only branding/limits, no secrets); confirm that is intended.
- Software inventory lists "Oracle Database" and "Oracle Database 19c" as separate products under one vendor (normalisation).
- PDF reports fail on hosts without Pango. The error is clear, but the PDF option could be hidden/disabled when Pango is missing (health flag).
- Unsupported `.nessus` and duplicate upload handling are good; consider a clearer message for a file that is valid XML but not Nessus.

## Scenarios that passed (no action needed)
Authentication: default admin forced password change, weak password rejected, old password rejected, lockout after repeated
failures (correct password rejected while locked), admin reset unlocks and forces change, same error for unknown user vs wrong
password, refresh rotation and refresh-token reuse detection (session family revoked), deactivated user's live token rejected,
role demotion effective immediately, last-admin protection, cannot delete self.

Authorization matrix (viewer / analyst / admin): users, audit, settings, SLA, scan delete/reparse, rebuild software, risk
approval, uploads, bulk edits all return 403 where expected; anonymous gets 401 everywhere.

Network scoping: scoped user sees only DMZ findings/assets/scans counts/diff/metrics/software/search/exports; out-of-scope
finding/asset/patch/bulk are 404 or no-ops; scoped viewer with no networks sees nothing; scoped user cannot create suppression rules.

Scans: import of 4 monthly scans, duplicate detection (SHA-256), non-.nessus and fake .nessus rejected, background ingest,
new/fixed/reopened lifecycle, delete scan reverts statuses, re-import restores them.

Workflow: status/assignee/due-date/notes, @mention notification, bulk update, invalid status/assignee rejected, direct
risk-accepted blocked, risk acceptance request/approve/reject/revoke/expiry validation, four-eyes self-approval blocked,
duplicate pending request blocked, false-positive rules (global and CIDR), SLA per-zone override with recalculation, saved views.

Reports: CSV, XLSX, HTML generated and downloaded as viewer; reports are private per user (admin sees all).

Browser (admin): login error message, dashboard, findings filters + drawer + save + history timeline, note containing
`<img onerror>` rendered as text (no XSS), users, add-user dialog, settings, audit log, scans, reports, networks, metrics,
approvals (self-approval hidden for own request), vulnerabilities, software.
Browser (viewer): forced password change (mismatch message, policy checklist, direct URL gated), admin pages show
"You don't have access", no import/add-network buttons, finding drawer read-only, approvals without approve buttons.
