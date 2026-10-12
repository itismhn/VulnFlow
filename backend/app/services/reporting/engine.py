"""Render report jobs to PDF / HTML / XLSX / CSV.

Reports are generated as the user who requested them, so network scoping
applies to report contents exactly like it does in the UI.
"""

import csv
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.storage import report_file_path
from app.models import Asset, Finding, Network, Plugin, ReportJob, User
from app.models.enums import ReportFormat
from app.schemas.finding import FindingFilters
from app.schemas.report import TemplateConfig
from app.services.dashboard import Dashboard, build_dashboard
from app.services.exporting import SEVERITY_LABELS, finding_rows
from app.services.findings_query import apply_filters, base_query
from app.services.reporting import charts
from app.services.reporting.xlsx import safe_cell, sheets_to_xlsx

TEMPLATE_DIR = Path(__file__).parent / "templates"

DEFAULT_SECTIONS = {
    "executive": ["summary", "kpis", "charts", "top_vulns", "top_hosts", "zones", "recommendations"],
    "technical": ["summary", "kpis", "details"],
    "network": ["summary", "networks"],
}

MAX_DETAIL_GROUPS = 400
MAX_INSTANCES_PER_GROUP = 150

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "j2"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
_env.filters["sev_label"] = lambda s: SEVERITY_LABELS[int(s)]
_env.filters["sev_class"] = lambda s: SEVERITY_LABELS[int(s)].lower()
_env.filters["dt"] = lambda d: d.strftime("%Y-%m-%d") if d else "—"


def describe_filters(f: FindingFilters, db: Session) -> list[str]:
    out = []
    if f.severity:
        out.append("Severity: " + ", ".join(SEVERITY_LABELS[s] for s in sorted(f.severity, reverse=True)))
    if f.status:
        out.append("Status: " + ", ".join(s.replace("_", " ") for s in f.status))
    if f.ip:
        out.append(f"IP / range: {f.ip}")
    if f.network_id:
        names = db.scalars(select(Network.name).where(Network.id.in_(f.network_id)))
        out.append("Networks: " + ", ".join(names))
    if f.zone:
        out.append("Zones: " + ", ".join(f.zone))
    if f.scan_id:
        out.append(f"Scan #{f.scan_id}")
    if f.exploitable:
        out.append("Exploitable only")
    if f.cve:
        out.append(f"CVE: {f.cve}")
    if f.q:
        out.append(f"Search: {f.q}")
    return out or ["All active findings"]


def _detail_groups(
    db: Session, user: User, filters: FindingFilters, group_by: str
) -> tuple[list[dict[str, Any]], bool]:
    """Findings grouped by vulnerability (or host) for the technical report."""
    stmt = apply_filters(base_query(user), filters)
    if group_by == "host":
        order = [Asset.ip, Finding.severity.desc(), Plugin.name]
    else:
        order = [Finding.severity.desc(), Plugin.id, Asset.ip, Finding.port]
    groups: dict[Any, dict[str, Any]] = {}
    truncated = False
    for f in db.scalars(stmt.order_by(*order).execution_options(yield_per=2000)):
        key = f.asset_id if group_by == "host" else f.plugin_id
        group = groups.get(key)
        if group is None:
            if len(groups) >= MAX_DETAIL_GROUPS:
                truncated = True
                break
            group = groups[key] = {
                "plugin": f.plugin,
                "asset": f.asset,
                "severity": f.severity,
                "instances": [],
                "count": 0,
            }
        group["count"] += 1
        group["severity"] = max(group["severity"], f.severity)
        if len(group["instances"]) < MAX_INSTANCES_PER_GROUP:
            group["instances"].append(f)
    result = list(groups.values())
    if group_by != "host":
        result.sort(key=lambda g: (-g["severity"], -g["count"]))
    return result, truncated


def _network_sections(db: Session, user: User, filters: FindingFilters, top_n: int) -> list[dict[str, Any]]:
    nets = list(db.scalars(select(Network).order_by(Network.criticality.desc(), Network.cidr)))
    if filters.network_id:
        nets = [n for n in nets if n.id in filters.network_id]
    sections = []
    for net in nets:
        scoped = filters.model_copy(update={"network_id": [net.id]})
        dash = build_dashboard(db, user, scoped, trend_days=28)
        if not dash.kpis.assets and not sum(dash.kpis.open.model_dump().values()):
            continue
        sections.append(
            {
                "network": net,
                "dash": dash,
                "top_vulns": dash.top_vulns[:top_n],
                "top_hosts": dash.top_hosts[:top_n],
            }
        )
    return sections


def _charts(dash: Dashboard) -> dict[str, str]:
    open_ = dash.kpis.open
    return {
        "donut": charts.donut(
            {"critical": open_.critical, "high": open_.high, "medium": open_.medium, "low": open_.low}
        ),
        "trend": charts.trend_lines(
            [p.date.strftime("%d %b") for p in dash.trend],
            {
                "critical": [p.critical for p in dash.trend],
                "high": [p.high for p in dash.trend],
                "medium": [p.medium for p in dash.trend],
            },
        ),
        "zones": charts.stacked_bars(
            [z.label for z in dash.by_zone[:10]],
            {
                "critical": [z.critical for z in dash.by_zone[:10]],
                "high": [z.high for z in dash.by_zone[:10]],
                "medium": [z.medium for z in dash.by_zone[:10]],
                "low": [z.low for z in dash.by_zone[:10]],
            },
        ),
        "age": charts.stacked_bars(
            [a.label for a in dash.age],
            {
                "critical": [a.critical for a in dash.age],
                "high": [a.high for a in dash.age],
                "medium": [a.medium for a in dash.age],
                "low": [a.low for a in dash.age],
            },
        ),
    }


