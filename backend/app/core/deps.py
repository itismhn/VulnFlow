import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.permissions import Perm, has_perm
from app.core.security import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER, decode_token
from app.models import RefreshToken, User

DB = Annotated[Session, Depends(get_db)]

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _session_alive(db: Session, user_id: int, sid: str | None) -> bool:
    """An access token is valid only while its sign-in has an unrevoked refresh token."""
    try:
        family = uuid.UUID(sid or "")
    except ValueError:
        return False
    return (
        db.scalar(
            select(RefreshToken.id)
            .where(
                RefreshToken.family_id == family,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > func.now(),
            )
            .limit(1)
        )
        is not None
    )


def get_current_user(request: Request, db: DB) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    via_cookie = token is not None
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth.removeprefix("Bearer ")
    payload = decode_token(token, "access") if token else None
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    # Double-submit CSRF check for cookie-authenticated, state-changing requests
    if via_cookie and request.method in _UNSAFE_METHODS:
        cookie = request.cookies.get(CSRF_COOKIE)
        if not cookie or cookie != request.headers.get(CSRF_HEADER):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")

    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or not _session_alive(db, user.id, payload.get("sid")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require(perm: Perm) -> Callable[[User], User]:
    def checker(user: CurrentUser) -> User:
        if user.must_change_password:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Password change required")
        if not has_perm(user.role, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return checker
