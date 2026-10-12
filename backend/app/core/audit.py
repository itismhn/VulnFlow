from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog, User


def client_ip(request: Request | None) -> str:
    # X-Forwarded-For is resolved by uvicorn --proxy-headers behind the bundled proxy;
    # reading it here would let any client forge the address it is logged under.
    if request is None or request.client is None:
        return ""
    return request.client.host


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
