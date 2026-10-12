# Report Manager

**Self-hosted vulnerability management for Nessus scan results.** Import `.nessus` exports, track every vulnerability from first detection to verified fix, slice exposure by IP range, zone, severity or asset, and produce branded reports, all inside your own network.

Built for security teams in regulated organisations (banks, payment processors, insurers) that need role-based access, network-scoped visibility, an audit trail, and an air-gapped-friendly deployment.

![Dashboard](docs/screenshots/dashboard.jpg)

## Why

Nessus is great at finding vulnerabilities. It is less helpful with the work that comes after:

- *Which findings are new since last month, which were fixed, and which came back?*
- *What is our critical exposure in the Core Banking range versus the DMZ?*
- *Who owns this, when is it due, and why was that one accepted as a risk?*
- *Can the branch IT team see only their own subnets?*
- *Can I hand management a PDF in five minutes?*

Report Manager turns a pile of scan exports into a managed, auditable vulnerability backlog.

## Features

**Scan import & history**
- Drag-and-drop `.nessus` (v2) upload. Several files at once, streamed and parsed in the background, so 100 MB+ files are fine.
- Duplicate file detection (SHA-256), progress tracking, re-import, archive, and delete. Deleting a scan reverts the status changes it caused.
- Each scan shows new, fixed, and persisting findings compared with the previous scan of the same hosts.

**Finding lifecycle that matches reality**
- Each finding is unique per *host + plugin + port + protocol* and tracked across every scan.
- Detected again → `last seen` updates; a `fixed` finding becomes **reopened**.
- Missing from a newer scan of that host → **auto-fixed**, with two safeguards against false closures:
  - an uncredentialed scan never closes findings from a credentialed one;
  - plugin families disabled in the scan policy are never closed.
- Out-of-order imports of older scans are handled correctly.
- Manual statuses: in progress, risk accepted (admin only, justification required), false positive. Imports never touch them.

**Explore & manage**
- Findings explorer with shareable URL filters: severity, status, **IP or CIDR**, network, zone, CVE, port, plugin family, CVSS, exploitability, overdue, and scan.
- **View by** host, vulnerability, network, zone, or port, then drill down with one click.
- Bulk assign, status change, due dates, and comments. Every change lands on the finding's timeline.
- Asset inventory with a risk score (severity-weighted, scaled by business criticality), scan timeline, and tags.
- Vulnerability view: where a given CVE or plugin exists across the estate.
- `⌘K` search across IPs, hostnames, CVEs, plugin IDs, and scans.

**Networks (IP ranges)**
- Name ranges and zones (Core Banking, Cards/PCI, DMZ, Branch…), set criticality and owner, or import them from CSV.
- Assets join the most specific range automatically.
- **Address-space heatmap**: every address in a range coloured by its worst open finding, so you see both risk and scan-coverage gaps.

![Network heatmap](docs/screenshots/networks-heatmap.jpg)

**Reporting**
- Built-in templates: **Executive Summary**, **Technical Detailed**, **Network / Range Report**.
- Custom templates: choose sections, default scope, intro text, and branding (company name, accent colour, classification banner such as *CONFIDENTIAL*).
- Output as **PDF, Excel (.xlsx), CSV, or HTML**. Any findings view can be turned into a report in one click.

**Access control & audit**
- Local accounts with three roles: **Admin**, **Analyst**, and **Viewer**.
- **Network scoping**: restrict a user to specific ranges. Every query, export, and report respects it.
- Append-only **audit log** covering sign-ins, failed logins, imports, status changes, exports, downloads, and admin actions.

| Findings by network | Finding detail (dark mode) |
|---|---|
| ![Findings](docs/screenshots/findings-by-network.jpg) | ![Detail](docs/screenshots/finding-detail-dark.jpg) |

## Quick start (Docker)

Requirements: Docker with Compose v2.

