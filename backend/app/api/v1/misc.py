from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import any_, func, literal, or_, select

from app.core.config import settings
from app.core.deps import DB, CurrentUser, require
from app.core.permissions import Perm
from app.models import Asset, AuditLog, Plugin, Scan, User
from app.schemas.common import ORM, Page
from app.services.scoping import scope_assets

router = APIRouter(tags=["misc"])


class SearchHit(BaseModel):
    kind: str
    id: int
    title: str
    subtitle: str = ""


@router.get("/search", response_model=list[SearchHit])
def search(
    user: CurrentUser, db: DB, q: Annotated[str, Query(min_length=2, max_length=100)]
) -> list[SearchHit]:
    term = q.strip()
    like = f"%{term}%"
    hits: list[SearchHit] = []

    assets = scope_assets(
        select(Asset)
        .where(or_(func.host(Asset.ip).like(f"{term}%"), Asset.hostname.ilike(like), Asset.fqdn.ilike(like)))
        .order_by(Asset.ip)
        .limit(6),
        user,
    )
    hits += [
        SearchHit(kind="asset", id=a.id, title=str(a.ip), subtitle=a.hostname or a.fqdn or a.os)
        for a in db.scalars(assets)
    ]

    plugin_cond = or_(Plugin.name.ilike(like), literal(term.upper()) == any_(Plugin.cves))
    if term.isdigit():
        plugin_cond = or_(plugin_cond, Plugin.id == int(term))
    hits += [
        SearchHit(kind="vulnerability", id=p.id, title=p.name, subtitle=f"Plugin {p.id} · {p.family}")
        for p in db.scalars(select(Plugin).where(plugin_cond).order_by(Plugin.severity.desc()).limit(6))
    ]

    if not user.scope_restricted:
        hits += [
            SearchHit(kind="scan", id=s.id, title=s.name, subtitle=s.filename)
            for s in db.scalars(
                select(Scan)
                .where(or_(Scan.name.ilike(like), Scan.filename.ilike(like)))
                .order_by(Scan.id.desc())
                .limit(4)
            )
        ]
    return hits


class AuditOut(ORM):
    id: int
    created_at: datetime
    actor_id: int | None
    actor_username: str
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, Any]
    ip: str
    user_agent: str


@router.get("/audit", response_model=Page[AuditOut])
def audit_log(
    _: Annotated[User, Depends(require(Perm.AUDIT_READ))],
    db: DB,
    action: str | None = None,
    actor: str | None = None,
    entity_type: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[AuditOut]:
    conds: list[Any] = []
    if action:
        conds.append(AuditLog.action.ilike(f"{action}%"))
    if actor:
        conds.append(AuditLog.actor_username.ilike(f"%{actor}%"))
    if entity_type:
        conds.append(AuditLog.entity_type == entity_type)
    total = db.scalar(select(func.count()).select_from(AuditLog).where(*conds)) or 0
    rows = db.scalars(
        select(AuditLog)
        .where(*conds)
        .order_by(AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=[AuditOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size)


class Meta(BaseModel):
    app_name: str
    version: str


@router.get("/meta", response_model=Meta)
def meta() -> Meta:
    from app import __version__

    return Meta(app_name=settings.app_name, version=__version__)
