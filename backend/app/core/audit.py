from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def client_ip(request: Request | None) -> str:
    if request is None:
        return ""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def audit(
    db: Session,
    action: str,
    *,
    request: Request | None = None,
    user: User | None = None,
    entity_type: str = "",
    entity_id: Any = "",
    details: dict[str, Any] | None = None,
    username: str | None = None,
) -> None:
    """Add an audit row to the session; committed with the caller's transaction."""
    db.add(
        AuditLog(
            actor_id=user.id if user else None,
            actor_username=username or (user.username if user else "system"),
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            details=details or {},
            ip=client_ip(request),
            user_agent=(request.headers.get("User-Agent", "") if request else "")[:255],
        )
    )
