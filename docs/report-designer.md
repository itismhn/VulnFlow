# Report designer

Create reusable report templates in the built-in designer. Existing templates continue to use their saved sections and branding.

## Built-in scenario templates

The original **Executive Summary**, **Technical Detailed**, and **Network / Range Report** remain available. Eight additional presets support security team workflows:

| Template | Default scope and purpose |
|---|---|
| Critical & High Remediation Plan | Active critical/high findings, grouped by vulnerability with solutions and affected hosts. |
| Public Exploit Exposure Brief | Active findings flagged with public exploit metadata; this does not imply confirmed exploitation or internet exposure. |
| Overdue Remediation Escalation | Active findings past their recorded due date; findings without due dates are excluded. |
| Aging Vulnerability Backlog | Active findings first seen more than 90 days ago; first-seen age includes time before reopening. |
| Asset Owner Remediation Handoff | Active findings grouped by host. Select the recipient's assets, network, or assignee before generating. |
| Reopened Findings Review | Currently reopened findings with investigation prompts. |
| Accepted Risk Review Register | Currently risk-accepted findings with a checklist for reviewing the supporting exceptions. Approval and expiry records are reviewed separately in the risk workflow. |
| Security Team Operations Review | Current exposure, trend and aging charts, rolling activity metrics, and a recurring meeting agenda. |

Each preset includes scenario-specific text, section ordering, and an accent colour. Duplicate a built-in template to save your own branding and wording, or use **Customize** when generating a single report. Default filters can be changed in **Scope**; generating from the findings explorer uses that explorer's scope instead of the template defaults.

New built-ins are registered when the API starts. Restart an existing API to make them available; no migration is needed. Registration preserves existing templates, including user templates whose names match a new preset.

Status-specific registers omit open-finding KPIs and charts because those metrics measure active findings independently of the selected status. The operations review is live, not a calendar-month snapshot: new/fixed metrics use the last 30 days and MTTR uses fixes from the last 180 days. HTML/PDF reproduce the preset's narrative and layout; CSV/XLSX export scoped data using the existing data-export layout. For owners and due dates, use the findings explorer or full CSV/XLSX export.

## Create manually

Select **Reports → New template**. The editor has four panels:

- **Opening pages**: up to ten pages before the report body. Upload a PNG/JPEG background, choose fill/contain and an optional dark overlay, and add text or image blocks. Drag a block to position it; use the inspector for exact position, width, text size, colour, bold, and alignment. Page order is adjustable.
- **Branding**: company name, classification, accent colour, header, footer, and uploaded logo. On a custom opening page, use **Add logo to page** to position it yourself. The standard cover includes the logo automatically.
- **Content**: introduction, replacement summary and recommendations, top-list size, finding grouping, default scope, section headings and order, and custom text sections. Every section can start on a new page.
- **Layout**: A4/Letter, portrait/landscape, body font and size, margins, page numbers, and cover visibility.

Use **Preview report** for an HTML proof with scoped live data and **PDF proof** to check actual pagination. Opening-page blocks have a fixed position, so very long text should be split across blocks/pages or put in a flowing custom section. The PDF proof is authoritative for print layout.

Supported manual text fields:

| Field | Value |
|---|---|
| `{{ report.title }}` | Report title |
| `{{ report.date }}` | Generation date in UTC |
| `{{ report.author }}` | Generating user's name |
| `{{ report.scope }}` | Effective report filter description |
| `{{ company.name }}` | Company name |
| `{{ company.classification }}` | Classification banner |
| `{{ metrics.total_open }}` | Total open findings |
| `{{ metrics.assets }}` | Assets in scope |

Manual templates output PDF/HTML. Excel and CSV remain data exports; they do not reproduce document backgrounds or page layouts.

## Generate one report

Choose a template and select **Generate report**. **Customize** edits content and design for that one report; applying those changes does not change the saved template. The selected template configuration and filters are saved with the job when it is queued. Later template edits/deletion do not change the job's settings. Report data is read when the worker generates the file; it is not a historical database snapshot.

Previews and generated reports use the requesting user's network scope. Template management and asset upload use the existing `templates:manage` permission. Uploads accept PNG/JPEG images up to 20 MB and 24 megapixels. Text supports the report fields listed above.

Uploaded files are immutable content-addressed assets under `storage/report-assets/`. Reports embed their images so downloaded HTML files are portable. Assets are included in backup/restore. Unreferenced assets are retained to keep queued jobs and saved settings valid.

## Upgrade and verification

Install backend dependencies from the updated lockfile, run `alembic upgrade head` (migration `0007` adds template snapshots), rebuild the frontend, and restart API/worker. Docker startup runs migrations as before.

Checks:

```bash
make typecheck
make lint
make test
cd frontend && pnpm build
```

On macOS, WeasyPrint may need `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` when launching the API, worker, or tests after installing Pango.

The development demonstration uses a separate PostgreSQL cluster on port 55432 and database `vulnflow_reports_demo`, with fictional scans. Its artifacts live under ignored `output/reports/`.

### Reporting verification, 23 November 2026

- Full backend suite: 102 passing tests, including 26 designer tests. Frontend production build, lint, and both type checks passed.
- The first container scan exposed fixable dependencies. Updated Pillow to 13.0.0, Brotli to 1.2.1, and dnspython to 2.9.2; explicitly install the current distribution zlib package when building the container. Re-ran the full suite and regenerated the sample with these dependencies.
- Exercised PDF, portable HTML, XLSX, and CSV generation; template create/edit/duplicate-name/delete; job snapshots; report-specific overrides; scoped previews and exports; report history access; image uploads and backup/restore.
- Checked A4/Letter in both orientations, hidden covers, section page breaks, no matching findings, detail limits, invalid settings, and long report titles. A rendering regression verifies charts stay inside the printable area at maximum margins.
- Generated a five-page Northstar executive assessment from fictional data, saved its reusable template in the demo, and visually inspected every PDF page. Local copies: `output/reports/northstar-assessment.pdf` and corresponding HTML/XLSX/CSV.
- Interactive browser testing could not run because a saved browser permission denies the local origin. Clicks, dragging, file-picker interaction, and responsive editor behavior remain unverified in a browser.

HTML/PDF detail output remains limited to 400 groups and 150 instances per group; reports disclose omitted rows. Use XLSX/CSV for the complete finding data.
