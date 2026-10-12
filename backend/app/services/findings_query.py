"""Single place that turns `FindingFilters` into SQL.

The findings explorer, CSV/XLSX export, dashboards, and report generator all use
this, so a filter behaves identically everywhere.
"""

import ipaddress
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, String, and_, any_, case, cast, exists, func, literal, or_, select
from sqlalchemy.dialects.postgresql import CIDR
from sqlalchemy.orm import aliased

from app.models import Asset, Finding, FindingOccurrence, Network, Plugin, User
from app.models.enums import ACTIVE_STATUSES
from app.schemas.finding import FindingFilters
from app.services.scoping import scope_assets

SEVERITY_WEIGHT = case(
    (Finding.severity == 4, 10.0),
    (Finding.severity == 3, 5.0),
    (Finding.severity == 2, 2.0),
    (Finding.severity == 1, 0.5),
    else_=0.0,
)


def base_query(user: User, *columns: Any) -> Select[Any]:
    stmt = select(*columns) if columns else select(Finding)
    stmt = (
        stmt.select_from(Finding)
        .join(Asset, Asset.id == Finding.asset_id)
        .join(Plugin, Plugin.id == Finding.plugin_id)
    )
    return scope_assets(stmt, user)


def apply_filters(stmt: Select[Any], f: FindingFilters) -> Select[Any]:
    conds: list[Any] = []

    statuses = f.status or list(ACTIVE_STATUSES)
    conds.append(Finding.status.in_([s.value for s in statuses]))

    if f.severity:
        conds.append(Finding.severity.in_(f.severity))
    elif not f.include_info:
        conds.append(Finding.severity > 0)

    if f.q:
        q = f.q.strip()
        like = f"%{q}%"
        text_match = or_(
            Plugin.name.ilike(like),
            Asset.hostname.ilike(like),
            Asset.fqdn.ilike(like),
            func.host(Asset.ip).like(f"{q}%"),
            func.array_to_string(Plugin.cves, " ").ilike(like),
        )
        conds.append(or_(text_match, Plugin.id == int(q)) if q.isdigit() else text_match)

    if f.ip:
        try:
            ip_range = ipaddress.ip_network(f.ip.strip(), strict=False)
            conds.append(Asset.ip.op("<<=")(cast(str(ip_range), CIDR)))
        except ValueError:
            conds.append(func.host(Asset.ip) == f.ip.strip())

    # Aliased networks: the outer query may itself join Network (group by network/zone)
    if f.network_id:
        in_net = aliased(Network)
        conds.append(
            exists(select(1).where(and_(in_net.id.in_(f.network_id), Asset.ip.op("<<=")(in_net.cidr))))
        )
    if f.zone:
        zone_net = aliased(Network)
        conds.append(Asset.network_id.in_(select(zone_net.id).where(zone_net.zone.in_(f.zone))))
    if f.asset_id:
        conds.append(Finding.asset_id == f.asset_id)
    if f.plugin_id:
        conds.append(Finding.plugin_id.in_(f.plugin_id))
    if f.family:
        conds.append(Plugin.family == f.family)
    if f.cve:
        conds.append(literal(f.cve.strip().upper()) == any_(Plugin.cves))
    if f.port is not None:
        conds.append(Finding.port == f.port)
    if f.exploitable is not None:
        conds.append(Plugin.exploit_available.is_(f.exploitable))
    if f.min_cvss is not None:
        conds.append(func.coalesce(Plugin.cvss3_base, Plugin.cvss2_base) >= f.min_cvss)
    if f.min_vpr is not None:
        conds.append(Plugin.vpr_score >= f.min_vpr)
    if f.scan_id:
        conds.append(
            exists(
                select(1).where(
                    and_(
                        FindingOccurrence.finding_id == Finding.id,
                        FindingOccurrence.scan_id == f.scan_id,
                    )
                )
            )
        )
    if f.assignee_id:
        conds.append(Finding.assignee_id == f.assignee_id)
    if f.overdue:
        conds.append(and_(Finding.due_date.is_not(None), Finding.due_date < date.today()))
    if f.older_than_days:
        conds.append(Finding.first_seen < datetime.now(UTC) - timedelta(days=f.older_than_days))

    return stmt.where(*conds)


SORTS: dict[str, Any] = {
    "severity": Finding.severity,
    "last_seen": Finding.last_seen,
    "first_seen": Finding.first_seen,
    "ip": Asset.ip,
    "plugin": Plugin.name,
    "port": Finding.port,
    "status": Finding.status,
    "cvss": func.coalesce(Plugin.cvss3_base, Plugin.cvss2_base),
    "vpr": Plugin.vpr_score,
    "due_date": Finding.due_date,
}


def apply_sort(stmt: Select[Any], sort: str | None) -> Select[Any]:
    sort = sort or "-severity"
    desc = sort.startswith("-")
    col = SORTS.get(sort.lstrip("-"), Finding.severity)
    primary = col.desc().nulls_last() if desc else col.asc().nulls_last()
    return stmt.order_by(primary, Asset.ip, Finding.id)


def severity_counts_expr() -> list[Any]:
    return [
        func.count().filter(Finding.severity == sev).label(name)
        for sev, name in ((4, "critical"), (3, "high"), (2, "medium"), (1, "low"), (0, "info"))
    ]


def ip_text(col: Any = Asset.ip) -> Any:
    return cast(func.host(col), String)
