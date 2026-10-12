from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.schemas.finding import FindingFilters
from app.services.findings_query import apply_filters, apply_sort, base_query

EXPORT_LIMIT = 250_000
SEVERITY_LABELS = ["Info", "Low", "Medium", "High", "Critical"]

FINDING_HEADER = [
    "IP",
    "Hostname",
    "Port",
    "Protocol",
    "Plugin ID",
    "Name",
    "Family",
    "Severity",
    "CVSS v3",
    "VPR",
    "CVEs",
    "Exploit available",
    "Status",
    "First seen",
    "Last seen",
    "Assignee",
    "Due date",
    "Solution",
]


def finding_rows(
    db: Session, user: User, filters: FindingFilters, sort: str | None = None, limit: int = EXPORT_LIMIT
) -> Iterator[list[Any]]:
    """Header row followed by one row per finding, streamed in chunks."""
    yield FINDING_HEADER
    stmt = apply_sort(apply_filters(base_query(user), filters), sort).limit(limit)
    for f in db.scalars(stmt.execution_options(yield_per=2000)):
        yield [
            str(f.asset.ip),
            f.asset.hostname or f.asset.fqdn,
            f.port,
            f.protocol,
            f.plugin_id,
            f.plugin.name,
            f.plugin.family,
            SEVERITY_LABELS[f.severity],
            f.plugin.cvss3_base or "",
            f.plugin.vpr_score or "",
            " ".join(f.plugin.cves),
            "yes" if f.plugin.exploit_available else "no",
            f.status,
            f.first_seen.date().isoformat(),
            f.last_seen.date().isoformat(),
            f.assignee.username if f.assignee else "",
            f.due_date.isoformat() if f.due_date else "",
            f.plugin.solution,
        ]
