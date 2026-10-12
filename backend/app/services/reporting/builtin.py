from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ReportTemplate
from app.schemas.report import TemplateConfig

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
]


def ensure_builtin_templates(db: Session) -> None:
    existing = set(db.scalars(select(ReportTemplate.name).where(ReportTemplate.builtin.is_(True))))
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