```bash
git clone https://github.com/itismhn/report-management.git
cd report-management
cp .env.example .env
```

Edit `.env` and set `RM_SECRET_KEY` (e.g. `openssl rand -hex 48`) and `POSTGRES_PASSWORD`. If you are not serving over HTTPS yet, set `RM_COOKIE_SECURE=false`.

```bash
make docker-up
docker compose -f deploy/docker-compose.yml exec api python -m app.cli create-admin
```

Open <http://localhost:8080> and sign in with the temporary password printed by `create-admin`. You will be asked to change it.

**Want to look around first?** Load fictional demo data, with five networks and four monthly scans:

```bash
docker compose -f deploy/docker-compose.yml exec api python -m app.cli seed-demo
```

## Local development

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+, pnpm, PostgreSQL 16+, and Redis.

```bash
make install     # backend + frontend dependencies
make dev-db      # creates rm_dev and rm_test databases
make migrate
cd backend && .venv/bin/python -m app.cli create-admin && cd ..
make demo        # optional: synthetic data
```

Then, in three terminals:

```bash
make api
```

```bash
make worker
```

```bash
make web
```

The UI runs at <http://localhost:5173> and the API docs at <http://localhost:8000/api/docs>.

PDF output needs the Pango library (`brew install pango` on macOS). HTML, Excel, and CSV work without it.

```bash
make test        # backend test suite (uses the rm_test database)
make lint        # ruff + biome
make typecheck   # mypy + tsc
```

## Architecture

```
            ┌──────────────┐     ┌───────────────────┐
 browser ──▶│ nginx (SPA)  │────▶│ FastAPI  /api/v1  │──┐
            └──────────────┘     └───────────────────┘  │   ┌────────────┐
                                          │ enqueue      ├──▶│ PostgreSQL │
                                          ▼              │   └────────────┘
                                   ┌─────────────┐       │
                                   │ Redis queue │──▶ Celery worker ──┘
                                   └─────────────┘   (parse .nessus, render reports)
```

| Layer | Technology |
|---|---|
| API | Python 3.13, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2 |
| Database | PostgreSQL: native `inet`/`cidr` types with GiST indexes for fast range queries |
| Jobs | Celery + Redis |
| Parsing | lxml streaming `iterparse` with entity resolution and network access disabled (XXE-safe) |
| Reports | Jinja2 → WeasyPrint (PDF), openpyxl (XLSX) |
| UI | React 19, TypeScript, Vite, TanStack Router & Query, Tailwind CSS v4, Radix UI, Recharts |

See [docs/architecture.md](docs/architecture.md) for the data model and lifecycle rules.

## Security

- Passwords are hashed with Argon2id. Accounts lock after repeated failures, and admin-issued passwords must be changed at first login.
- Sessions use httpOnly, SameSite=strict cookies: a short-lived access token and a rotating refresh token with reuse detection. CSRF uses a double-submit token.
- Row-level network scoping is applied in a single query helper and covered by tests.
- Uploads are size-limited, content-checked, and stored outside the web root. The XML parser cannot fetch external entities.
- Spreadsheet exports are protected against formula injection.
- nginx sends a strict Content-Security-Policy and rate-limits login.
- No external CDNs or telemetry: fonts and assets are bundled, so it works in air-gapped networks.

Found a vulnerability? Please follow [SECURITY.md](SECURITY.md).

> **Never commit real scan files.** They reveal internal addresses and weaknesses. Use the synthetic generator: `python -m app.cli demo-files`.

## Roadmap

Planned work, including SLA policies, scan diff views, KEV/EPSS enrichment, scheduled reports, Tenable API sync, Jira/ServiceNow, and LDAP/SSO, is tracked in [ROADMAP.md](ROADMAP.md).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

## License

[Apache License 2.0](LICENSE)

*Nessus is a registered trademark of Tenable, Inc. This project is independent and not affiliated with or endorsed by Tenable.*
