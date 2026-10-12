from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select, update

from app.core.audit import audit
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.core.security import hash_password, password_problems
from app.models import Network, RefreshToken, User
from app.models.enums import Role
from app.schemas.user import PasswordReset, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])
Admin = Annotated[User, Depends(require(Perm.USERS_MANAGE))]


def _check_password(password: str) -> None:
    problems = password_problems(password)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Password " + ", ".join(problems))


def _networks(db: DB, ids: list[int]) -> list[Network]:
    nets = list(db.scalars(select(Network).where(Network.id.in_(ids)))) if ids else []
    if len(nets) != len(set(ids)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown network id")
    return nets


def _active_admins(db: DB) -> int:
    return db.scalar(select(func.count()).where(User.role == Role.ADMIN, User.is_active.is_(True))) or 0


@router.get("", response_model=list[UserOut])
def list_users(_: Admin, db: DB) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.get("/directory", response_model=list[dict[str, int | str]])
def directory(_: Annotated[User, Depends(require(Perm.FINDINGS_READ))], db: DB) -> list[dict[str, int | str]]:
    """Minimal list of active users, for assignee pickers."""
    rows = db.execute(
        select(User.id, User.username, User.full_name)
        .where(User.is_active.is_(True), User.role != Role.VIEWER)
        .order_by(User.username)
    )
    return [{"id": r.id, "username": r.username, "full_name": r.full_name} for r in rows]


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, admin: Admin, db: DB) -> User:
    _check_password(body.password)
    username = body.username.lower()
    exists = db.scalar(
        select(User.id).where(
            (func.lower(User.username) == username) | (func.lower(User.email) == body.email.lower())
        )
    )
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username or email already exists")
    user = User(
        username=username,
        email=body.email.lower(),
        full_name=body.full_name,
        role=body.role,
        password_hash=hash_password(body.password),
        must_change_password=True,
        scope_restricted=body.scope_restricted,
        networks=_networks(db, body.network_ids),
    )
    db.add(user)
    db.flush()
    audit(
        db,
        "user.created",
        request=request,
        user=admin,
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username, "role": user.role},
    )
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, request: Request, admin: Admin, db: DB) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    changes = body.model_dump(exclude_unset=True)
    demoting = user.role == Role.ADMIN and (
        changes.get("role", Role.ADMIN) != Role.ADMIN or changes.get("is_active") is False
    )
    if demoting and _active_admins(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot remove the last active admin")

    if "network_ids" in changes:
        user.networks = _networks(db, changes.pop("network_ids") or [])
    if changes.get("email"):
        changes["email"] = changes["email"].lower()
    for key, value in changes.items():
        setattr(user, key, value)
    if changes.get("is_active") is False:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )
    audit(
        db,
        "user.updated",
        request=request,
        user=admin,
        entity_type="user",
        entity_id=user.id,
        details={k: str(v) for k, v in body.model_dump(exclude_unset=True).items()},
    )
    db.commit()
    return user


@router.post("/{user_id}/reset-password", response_model=UserOut)
def reset_password(user_id: int, body: PasswordReset, request: Request, admin: Admin, db: DB) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    _check_password(body.password)
    user.password_hash = hash_password(body.password)
    user.must_change_password = True
    user.failed_logins = 0
    user.locked_until = None
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=func.now())
    )
    audit(db, "user.password_reset", request=request, user=admin, entity_type="user", entity_id=user.id)
    db.commit()
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, admin: Admin, db: DB) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot delete your own account")
    if user.role == Role.ADMIN and _active_admins(db) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cannot remove the last active admin")
    audit(
        db,
        "user.deleted",
        request=request,
        user=admin,
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username},
    )
    db.delete(user)
    db.commit()
