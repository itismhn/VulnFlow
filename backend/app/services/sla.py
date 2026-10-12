"""SLA due dates: derived from the finding's severity, its network zone, and first detection."""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import SlaPolicy

# Zone policy wins over the default (zone IS NULL) policy; disabled policies are ignored.
# Only touches findings whose due date is policy-driven, so manual dates survive.
_APPLY = """
WITH target AS (
    SELECT f.id,
           ((f.first_seen AT TIME ZONE 'UTC')::date + CASE f.severity
                WHEN 4 THEN p.critical_days WHEN 3 THEN p.high_days
                WHEN 2 THEN p.medium_days WHEN 1 THEN p.low_days END) AS due
    FROM findings f
    JOIN assets a ON a.id = f.asset_id
    LEFT JOIN networks n ON n.id = a.network_id
    LEFT JOIN LATERAL (
        SELECT * FROM sla_policies sp
        WHERE sp.enabled AND (sp.zone IS NULL OR sp.zone = n.zone)
        ORDER BY sp.zone IS NULL
        LIMIT 1
    ) p ON true
    WHERE COALESCE(f.due_source, 'sla') = 'sla' {scope}
)
UPDATE findings f
SET due_date = target.due,
    due_source = CASE WHEN target.due IS NULL THEN NULL ELSE 'sla' END
FROM target
WHERE f.id = target.id
  AND (f.due_date IS DISTINCT FROM target.due OR f.due_source IS DISTINCT FROM
       CASE WHEN target.due IS NULL THEN NULL ELSE 'sla' END)
"""


def apply_sla(db: Session, asset_ids: list[int] | None = None) -> int:
    """(Re)compute policy-driven due dates. Returns the number of findings changed."""
    if asset_ids is not None and not asset_ids:
        return 0
    if asset_ids is None:
        result = db.execute(text(_APPLY.format(scope="")))
    else:
        result = db.execute(text(_APPLY.format(scope="AND f.asset_id = ANY(:ids)")), {"ids": asset_ids})
    return result.rowcount or 0  # type: ignore[attr-defined]


def ensure_default_policy(db: Session) -> None:
    """Create the default (all zones) policy on first start."""
    if db.scalar(select(SlaPolicy.id).where(SlaPolicy.zone.is_(None))) is None:
        db.add(SlaPolicy(zone=None))
        db.commit()
