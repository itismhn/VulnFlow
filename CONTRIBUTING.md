# Contributing

Thanks for helping improve Report Manager.

## Ground rules

- **Never commit real scan data**, IP addresses, hostnames, or screenshots from a real environment. Use `python -m app.cli demo-files` or `make demo` for fictional data.
- Security issues go to [SECURITY.md](SECURITY.md), not public issues.
- For larger changes, open an issue first so we can agree on the approach. Check [ROADMAP.md](ROADMAP.md) to see what is planned.

## Setup

Follow **Local development** in the [README](README.md). Run these before you open a pull request:

```bash
make lint
```

```bash
make typecheck
```

```bash
make test
```

## Code layout

```
backend/app/
  api/v1/          HTTP routes (thin: validation, permissions, audit)
  services/        business logic: ingest + lifecycle, query filters, reporting, scoping
  services/parsers scanner formats (implement ScanParser to add one)
  models/          SQLAlchemy models
  schemas/         Pydantic request/response models
frontend/src/
  routes/          TanStack Router file routes (thin)
  features/        pages and their components, by domain
  components/      shared UI (primitives, severity components)
  lib/             API client, types, hooks, utilities
```

## Conventions

- **Backend:** every endpoint declares its permission with `require(Perm.X)`. Any query that returns assets or findings must go through `base_query()` / `scope_assets()` so network scoping applies. Write actions call `audit()`.
- **Filters** live in one place (`services/findings_query.py`) and are shared by the explorer, exports, dashboard, and reports. Add new filters there.
- **Schema changes** need an Alembic migration: `cd backend && .venv/bin/alembic revision --autogenerate -m "describe change"`.
- **Frontend:** severity colours are reserved for risk and the brand colour for actions; never use one for the other. Check new UI in light and dark mode and at mobile width.
- Keep pull requests focused, and add or update tests for behaviour changes.

## Commit messages

Use the imperative mood with a short summary line, e.g. `Add SLA policy model and due-date calculation`.
