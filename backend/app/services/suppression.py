"""Suppression rules: mark a plugin as a false positive across hosts."""

from typing import Any

from sqlalchemy import and_, cast, insert, select, update
from sqlalchemy.dialects.postgresql import CIDR
from sqlalchemy.orm import Session

from app.models import Asset, Finding, FindingEvent, SuppressionRule
from app.models.enums import FindingEventKind, FindingStatus


def _matches(rule: SuppressionRule) -> list[Any]:
    conds: list[Any] = [Finding.plugin_id == rule.plugin_id]
    if rule.port is not None:
        conds.append(Finding.port == rule.port)
    if rule.cidr:
        conds.append(
            Finding.asset_id.in_(select(Asset.id).where(Asset.ip.op("<<=")(cast(str(rule.cidr), CIDR))))
        )
    return conds


def apply_rule(
    db: Session, rule: SuppressionRule, asset_ids: list[int] | None = None, actor_id: int | None = None
) -> int:
    """Mark matching findings (not already suppressed or accepted) as false positives."""
    conds = [
        *_matches(rule),
        Finding.status.not_in([FindingStatus.FALSE_POSITIVE, FindingStatus.RISK_ACCEPTED]),
    ]
    if asset_ids is not None:
        if not asset_ids:
            return 0
        conds.append(Finding.asset_id.in_(asset_ids))
    rows = db.execute(select(Finding.id, Finding.status).where(and_(*conds))).all()
    if not rows:
        return 0
    note = f"Suppressed by rule #{rule.id}: {rule.reason}"
    db.execute(
        insert(FindingEvent).values(
            [
                {
                    "finding_id": fid,
                    "kind": FindingEventKind.STATUS,
                    "from_status": old,
                    "to_status": FindingStatus.FALSE_POSITIVE,
                    "note": note,
                    "actor_id": actor_id,
                    "scan_id": None,
                }
                for fid, old in rows
            ]
        )
    )
    db.execute(
        update(Finding)
        .where(Finding.id.in_([r[0] for r in rows]))
        .values(status=FindingStatus.FALSE_POSITIVE, fixed_at=None)
        .execution_options(synchronize_session=False)
    )
    return len(rows)


def release_rule(db: Session, rule: SuppressionRule, actor_id: int | None = None) -> int:
    """Undo a rule: findings it suppressed (and nobody changed since) go back to open."""
    marker = f"Suppressed by rule #{rule.id}:%"
    last_event = (
        select(FindingEvent.note)
        .where(FindingEvent.finding_id == Finding.id, FindingEvent.kind == FindingEventKind.STATUS)
        .order_by(FindingEvent.created_at.desc(), FindingEvent.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    ids = list(
        db.scalars(
            select(Finding.id).where(
                *_matches(rule),
                Finding.status == FindingStatus.FALSE_POSITIVE,
                last_event.like(marker),
            )
        )
    )
    if not ids:
        return 0
    db.execute(
        insert(FindingEvent).values(
            [
                {
                    "finding_id": fid,
                    "kind": FindingEventKind.STATUS,
                    "from_status": FindingStatus.FALSE_POSITIVE,
                    "to_status": FindingStatus.OPEN,
                    "note": f"Suppression rule #{rule.id} removed",
                    "actor_id": actor_id,
                    "scan_id": None,
                }
                for fid in ids
            ]
        )
    )
    db.execute(
        update(Finding)
        .where(Finding.id.in_(ids))
        .values(status=FindingStatus.OPEN)
        .execution_options(synchronize_session=False)
    )
    return len(ids)


def apply_all(db: Session, asset_ids: list[int]) -> int:
    rules = db.scalars(select(SuppressionRule).where(SuppressionRule.enabled.is_(True))).unique()
    return sum(apply_rule(db, r, asset_ids) for r in rules)
