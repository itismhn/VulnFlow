<p align="center"><img src="docs/brand/logo.svg" alt="VulnFlow" height="48"></p>

# VulnFlow

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

VulnFlow turns a pile of scan exports into a managed, auditable vulnerability backlog.

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
- Only hosts a scan actually covered are compared, so a full `/16` sweep one month and a single-subnet scan the next can be mixed freely: hosts outside the smaller scan keep their findings as they are.
- Out-of-order imports of older scans are handled correctly: they never reopen what a newer scan fixed, and findings only an older scan saw are closed by the newer one.
- Nothing is deleted when it is fixed. Every finding keeps its status timeline and the list of scans that detected it.
- Manual statuses: in progress, risk accepted (through approval), false positive. Imports never touch them.

**Explore & manage**
- Findings explorer with shareable URL filters: severity, status, **IP or CIDR**, network, zone, CVE, port, plugin family, CVSS, exploitability, overdue, and scan.
- **View by** host, vulnerability, network, zone, or port, then drill down with one click.
- Bulk assign, status change, due dates, and comments. Every change lands on the finding's timeline.
- Asset inventory with a risk score (severity-weighted, scaled by business criticality), scan timeline, and tags.
- Vulnerability view: where a given CVE or plugin exists across the estate.
- **Software inventory**: every OS, application, package, and service version Nessus found, grouped by vendor and product (for example *Oracle* → Database, Java, Linux, each with every version found). Search for a product and a version range (for example `log4j` and `<2.17.1`) to list the hosts a new CVE affects, then export them.
- `⌘K` search across IPs, hostnames, CVEs, plugin IDs, and scans.

**Remediation workflow**
- **SLA policies** per severity, with per-zone overrides. Due dates are set automatically, follow policy changes, and show overdue and due-soon badges. Manual dates are kept.
- **Risk acceptance** with justification and expiry, approved by a second admin. The finding reopens automatically when it expires.
- **False positive on all hosts**: one rule suppresses a plugin everywhere, in a range, or on a port, including future imports.
- **My work** for assignees, **@mentions** in comments, and an in-app notification centre.
- **Saved views**, personal or shared, and a **scan compare** page listing new, fixed, and persisting findings between any two scans.
- **Remediation metrics**: SLA compliance, time to fix by severity, zone, and owner team, and weekly detected vs fixed.

**Networks (IP ranges)**
- Name ranges and zones (Core Banking, Cards/PCI, DMZ, Branch…), set criticality and owner, or import them from CSV.
- Assets join the most specific range automatically.
- **Address-space heatmap**: every address in a range coloured by its worst open finding, so you see both risk and scan-coverage gaps.

![Network heatmap](docs/screenshots/networks-heatmap.jpg)

**Reporting**
- Built-in templates: **Executive Summary**, **Technical Detailed**, **Network / Range Report**.
- Manual report designer: create opening pages with background images, logos, and positioned text; reorder sections, write custom content, and configure page layout.
- Save reusable templates, preview reports, and customize a single report without changing its template. See the [report designer guide](docs/report-designer.md).
- Output as **PDF, Excel (.xlsx), CSV, or HTML**. Any findings view can be turned into a report in one click.

**Access control & audit**
- Local accounts with three roles: **Admin**, **Analyst**, and **Viewer**.
- **Network scoping**: restrict a user to specific ranges. Every query, export, and report respects it.
- Append-only **audit log** covering sign-ins, failed logins, imports, status changes, exports, downloads, and admin actions, with CSV export and a retention setting.

