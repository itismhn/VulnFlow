"""Remediation metrics: SLA compliance, time to remediate, and weekly velocity."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Date, case, cast, func
from sqlalchemy.orm import Session, aliased

from app.models import Asset, Finding, Network, User
from app.models.enums import ACTIVE_STATUSES, FindingStatus
from app.schemas.finding import FindingFilters
from app.services.findings_query import apply_filters, base_query

SEV_NAMES = {4: "critical", 3: "high", 2: "medium", 1: "low"}


class SlaRow(BaseModel):
    key: str
    total: int
    met: int
    breached: int
    open_overdue: int
    compliance: float | None


class MttrRow(BaseModel):
    key: str
    fixed: int
    mttr_days: float | None


class VelocityPoint(BaseModel):
    week: date
    opened: int
    fixed: int


class Metrics(BaseModel):
    sla_overall: SlaRow
    sla_by_severity: list[SlaRow]
    sla_by_zone: list[SlaRow]
    mttr_by_severity: list[MttrRow]
    mttr_by_zone: list[MttrRow]
    mttr_by_owner: list[MttrRow]
    velocity: list[VelocityPoint]


def _days(expr: Any) -> Any:
    return func.extract("epoch", expr) / 86400.0


def build_metrics(db: Session, user: User, filters: FindingFilters, weeks: int = 12) -> Metrics:
    today = datetime.now(UTC).date()
    since = datetime.now(UTC) - timedelta(weeks=weeks)
    in_window = FindingFilters(
        **filters.model_dump(exclude={"status"}),
        status=[*ACTIVE_STATUSES, FindingStatus.FIXED],
    )
    zone_net = aliased(Network)
    zone = func.coalesce(zone_net.zone, "Unassigned")
    owner = func.coalesce(func.nullif(zone_net.owner, ""), "No owner")

    # SLA: fixed by the due date = met; fixed late = breached; still open past due = breached.
    fixed_date = cast(Finding.fixed_at, Date)
    is_fixed = Finding.status == FindingStatus.FIXED
    met = func.count().filter(is_fixed, fixed_date <= Finding.due_date)
    late = func.count().filter(is_fixed, fixed_date > Finding.due_date)
    open_overdue = func.count().filter(~is_fixed, Finding.due_date < today)
    open_ok = func.count().filter(~is_fixed, Finding.due_date >= today)
    sla_cols = [met.label("met"), late.label("late"), open_overdue.label("od"), open_ok.label("ok")]

    def sla_query(*keys: Any) -> Any:
        stmt = apply_filters(base_query(user, *keys, *sla_cols), in_window).where(
            Finding.due_date.is_not(None),
            # Ignore old history: only findings fixed recently or still open count
            case((is_fixed, Finding.fixed_at >= since), else_=True),
        )
        return stmt.outerjoin(zone_net, zone_net.id == Asset.network_id)

    def sla_row(key: str, m: int, lt: int, od: int, ok: int) -> SlaRow:
        decided = m + lt + od
        return SlaRow(
            key=key,
            total=m + lt + od + ok,
            met=m,
            breached=lt + od,
            open_overdue=od,
            compliance=round(100.0 * m / decided, 1) if decided else None,
        )

    overall = db.execute(sla_query()).one()
    by_sev = db.execute(
        sla_query(Finding.severity).group_by(Finding.severity).order_by(Finding.severity.desc())
    )
    by_zone = db.execute(sla_query(zone).group_by(zone).order_by(zone))

    # Time to remediate, for findings fixed within the window
    ttr = func.avg(_days(Finding.fixed_at - Finding.first_seen))
    fixed_filters = FindingFilters(**filters.model_dump(exclude={"status"}), status=[FindingStatus.FIXED])

    def mttr_query(key: Any) -> Any:
        return (
            apply_filters(base_query(user, key, func.count(), ttr), fixed_filters)
            .outerjoin(zone_net, zone_net.id == Asset.network_id)
            .where(Finding.fixed_at >= since)
            .group_by(key)
            .order_by(key)
        )

    def mttr_rows(rows: Any, label: Any = str) -> list[MttrRow]:
        return [
            MttrRow(key=label(k), fixed=n, mttr_days=round(float(d), 1) if d is not None else None)
            for k, n, d in rows
        ]

    # Weekly velocity: findings first detected vs fixed per week
    any_status = FindingFilters(
        **filters.model_dump(exclude={"status"}),
        status=[*FindingStatus],
    )
    opened_week = cast(func.date_trunc("week", Finding.first_seen), Date)
    fixed_week = cast(func.date_trunc("week", Finding.fixed_at), Date)
    opened: dict[date, int] = dict(
        db.execute(
            apply_filters(base_query(user, opened_week, func.count()), any_status)
            .where(Finding.first_seen >= since)
            .group_by(opened_week)
        ).all()
    )
    fixed: dict[date, int] = dict(
        db.execute(
            apply_filters(base_query(user, fixed_week, func.count()), fixed_filters)
            .where(Finding.fixed_at >= since)
            .group_by(fixed_week)
        ).all()
    )
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    velocity = [
        VelocityPoint(week=w, opened=opened.get(w, 0), fixed=fixed.get(w, 0))
        for w in (start + timedelta(weeks=i) for i in range(weeks))
    ]

    return Metrics(
        sla_overall=sla_row("overall", *overall),
        sla_by_severity=[sla_row(SEV_NAMES.get(k, str(k)), *rest) for k, *rest in by_sev],
        sla_by_zone=[sla_row(k, *rest) for k, *rest in by_zone],
        mttr_by_severity=mttr_rows(
            db.execute(mttr_query(Finding.severity).order_by(None).order_by(Finding.severity.desc())),
            lambda k: SEV_NAMES.get(k, str(k)),
        ),
        mttr_by_zone=mttr_rows(db.execute(mttr_query(zone))),
        mttr_by_owner=mttr_rows(db.execute(mttr_query(owner))),
        velocity=velocity,
    )
