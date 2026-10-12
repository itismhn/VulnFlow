import re
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import Perm, has_perm
from app.models import Finding, Notification, User
from app.services.findings_query import base_query

MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_.-]{2,64})")


def notify(
    db: Session,
    user_ids: Iterable[int],
    kind: str,
    title: str,
    *,
    body: str = "",
    link: str = "",
    actor: User | None = None,
) -> None:
    for uid in set(user_ids):
        if actor is not None and uid == actor.id:
            continue
        db.add(
            Notification(
                user_id=uid,
                kind=kind,
                title=title[:255],
                body=body[:2000],
                link=link[:512],
                actor_id=actor.id if actor else None,
            )
        )


def can_see_finding(db: Session, user: User, finding_id: int) -> bool:
    if not user.is_active or not has_perm(user.role, Perm.FINDINGS_READ):
        return False
    return db.scalar(base_query(user, Finding.id).where(Finding.id == finding_id)) is not None


def mentioned_users(db: Session, text: str, finding_id: int) -> list[User]:
    """Active users named with @username who are allowed to see the finding."""
    names = {m.lower() for m in MENTION_RE.findall(text)}
    if not names:
        return []
    users = db.scalars(select(User).where(func.lower(User.username).in_(names), User.is_active.is_(True)))
    return [u for u in users if can_see_finding(db, u, finding_id)]


def users_with(db: Session, perm: Perm) -> list[User]:
    return [u for u in db.scalars(select(User).where(User.is_active.is_(True))) if has_perm(u.role, perm)]


def finding_link(finding_id: int) -> str:
    return f"/findings?finding={finding_id}"
