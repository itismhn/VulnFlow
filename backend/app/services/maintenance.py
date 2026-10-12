from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.models import AuditLog, Notification
from app.services.app_settings import get_setting
from app.services.risk import expire_due
from app.services.sla import apply_sla

NOTIFICATION_DAYS = 90


def purge_audit(db: Session) -> int:
    days = int(get_setting(db, "audit_retention_days"))
    if days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=days)
    # The append-only trigger allows deletes only while this flag is set
    db.execute(text("SELECT set_config('rm.audit_purge', 'on', true)"))
    removed = db.execute(delete(AuditLog).where(AuditLog.created_at < cutoff)).rowcount or 0  # type: ignore[attr-defined]
    db.execute(text("SELECT set_config('rm.audit_purge', 'off', true)"))
    if removed:
        audit(db, "audit.purged", details={"removed": removed, "retention_days": days})
    return removed


def run_daily(db: Session) -> dict[str, int]:
    expired = expire_due(db)
    cutoff = datetime.now(UTC) - timedelta(days=NOTIFICATION_DAYS)
    old_notes = db.execute(delete(Notification).where(Notification.created_at < cutoff)).rowcount or 0  # type: ignore[attr-defined]
    return {
        "risk_expired": expired,
        "audit_purged": purge_audit(db),
        "notifications_purged": old_notes,
        "sla_updated": apply_sla(db),
    }
