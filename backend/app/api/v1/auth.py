import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select, update

from app.core.audit import audit
from app.core.config import settings
from app.core.deps import DB, CurrentUser
from app.core.permissions import ROLE_PERMISSIONS
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    create_token,
    decode_token,
    hash_password,
    new_csrf_token,
    password_problems,
    verify_password,
)
from app.models import RefreshToken, User
from app.schemas.user import ChangePasswordIn, LoginIn, MeOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_PATH = "/api/v1/auth"


def me_out(user: User) -> MeOut:
    return MeOut(
        **UserOut.model_validate(user).model_dump(),
        permissions=sorted(ROLE_PERMISSIONS.get(user.role, frozenset())),
    )


def _issue_session(db: DB, response: Response, user: User) -> None:
    refresh = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
    )
    db.add(refresh)
    access = create_token(
        str(user.id), "access", timedelta(minutes=settings.access_token_minutes), role=user.role
    )
    refresh_jwt = create_token(
        str(user.id), "refresh", timedelta(days=settings.refresh_token_days), jti=str(refresh.id)
    )
    common: dict[str, Any] = {"secure": settings.cookie_secure, "samesite": "strict"}
    response.set_cookie(
        ACCESS_COOKIE, access, httponly=True, max_age=settings.access_token_minutes * 60, **common
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_jwt,
        httponly=True,
        path=REFRESH_PATH,
        max_age=settings.refresh_token_days * 86400,
        **common,
    )
    response.set_cookie(CSRF_COOKIE, new_csrf_token(), httponly=False, **common)


def _clear_session(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE)
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    response.delete_cookie(CSRF_COOKIE)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: DB) -> MeOut:
    username = body.username.strip().lower()
    user = db.scalar(select(User).where(func.lower(User.username) == username))
    now = datetime.now(UTC)

    if user and user.locked_until and user.locked_until > now:
        audit(db, "auth.login_locked", request=request, user=user, entity_type="user", entity_id=user.id)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account temporarily locked. Try again later.")

    if not verify_password(body.password, user.password_hash if user else None) or not user:
        if user:
            user.failed_logins += 1
            if user.failed_logins >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_logins = 0
        audit(
            db,
            "auth.login_failed",
            request=request,
            user=user,
            username=body.username[:64],
            entity_type="user",
            entity_id=user.id if user else "",
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    if not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    _issue_session(db, response, user)
    audit(db, "auth.login", request=request, user=user, entity_type="user", entity_id=user.id)
    db.commit()
    return me_out(user)


@router.post("/refresh", response_model=MeOut)
def refresh(request: Request, response: Response, db: DB) -> MeOut:
    token = request.cookies.get(REFRESH_COOKIE)
    payload = decode_token(token, "refresh") if token else None
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

    stored = db.get(RefreshToken, uuid.UUID(payload["jti"]))
    user = db.get(User, int(payload["sub"]))
    if stored is None or user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    if stored.revoked_at is not None:
        # A rotated token was replayed: assume theft and end every session of this user
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )
        audit(db, "auth.refresh_reuse", request=request, user=user, entity_type="user", entity_id=user.id)
        db.commit()
        _clear_session(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    if stored.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")

    stored.revoked_at = datetime.now(UTC)
    _issue_session(db, response, user)
    db.commit()
    return me_out(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DB) -> None:
    token = request.cookies.get(REFRESH_COOKIE)
    payload = decode_token(token, "refresh") if token else None
    if payload:
        stored = db.get(RefreshToken, uuid.UUID(payload["jti"]))
        if stored and stored.revoked_at is None:
            stored.revoked_at = datetime.now(UTC)
        audit(db, "auth.logout", request=request, username=None, entity_type="user", entity_id=payload["sub"])
        db.commit()
    _clear_session(response)


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser) -> MeOut:
    return me_out(user)


@router.post("/change-password", response_model=MeOut)
def change_password(body: ChangePasswordIn, request: Request, user: CurrentUser, db: DB) -> MeOut:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must differ from the current one")
    problems = password_problems(body.new_password)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Password " + ", ".join(problems))
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    audit(db, "auth.password_changed", request=request, user=user, entity_type="user", entity_id=user.id)
    db.commit()
    return me_out(user)
