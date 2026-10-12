from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select, update

from app.core.deps import DB, CurrentUser
from app.models import Notification
from app.schemas.workflow import NotificationList, NotificationOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationList)
def list_notifications(
    user: CurrentUser, db: DB, unread_only: bool = False, limit: int = 30
) -> NotificationList:
    conds = [Notification.user_id == user.id]
    if unread_only:
        conds.append(Notification.read_at.is_(None))
    rows = db.scalars(
        select(Notification).where(*conds).order_by(Notification.id.desc()).limit(min(max(limit, 1), 100))
    ).unique()
    unread = db.scalar(
        select(func.count()).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return NotificationList(items=[NotificationOut.model_validate(n) for n in rows], unread=unread or 0)


@router.post("/read", response_model=dict[str, int])
def mark_read(user: CurrentUser, db: DB, ids: Annotated[list[int] | None, Query()] = None) -> dict[str, int]:
    """Mark the given notifications (or all) as read."""
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    result = db.execute(stmt.values(read_at=datetime.now(UTC)))
    db.commit()
    return {"updated": result.rowcount or 0}  # type: ignore[attr-defined]