**Backup & restore**
- One archive holds everything: the database, uploaded `.nessus` files, and generated reports.
- **Back up now** under *Settings*, or automatic daily or weekly backups that keep the last *N*. Download any archive from the same page.
- Restore with one command. Backups from older versions are migrated on restore. See [Backup and restore](#backup-and-restore).

| Findings by network | Finding detail (dark mode) |
|---|---|
| ![Findings](docs/screenshots/findings-by-network.jpg) | ![Detail](docs/screenshots/finding-detail-dark.jpg) |

## Installation

VulnFlow runs as five services: PostgreSQL, Redis, the API, a background worker, and the web UI (nginx). Docker is the easiest way to run them all. You can also run them directly on a host.

### Option A: Docker (recommended)

Requirements: Docker with Compose v2, `make`, and `openssl`. On Windows, see [Docker on Windows](#docker-on-windows).

```bash
git clone https://github.com/itismhn/VulnFlow.git
cd VulnFlow
make docker-env     # writes .env with random RM_SECRET_KEY and POSTGRES_PASSWORD
make docker-up      # builds images, runs migrations, creates the default admin, starts everything
```

Open <http://localhost:8080> and sign in with the [default admin](#default-admin-account) (`admin` / `admin123`). You will be asked to change the password.

### Default admin account

On a fresh install (no users in the database), migrations create one admin account:

| Username | Password |
|---|---|
| `admin` | `admin123` |

The password must be changed at first sign-in, and the new one has to meet the password policy. The account is created only when there are no users at all, so it never comes back once you have set up your own. To create another admin with a random password instead, run `create-admin` (see [Admin CLI](#admin-cli)).

**Change this password before exposing VulnFlow to anyone else.** Everyone who has read this README knows the default.

`make docker-env` sets `RM_COOKIE_SECURE=false` so sign-in works over plain `http://`. Once TLS is in front of the app, set it to `true` in `.env` and run `make docker-up` again.

**Want to look around first?** `make docker-demo` loads fictional data: five networks and four monthly scans.

Day-to-day Docker commands:

| Command | What it does |
|---|---|
| `make docker-up` | Build and start, or apply changes after `git pull` / editing `.env` (migrations run automatically) |
| `make docker-down` | Stop the stack. Data volumes are kept |
| `make docker-ps` | Container status and health |
| `make docker-logs` | Follow logs from all containers |
| `make docker-backup` | Full backup (database, scans, reports), with a copy in `backups/` |
| `make docker-restore FILE=backups/….tar.gz` | Replace all data with a backup. See [Backup and restore](#backup-and-restore) |

Without `make`, use Compose directly. Always pass `--env-file .env`, or Compose cannot resolve `POSTGRES_PASSWORD`:

```bash
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
```

Data lives in the named volumes `pgdata` (database), `storage` (uploaded scans and generated reports), `backups` (backup archives), and `redisdata`. `docker compose down -v` **deletes them**, backups included.

#### Docker on Windows

Requirements: [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with the WSL 2 backend and Linux containers (the default), and Git. You don't need `make` or `openssl`. Run these in PowerShell:

```powershell
git clone https://github.com/itismhn/VulnFlow.git
cd VulnFlow

# Same as `make docker-env`: write .env with random secrets, cookies over plain http
function New-Hex($bytes) { $b = [byte[]]::new($bytes); [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b); -join ($b | ForEach-Object { $_.ToString('x2') }) }
(Get-Content .env.example) `
  -replace '^RM_SECRET_KEY=.*', "RM_SECRET_KEY=$(New-Hex 48)" `
  -replace '^POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$(New-Hex 24)" `
  -replace '^RM_COOKIE_SECURE=.*', 'RM_COOKIE_SECURE=false' |
  Set-Content .env -Encoding ascii

# Shortcut for the long compose command (lasts for this PowerShell window)
function vf { docker compose -f deploy/docker-compose.yml --env-file .env @args }

vf up -d --build
```

Open <http://localhost:8080> and sign in with the [default admin](#default-admin-account). The `make` targets map to `vf` like this:

| Make target | PowerShell |
|---|---|
| `make docker-up` | `vf up -d --build` |
| `make docker-down` | `vf down` |
| `make docker-ps` | `vf ps` |
| `make docker-logs` | `vf logs -f --tail=100` |
| `make docker-admin` | `vf exec api python -m app.cli create-admin` |
| `make docker-demo` | `vf exec api python -m app.cli seed-demo` |

To make a backup and copy it out (same as `make docker-backup`):

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
$name = vf exec -T api python -m app.cli backup --print-name
vf cp api:/backups/$name backups/$name
```

For restoring, see [Backup and restore](#backup-and-restore).

The repository's `.gitattributes` keeps LF line endings even when Git's `core.autocrlf` is on. If you cloned an older copy that has CRLF endings, clone it again. If you prefer `make`, the Makefile also works from Git Bash or WSL with `make` installed.

#### Servers without internet access

The server doesn't need internet. On a PC that has internet, build all images into one zip, copy it over (USB stick or file share), then load and start it on the server:

```bash
make docker-bundle    # on the connected PC: writes dist/vulnflow-offline.zip
```

```bash
docker load -i vulnflow-images.tar                                          # on the server
docker compose -f deploy/docker-compose.yml --env-file .env up -d --pull never
```

**[Offline installation guide](docs/offline-install.md)** has every step for Windows and Linux: building without `make`, proxies, creating `.env`, upgrades, backups, and the server requirements. Windows Server needs WSL 2 or a Linux VM, because VulnFlow uses Linux containers.

### Option B: Without Docker

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22+, pnpm, PostgreSQL 16+, Redis, and Pango for PDF reports (`brew install pango` on macOS, `apt install libpango-1.0-0 libpangoft2-1.0-0` on Debian/Ubuntu). HTML, Excel, and CSV reports work without Pango.

**Development setup** (hot reload, default settings, no `.env` needed):

```bash
make install     # backend + frontend dependencies
make dev-db      # creates rm_dev and rm_test databases
make migrate     # also creates the default admin (admin / admin123)
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

**Production on a host:**

1. Create a database and user in PostgreSQL, and make sure Redis is running.
2. Copy `.env.example` to `backend/.env`. Set `RM_SECRET_KEY`, uncomment `RM_DATABASE_URL` and `RM_REDIS_URL`, and point them at your services. Set `RM_STORAGE_DIR` to a directory outside the web root.
3. Install and migrate: `cd backend && uv sync --no-dev && .venv/bin/alembic upgrade head`, then `.venv/bin/python -m app.cli ensure-admin` to create the [default admin](#default-admin-account), or `create-admin` for one with a random password.
4. Run the API with `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers`, and run the worker with the command from `make worker`. Use systemd or a similar tool to keep both running. Run **one** worker only, because it also runs the scheduler.
5. Build the UI with `cd frontend && pnpm install && pnpm build`, and serve `frontend/dist` with nginx. Use [frontend/nginx.conf](frontend/nginx.conf) as the template, changing `proxy_pass http://api:8000` to `http://127.0.0.1:8000`.

## Usage

1. **Add networks** (*Networks*): name your IP ranges and zones, set criticality and owner, or import them from CSV. Assets are matched to the most specific range.
2. **Import scans** (**Import scan** in the top bar): in Nessus, export a scan as **.nessus**, then drag one or more files in. Parsing runs in the background. *Scan history* shows progress and, per scan, the new, fixed, and persisting findings.
3. **Work the findings** (*Findings*, *Vulnerabilities*, *Assets*, *Software*): filter by severity, network, status, or CVE. Assign owners, set due dates, comment, accept risks, or mark false positives. Assignees see their queue under *My work*; risk acceptances wait in *Risk approvals*.
   To check a new CVE against your estate, open *Software*, search for the product, and enter the affected range in the version box, e.g. `<2.17.1` or `>=19.3 <19.21`. *By host* lists every matching host with the port or path where the software was found. Credentialed scans give the most complete inventory, because uncredentialed scans only see what network services announce.
4. **Report** (*Reports*): pick a template, scope, and format (PDF, XLSX, CSV, HTML).
5. **Administer** (*Users*, *Settings*, *Audit log*): create users with the Admin, Analyst, or Viewer role and restrict them to networks, set SLA policies, branding, and automatic backups, and review the audit log.

Press `⌘K` / `Ctrl+K` anywhere to search IPs, hostnames, CVEs, plugins, and scans.

## Help

### Make commands

Run `make help` to list every target. The main ones are `install`, `migrate`, `api`, `worker`, `web`, `demo`, `test`, `lint`, `typecheck`, and the `docker-*` targets above.

### Admin CLI

Run these inside `backend/` with `.venv/bin/python -m app.cli …`, or in Docker with `make docker-admin` / `docker compose … exec api python -m app.cli …`:

| Command | What it does |
|---|---|
| `ensure-admin` | Create the [default admin](#default-admin-account) (`admin` / `admin123`) if there are no users yet. Runs automatically after migrations |
| `create-admin [--username admin] [--email …] [--password …]` | Create an admin. A random temporary password is printed if you omit one |
| `seed-demo [--months 4] [--hosts-per-network 12]` | Load demo networks and synthetic scans into the database |
| `demo-files [--out demo-data]` | Write synthetic `.nessus` files to try the upload flow |
| `rebuild-software [--if-empty]` | Rebuild the software inventory from findings already in the database |
| `backup [--print-name]` | Write a full backup to the backup folder |
| `list-backups` | List the backups in the backup folder |
| `restore FILE [--yes] [--force]` | Replace **all** data with a backup. `FILE` is a path or the name of an archive in the backup folder |
| `--help` | Show all commands and options |

### Configuration

All settings are environment variables with the `RM_` prefix. See [.env.example](.env.example) for the full list. The ones you will most likely change:

| Variable | Default | Notes |
|---|---|---|
| `RM_SECRET_KEY` | (none) | **Required** in production, at least 32 characters. Signs session tokens |
| `RM_ENVIRONMENT` | `development` | `production` disables API docs and enforces the secret check |
| `RM_COOKIE_SECURE` | `false` | Set to `true` when served over HTTPS |
| `RM_DATABASE_URL` / `RM_REDIS_URL` | localhost | Built automatically in Docker |
| `RM_MAX_UPLOAD_MB` | `1024` | Keep `client_max_body_size` in nginx.conf in sync |
| `RM_BACKUP_DIR` | `<storage>/backups` | Where backup archives go. `/backups` in Docker (the `vulnflow_backups` volume) |
| `RM_PG_BIN_DIR` | (PATH) | Folder with `pg_dump` / `pg_restore` if they are not on `PATH`. Included in the Docker image |
| `HTTP_PORT` | `8080` | Docker only: host port for the UI |

### Backup and restore

A backup is one `.tar.gz` file with the database, the uploaded `.nessus` files, and generated reports, plus a `manifest.json` describing what is inside. Make one in three ways:

- **Settings → Backups → Back up now**. The same page lists, downloads, and deletes archives.
- **On a schedule**: set *Automatic backups* to daily or weekly. They run at 01:30 UTC from the worker, and only the newest *Keep* of them are kept. Manual backups are never deleted automatically.
- **From the command line**: `make docker-backup`, or `python -m app.cli backup`.

Archives are written to `RM_BACKUP_DIR` (in Docker, the `vulnflow_backups` volume). **A backup on the same disk doesn't survive losing that disk.** Copy archives to another server, or replace the volume in `deploy/docker-compose.yml` with a bind mount to a network share, such as `- /mnt/nas/vulnflow:/backups`.

Archives contain every finding and the users' password hashes, so store them like the database itself. The `.env` file is **not** included. Keep a copy of it with your backups: without the same `RM_SECRET_KEY` nothing breaks, but everyone has to sign in again.

**Restore** replaces everything currently in VulnFlow with the backup's contents:

```bash
make docker-restore FILE=backups/vulnflow-20261110-013000-scheduled.tar.gz
```

This copies the file into the backups volume, stops the web, api, and worker containers, asks for confirmation, restores, and starts everything again. Without `make`, run the same steps by hand:

```bash
docker compose -f deploy/docker-compose.yml --env-file .env cp backups/FILE.tar.gz api:/backups/
docker compose -f deploy/docker-compose.yml --env-file .env exec -T -u root api chown app /backups/FILE.tar.gz
docker compose -f deploy/docker-compose.yml --env-file .env stop web api worker
docker compose -f deploy/docker-compose.yml --env-file .env run --rm --no-deps api python -m app.cli restore FILE.tar.gz
docker compose -f deploy/docker-compose.yml --env-file .env up -d
```

Without Docker, stop the API and worker, then run `.venv/bin/python -m app.cli restore /path/to/FILE.tar.gz` in `backend/`.

Notes:
- A backup from an older VulnFlow version is upgraded to the current schema during the restore. A backup from a **newer** version is refused: upgrade VulnFlow first.
- The restore refuses to run while other database connections are open (the API or worker still running). `--force` overrides this.
- All sessions are ended, so everyone signs in again afterwards. The restore is recorded in the audit log.
- The archive is checked before anything is changed: unexpected entries, missing parts, or paths outside the storage folder stop the restore.
- `pg_dump` must be the same major version as the PostgreSQL server or newer. The Docker image ships version 17, matching the bundled `postgres:17` database.

### Troubleshooting

- **Sign-in succeeds but you land back on the login page:** you are on plain `http://` with `RM_COOKIE_SECURE=true`. Set it to `false`, or put HTTPS in front.
- **`api` keeps restarting with "Set RM_SECRET_KEY…":** the key is missing, still `change-me`, or shorter than 32 characters.
- **`required variable POSTGRES_PASSWORD is missing`:** you ran `docker compose` without `--env-file .env`. Use the `make docker-*` targets.
- **API cannot connect to the database after changing `POSTGRES_PASSWORD`:** the database volume keeps the original password. Change it back, or update the password inside PostgreSQL.
- **Upload stuck in "queued":** the worker is not running. Check `make docker-logs` (Docker) or the `make worker` terminal.
- **PDF reports fail outside Docker:** install Pango (see requirements above).
- **`unable to get image 'vulnflow-api:latest': request returned 500`:** the Docker client can't reach a Linux engine. Docker Desktop is not running, it is set to Windows containers, or the host only has the Windows Server engine. See [Servers without internet access](#servers-without-internet-access).
- **Port 8080 already in use:** set `HTTP_PORT` in `.env` and run `make docker-up` again.

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

Planned work, including KEV/EPSS enrichment, a report template builder, scheduled reports, Tenable API sync, Jira/ServiceNow, and LDAP/SSO, is tracked in [ROADMAP.md](ROADMAP.md).

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

## License

[Apache License 2.0](LICENSE)

*Nessus is a registered trademark of Tenable, Inc. This project is independent and not affiliated with or endorsed by Tenable.*