def build_context(db: Session, job: ReportJob, user: User) -> dict[str, Any]:
    template = job.template
    kind = template.kind if template else "technical"
    config = TemplateConfig.model_validate(template.config if template else {})
    filters = FindingFilters.model_validate(job.filters or config.filters.model_dump())
    sections = config.sections or DEFAULT_SECTIONS[kind]

    dash = build_dashboard(db, user, filters)
    ctx: dict[str, Any] = {
        "app_name": settings.app_name,
        "title": job.name,
        "kind": kind,
        "sections": sections,
        "branding": config.branding,
        "intro": config.intro,
        "generated_at": datetime.now(UTC),
        "author": user,
        "filters": describe_filters(filters, db),
        "dash": dash,
        "charts": _charts(dash),
        "top_n": config.top_n,
        "total_open": sum(dash.kpis.open.model_dump().values()),
    }
    if "details" in sections:
        ctx["groups"], ctx["truncated"] = _detail_groups(db, user, filters, config.group_by)
        ctx["group_by"] = config.group_by
    if "networks" in sections:
        ctx["networks"] = _network_sections(db, user, filters, config.top_n)
    return ctx


def render_html(ctx: dict[str, Any]) -> str:
    return _env.get_template("report.html.j2").render(**ctx)


def _xlsx(db: Session, user: User, ctx: dict[str, Any], filters: FindingFilters) -> bytes:
    dash: Dashboard = ctx["dash"]
    k = dash.kpis
    summary = [
        ["Metric", "Value"],
        ["Report", ctx["title"]],
        ["Generated", ctx["generated_at"].strftime("%Y-%m-%d %H:%M UTC")],
        ["Scope", "; ".join(ctx["filters"])],
        ["Open critical", k.open.critical],
        ["Open high", k.open.high],
        ["Open medium", k.open.medium],
        ["Open low", k.open.low],
        ["Exploitable", k.exploitable],
        ["Overdue", k.overdue],
        ["Assets", k.assets],
        ["Assets with critical", k.assets_with_critical],
        ["New (30 days)", k.new_30d],
        ["Fixed (30 days)", k.fixed_30d],
    ]
    vuln_rows: list[list[Any]] = [
        ["Plugin ID", "Name", "Family", "Severity", "Hosts", "Instances", "CVSS v3", "VPR", "Exploit", "CVEs"]
    ]
    stmt = (
        apply_filters(
            base_query(
                user,
                Plugin.id,
                Plugin.name,
                Plugin.family,
                func.max(Finding.severity),
                func.count(func.distinct(Finding.asset_id)),
                func.count(),
                Plugin.cvss3_base,
                Plugin.vpr_score,
                Plugin.exploit_available,
                Plugin.cves,
            ),
            filters,
        )
        .group_by(Plugin.id)
        .order_by(func.max(Finding.severity).desc(), func.count().desc())
    )
    for r in db.execute(stmt):
        vuln_rows.append(
            [
                r[0],
                r[1],
                r[2],
                SEVERITY_LABELS[r[3]],
                r[4],
                r[5],
                r[6] or "",
                r[7] or "",
                "yes" if r[8] else "no",
                " ".join(r[9]),
            ]
        )
    host_rows: list[list[Any]] = [["IP", "Hostname", "Risk score", "Critical", "High"]]
    host_rows += [[h.ip, h.hostname, h.risk_score, h.critical, h.high] for h in dash.top_hosts]
    return sheets_to_xlsx(
        {
            "Summary": summary,
            "Vulnerabilities": vuln_rows,
            "Findings": finding_rows(db, user, filters),
            "Top hosts": host_rows,
        }
    )


def render_report(db: Session, job: ReportJob) -> Path:
    user = job.created_by
    if user is None:
        raise RuntimeError("Report owner no longer exists")
    template = job.template
    config = TemplateConfig.model_validate(template.config if template else {})
    filters = FindingFilters.model_validate(job.filters or config.filters.model_dump())

    if job.format == ReportFormat.CSV:
        buf = io.StringIO()
        writer = csv.writer(buf)
        for row in finding_rows(db, user, filters):
            writer.writerow([safe_cell(v) for v in row])
        data = buf.getvalue().encode("utf-8-sig")
    else:
        ctx = build_context(db, job, user)
        if job.format == ReportFormat.XLSX:
            data = _xlsx(db, user, ctx, filters)
        else:
            html = render_html(ctx)
            if job.format == ReportFormat.HTML:
                data = html.encode()
            else:
                try:
                    from weasyprint import HTML  # heavy import, only when needed
                except OSError as exc:
                    raise RuntimeError(
                        "PDF output needs the Pango system library. It is included in the Docker image; "
                        "on macOS run `brew install pango`, on Debian/Ubuntu `apt install libpango-1.0-0 "
                        "libpangoft2-1.0-0`. HTML, Excel and CSV formats work without it."
                    ) from exc

                data = HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf()

    path = report_file_path(job.id, job.format)
    path.write_bytes(data)
    job.file_path = str(path)
    job.size_bytes = len(data)
    return path
