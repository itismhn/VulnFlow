from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ReportTemplate
from app.models.enums import FindingStatus
from app.schemas.finding import FindingFilters
from app.schemas.report import Branding, CustomSection, TemplateConfig

BUILTIN_TEMPLATES = [
    {
        "name": "Executive Summary",
        "kind": "executive",
        "description": "KPIs, risk trend, top vulnerabilities and assets, exposure by zone, and recommendations for management.",
        "config": TemplateConfig(
            sections=["summary", "kpis", "charts", "top_vulns", "top_hosts", "zones", "recommendations"]
        ),
    },
    {
        "name": "Technical Detailed",
        "kind": "technical",
        "description": "Every vulnerability with description, solution, and affected hosts, for remediation teams.",
        "config": TemplateConfig(sections=["summary", "kpis", "details"], group_by="plugin"),
    },
    {
        "name": "Network / Range Report",
        "kind": "network",
        "description": "One section per IP range with severity totals, top vulnerabilities, and riskiest hosts.",
        "config": TemplateConfig(sections=["summary", "networks"]),
    },
    {
        "name": "Critical & High Remediation Plan",
        "kind": "technical",
        "description": "Critical and high active findings, grouped by vulnerability for coordinated patching.",
        "config": TemplateConfig(
            sections=["summary", "kpis", "top_vulns", "details", "recommendations"],
            filters=FindingFilters(severity=[4, 3]),
            branding=Branding(primary_color="#b91c1c"),
            intro="Remediation planning for critical and high findings in {{ report.scope }}.",
            section_titles={"details": "Remediation work packages"},
            page_breaks=["details"],
            recommendations_text=(
                "Assign an accountable owner and target date to each work package. Review the "
                "scanner-provided solution against the affected product and version, schedule the "
                "change, and record rollback steps. Prioritize public-exploit findings and critical "
                "assets. Validate each change with a follow-up scan before closing the finding."
            ),
        ),
    },
    {
        "name": "Public Exploit Exposure Brief",
        "kind": "technical",
        "description": "Active findings flagged with a public exploit, with affected hosts and remediation guidance.",
        "config": TemplateConfig(
            sections=["summary", "kpis", "top_hosts", "details", "recommendations"],
            filters=FindingFilters(exploitable=True),
            branding=Branding(primary_color="#c2410c"),
            intro=(
                "Public-exploit availability is taken from imported scanner metadata. It does not "
                "establish exploitation in this environment or prove that a host is internet-facing."
            ),
            section_titles={"details": "Findings with public exploit metadata"},
            recommendations_text=(
                "Validate affected versions and reachability, then agree remediation priorities with "
                "asset owners. Where immediate patching is unavailable, document compensating "
                "controls and a review date. Coordinate detection review with the SOC and verify "
                "remediation through a follow-up scan."
            ),
        ),
    },
    {
        "name": "Overdue Remediation Escalation",
        "kind": "technical",
        "description": "Active findings past their recorded due date, for remediation owners and team leads.",
        "config": TemplateConfig(
            sections=["summary", "top_vulns", "details", "custom_escalation"],
            filters=FindingFilters(overdue=True),
            branding=Branding(primary_color="#9f1239"),
            intro=(
                "Includes active findings whose recorded due date has passed. Findings without a "
                "due date are excluded; this is not a complete assessment of policy compliance."
            ),
            section_titles={"details": "Overdue vulnerability work packages"},
            custom_sections=[
                CustomSection(
                    id="custom_escalation",
                    title="Escalation meeting checklist",
                    text=(
                        "For each overdue finding, review the assigned owner and due date in the "
                        "findings explorer or full CSV/XLSX export. Record the blocker, escalation "
                        "contact, revised delivery commitment, and validation scan plan. Route any "
                        "proposed exception through the risk-acceptance workflow."
                    ),
                )
            ],
        ),
    },
    {
        "name": "Aging Vulnerability Backlog",
        "kind": "technical",
        "description": "Active findings first seen more than 90 days ago, for backlog reduction planning.",
        "config": TemplateConfig(
            sections=["summary", "kpis", "top_vulns", "top_hosts", "details", "recommendations"],
            filters=FindingFilters(older_than_days=90),
            branding=Branding(primary_color="#92400e"),
            intro=(
                "The backlog is selected by first-seen age greater than 90 days, including reopened "
                "findings. First-seen age does not measure continuous exposure or time overdue."
            ),
            section_titles={"details": "Long-standing findings"},
            recommendations_text=(
                "Group repeat issues into shared patch or configuration changes. Confirm that "
                "asset ownership and scan coverage are current, agree a backlog reduction plan, "
                "and record blockers and exceptions. Use rescans to validate completed changes."
            ),
        ),
    },
    {
        "name": "Asset Owner Remediation Handoff",
        "kind": "technical",
        "description": "Host-by-host active findings for infrastructure and application owners; narrow the scope before sharing.",
        "config": TemplateConfig(
            sections=["summary", "top_hosts", "details", "recommendations"],
            group_by="host",
            branding=Branding(primary_color="#0f766e"),
            intro=(
                "Use report scope to select the recipient's assets, network, or assignee before "
                "generation. Each host section lists its active vulnerabilities and services."
            ),
            section_titles={"details": "Host remediation checklist"},
            page_breaks=["details"],
            recommendations_text=(
                "Confirm ownership of each listed host. Review individual finding details for "
                "scanner evidence and the recommended solution, agree maintenance windows and "
                "target dates, and arrange a validation scan after changes."
            ),
        ),
    },
    {
        "name": "Reopened Findings Review",
        "kind": "technical",
        "description": "Findings currently marked reopened, for investigating recurring exposure after closure.",
        "config": TemplateConfig(
            sections=["summary", "details", "recommendations"],
            filters=FindingFilters(status=[FindingStatus.REOPENED]),
            branding=Branding(primary_color="#7c3aed"),
            summary_text=(
                "This register lists findings currently marked reopened in {{ report.scope }}. "
                "Review each finding's scan history and evidence to understand why it returned. "
                "A reopened status alone does not establish the cause."
            ),
            section_titles={"details": "Reopened finding register"},
            recommendations_text=(
                "Compare the previous closure with current scan evidence. Check for rolled-back "
                "patches, configuration drift, rebuilds, and changes in scan coverage. Record the "
                "confirmed cause and corrective action, then verify through a follow-up scan."
            ),
        ),
    },
    {
        "name": "Accepted Risk Review Register",
        "kind": "technical",
        "description": "Findings currently marked risk accepted, with a checklist for reviewing supporting exceptions.",
        "config": TemplateConfig(
            sections=["summary", "details", "custom_risk_review"],
            filters=FindingFilters(status=[FindingStatus.RISK_ACCEPTED]),
            branding=Branding(primary_color="#475569"),
            summary_text=(
                "This register lists findings currently marked risk accepted in {{ report.scope }}. "
                "It does not certify exception approval or include approval records, expiry dates, "
                "or compensating-control evidence. Review those records in the risk workflow."
            ),
            section_titles={"details": "Accepted finding register"},
            custom_sections=[
                CustomSection(
                    id="custom_risk_review",
                    title="Exception review checklist",
                    text=(
                        "For each finding, check the linked exception's approval status, accountable "
                        "risk owner, rationale, scope, expiry, and compensating controls. Confirm "
                        "that the business context remains valid and record the next review or "
                        "remediation decision in the risk workflow."
                    ),
                )
            ],
        ),
    },
    {
        "name": "Security Team Operations Review",
        "kind": "executive",
        "description": "Current exposure, rolling activity metrics, aging, and team review prompts for recurring security meetings.",
        "config": TemplateConfig(
            sections=["summary", "kpis", "charts", "top_vulns", "zones", "custom_review", "recommendations"],
            branding=Branding(primary_color="#0369a1"),
            intro=(
                "Operational review of the current selected scope. New and fixed counts use a "
                "rolling 30-day window; MTTR uses fixes from the last 180 days. This report is "
                "generated from live records and is not a calendar-month or historical snapshot."
            ),
            custom_sections=[
                CustomSection(
                    id="custom_review",
                    title="Team review agenda",
                    text=(
                        "Review newly detected exposure, public-exploit findings, overdue work, "
                        "and long-standing backlog. Confirm asset owners, remediation commitments, "
                        "scan coverage, and validation plans. Record decisions and follow-up "
                        "actions in the team's tracking system."
                    ),
                )
            ],
        ),
    },
]


def ensure_builtin_templates(db: Session) -> None:
    # Names are globally unique; preserve a user's template if its name matches a new preset.
    existing = set(db.scalars(select(ReportTemplate.name)))
    for t in BUILTIN_TEMPLATES:
        if t["name"] not in existing:
            db.add(
                ReportTemplate(
                    name=t["name"],
                    kind=t["kind"],
                    description=t["description"],
                    builtin=True,
                    config=t["config"].model_dump(mode="json"),  # type: ignore[attr-defined]
                )
            )
    db.commit()
