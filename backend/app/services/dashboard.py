from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Date, and_, cast, func, literal_column, select, text
from sqlalchemy.orm import Session

from app.models import Asset, Finding, Network, Plugin, Scan, User
from app.models.enums import ACTIVE_STATUSES, FindingStatus, ScanStatus
from app.schemas.common import SeverityCounts
from app.schemas.finding import FindingFilters
from app.services.findings_query import SEVERITY_WEIGHT, apply_filters, base_query


class TrendPoint(BaseModel):
    date: date
    critical: int
    high: int
    medium: int
    low: int


class TopHost(BaseModel):
    asset_id: int
    ip: str
    hostname: str
    risk_score: float
    critical: int
    high: int


class TopVuln(BaseModel):
    plugin_id: int
    name: str
    severity: int
    hosts: int
    exploit_available: bool


class Bucket(BaseModel):
    label: str
    critical: int
    high: int
    medium: int
    low: int


class Kpis(BaseModel):
    open: SeverityCounts
    exploitable: int
    overdue: int
    assets: int
    assets_with_critical: int
    scans: int
    last_scan_at: datetime | None
    new_30d: int
    fixed_30d: int
    mttr_days: dict[str, float | None]


class Dashboard(BaseModel):
    kpis: Kpis
    trend: list[TrendPoint]
    top_hosts: list[TopHost]
    top_vulns: list[TopVuln]
    by_zone: list[Bucket]
    age: list[Bucket]
    status: dict[str, int]


def _sev_cols() -> list[Any]:
    return [
        func.count().filter(Finding.severity == s).label(n)
        for s, n in ((4, "critical"), (3, "high"), (2, "medium"), (1, "low"))
    ]


