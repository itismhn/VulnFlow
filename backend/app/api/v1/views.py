from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import SavedView, User
from app.models.enums import Role
from app.schemas.workflow import SavedViewIn, SavedViewOut

router = APIRouter(prefix="/views", tags=["views"])

Reader = Annotated[User, Depends(require(Perm.FINDINGS_READ))]


@router.get("", response_model=list[SavedViewOut])
def list_views(user: Reader, db: DB) -> list[SavedView]:
    return list(
        db.scalars(
            select(SavedView)
            .where(or_(SavedView.owner_id == user.id, SavedView.shared.is_(True)))
            .order_by(SavedView.name)
        ).unique()
    )


def _commit(db: DB) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a view with this name") from exc


@router.post("", response_model=SavedViewOut, status_code=201)
def create_view(body: SavedViewIn, user: Reader, db: DB) -> SavedView:
    view = SavedView(owner_id=user.id, **body.model_dump())
    db.add(view)
    _commit(db)
    db.refresh(view)
    return view


def _owned(db: DB, user: User, view_id: int) -> SavedView:
    view = db.get(SavedView, view_id)
    if view is None or (view.owner_id != user.id and not view.shared):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "View not found")
    if view.owner_id != user.id and user.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner can change this view")
    return view


@router.put("/{view_id}", response_model=SavedViewOut)
def update_view(view_id: int, body: SavedViewIn, user: Reader, db: DB) -> SavedView:
    view = _owned(db, user, view_id)
    for key, value in body.model_dump().items():
        setattr(view, key, value)
    _commit(db)
    db.refresh(view)
    return view


@router.delete("/{view_id}", status_code=204)
def delete_view(view_id: int, user: Reader, db: DB) -> None:
    db.delete(_owned(db, user, view_id))
    db.commit()