def build_dashboard(db: Session, user: User, filters: FindingFilters, trend_days: int = 180) -> Dashboard:
    now = datetime.now(UTC)
    active = filters.model_copy(update={"status": list(ACTIVE_STATUSES)})

    open_counts = db.execute(apply_filters(base_query(user, *_sev_cols()), active)).one()
    exploitable = db.scalar(
        apply_filters(base_query(user, func.count()), active.model_copy(update={"exploitable": True}))
    )
    overdue = db.scalar(
        apply_filters(base_query(user, func.count()), active.model_copy(update={"overdue": True}))
    )
    asset_stats = db.execute(
        apply_filters(
            base_query(
                user,
                func.count(func.distinct(Asset.id)),
                func.count(func.distinct(Asset.id)).filter(Finding.severity == 4),
            ),
            active.model_copy(update={"include_info": True}),
        )
    ).one()

    any_status = filters.model_copy(update={"status": list(FindingStatus)})
    new_30d = db.scalar(
        apply_filters(base_query(user, func.count()), any_status).where(
            Finding.first_seen >= now - timedelta(days=30)
        )
    )
    fixed = filters.model_copy(update={"status": [FindingStatus.FIXED]})
    fixed_30d = db.scalar(
        apply_filters(base_query(user, func.count()), fixed).where(
            Finding.fixed_at >= now - timedelta(days=30)
        )
    )
    mttr_rows = db.execute(
        apply_filters(
            base_query(
                user,
                Finding.severity,
                func.avg(func.extract("epoch", Finding.fixed_at - Finding.first_seen) / 86400),
            ),
            fixed,
        )
        .where(Finding.fixed_at >= now - timedelta(days=180))
        .group_by(Finding.severity)
    ).all()
    mttr: dict[str, float | None] = {"critical": None, "high": None, "medium": None, "low": None}
    names = {4: "critical", 3: "high", 2: "medium", 1: "low"}
    for sev, days in mttr_rows:
        if sev in names and days is not None:
            mttr[names[sev]] = round(float(days), 1)

    last_scan = db.execute(
        select(func.count(), func.max(Scan.started_at)).where(
            Scan.status == ScanStatus.DONE, Scan.archived.is_(False)
        )
    ).one()

    kpis = Kpis(
        open=SeverityCounts(
            critical=open_counts.critical,
            high=open_counts.high,
            medium=open_counts.medium,
            low=open_counts.low,
        ),
        exploitable=exploitable or 0,
        overdue=overdue or 0,
        assets=asset_stats[0],
        assets_with_critical=asset_stats[1],
        scans=last_scan[0],
        last_scan_at=last_scan[1],
        new_30d=new_30d or 0,
        fixed_30d=fixed_30d or 0,
        mttr_days=mttr,
    )

    # Trend: open findings at each weekly point, reconstructed from first_seen/fixed_at
    day = (
        func.generate_series(
            cast(now - timedelta(days=trend_days), Date), cast(now, Date), text("interval '7 days'")
        )
        .table_valued("d")
        .render_derived()
    )
    d = cast(day.c.d, Date)
    not_fp = filters.model_copy(
        update={"status": [s for s in FindingStatus if s != FindingStatus.FALSE_POSITIVE]}
    )
    trend_stmt = (
        apply_filters(base_query(user, d.label("day"), *_sev_cols()), not_fp)
        .join(
            day,
            and_(
                cast(Finding.first_seen, Date) <= d,
                (Finding.fixed_at.is_(None)) | (cast(Finding.fixed_at, Date) > d),
            ),
        )
        .group_by(d)
        .order_by(d)
    )
    trend_map = {r.day: r for r in db.execute(trend_stmt)}
    trend = []
    point = (now - timedelta(days=trend_days)).date()
    while point <= now.date():
        r = trend_map.get(point)
        trend.append(
            TrendPoint(
                date=point,
                critical=r.critical if r else 0,
                high=r.high if r else 0,
                medium=r.medium if r else 0,
                low=r.low if r else 0,
            )
        )
        point += timedelta(days=7)

    eff_crit = func.coalesce(Asset.criticality, Network.criticality, 3)
    risk = (func.sum(SEVERITY_WEIGHT) * eff_crit / 3.0).label("risk")
    top_hosts = [
        TopHost(
            asset_id=r.id,
            ip=str(r.ip),
            hostname=r.hostname or r.fqdn,
            risk_score=round(float(r.risk), 1),
            critical=r.critical,
            high=r.high,
        )
        for r in db.execute(
            apply_filters(
                base_query(
                    user, Asset.id, Asset.ip, Asset.hostname, Asset.fqdn, risk, *_sev_cols()
                ).outerjoin(Network, Network.id == Asset.network_id),
                active,
            )
            .group_by(Asset.id, Network.id)
            .order_by(literal_column("risk").desc())
            .limit(10)
        )
    ]

    top_vulns = [
        TopVuln(
            plugin_id=r.id,
            name=r.name,
            severity=r.severity,
            hosts=r.hosts,
            exploit_available=r.exploit_available,
        )
        for r in db.execute(
            apply_filters(
                base_query(
                    user,
                    Plugin.id,
                    Plugin.name,
                    Plugin.exploit_available,
                    func.max(Finding.severity).label("severity"),
                    func.count(func.distinct(Finding.asset_id)).label("hosts"),
                ),
                active,
            )
            .group_by(Plugin.id)
            .order_by(literal_column("severity").desc(), literal_column("hosts").desc())
            .limit(10)
        )
    ]

    zone = func.coalesce(func.nullif(Network.zone, ""), "Unassigned")
    by_zone = [
        Bucket(label=r.zone, critical=r.critical, high=r.high, medium=r.medium, low=r.low)
        for r in db.execute(
            apply_filters(
                base_query(user, zone.label("zone"), *_sev_cols()).outerjoin(
                    Network, Network.id == Asset.network_id
                ),
                active,
            )
            .group_by(zone)
            .order_by(func.count().filter(Finding.severity == 4).desc(), func.count().desc())
        )
    ]

    age_days = func.extract("epoch", func.now() - Finding.first_seen) / 86400
    bucket = func.width_bucket(age_days, [30, 60, 90, 180])
    labels = ["0-30 days", "31-60 days", "61-90 days", "91-180 days", "180+ days"]
    age_rows = {
        r.b: r
        for r in db.execute(
            apply_filters(base_query(user, bucket.label("b"), *_sev_cols()), active).group_by(bucket)
        )
    }
    age = [
        Bucket(
            label=label,
            critical=age_rows[i].critical if i in age_rows else 0,
            high=age_rows[i].high if i in age_rows else 0,
            medium=age_rows[i].medium if i in age_rows else 0,
            low=age_rows[i].low if i in age_rows else 0,
        )
        for i, label in enumerate(labels)
    ]

    status_counts: dict[str, int] = dict(
        db.execute(
            apply_filters(base_query(user, Finding.status, func.count()), any_status).group_by(Finding.status)
        ).all()
    )

    return Dashboard(
        kpis=kpis,
        trend=trend,
        top_hosts=top_hosts,
        top_vulns=top_vulns,
        by_zone=by_zone,
        age=age,
        status={s.value: status_counts.get(s.value, 0) for s in FindingStatus},
    )
