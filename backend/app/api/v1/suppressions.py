import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from app.core.audit import audit
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import Finding, Plugin, SuppressionRule, User
from app.models.enums import FindingStatus
from app.schemas.workflow import SuppressionIn, SuppressionOut, SuppressionUpdate
from app.services.suppression import _matches, apply_rule, release_rule

router = APIRouter(prefix="/suppressions", tags=["suppressions"])

Reader = Annotated[User, Depends(require(Perm.FINDINGS_READ))]
Editor = Annotated[User, Depends(require(Perm.FINDINGS_UPDATE))]


def _unscoped(user: User) -> None:
    # A rule can touch any host, so network-scoped users cannot create or change one
    if user.scope_restricted:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Suppression rules affect all networks")


def _out(db: DB, rule: SuppressionRule) -> SuppressionOut:
    matched = db.scalar(
        select(func.count()).where(*_matches(rule), Finding.status == FindingStatus.FALSE_POSITIVE)
    )
    out = SuppressionOut.model_validate(rule)
    out.plugin_name = db.scalar(select(Plugin.name).where(Plugin.id == rule.plugin_id)) or ""
    out.matched = matched or 0
    return out


@router.get("", response_model=list[SuppressionOut])
def list_rules(_: Reader, db: DB) -> list[SuppressionOut]:
    rules = db.scalars(select(SuppressionRule).order_by(SuppressionRule.id.desc())).unique()
    return [_out(db, r) for r in rules]


@router.post("", response_model=SuppressionOut, status_code=201)
def create_rule(body: SuppressionIn, request: Request, user: Editor, db: DB) -> SuppressionOut:
    _unscoped(user)
    if db.get(Plugin, body.plugin_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plugin not found")
    cidr = None
    if body.cidr:
        try:
            cidr = str(ipaddress.ip_network(body.cidr.strip(), strict=False))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid CIDR") from exc
    rule = SuppressionRule(
        plugin_id=body.plugin_id, cidr=cidr, port=body.port, reason=body.reason.strip(), created_by_id=user.id
    )
    db.add(rule)
    db.flush()
    count = apply_rule(db, rule, actor_id=user.id)
    audit(
        db,
        "suppression.created",
        request=request,
        user=user,
        entity_type="suppression",
        entity_id=rule.id,
        details={**body.model_dump(), "applied": count},
    )
    db.commit()
    db.refresh(rule)
    return _out(db, rule)


@router.patch("/{rule_id}", response_model=SuppressionOut)
def update_rule(
    rule_id: int, body: SuppressionUpdate, request: Request, user: Editor, db: DB
) -> SuppressionOut:
    _unscoped(user)
    rule = db.get(SuppressionRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    if body.reason is not None:
        rule.reason = body.reason.strip()
    if body.enabled is not None and body.enabled != rule.enabled:
        rule.enabled = body.enabled
        if body.enabled:
            apply_rule(db, rule, actor_id=user.id)
        else:
            release_rule(db, rule, actor_id=user.id)
    audit(
        db,
        "suppression.updated",
        request=request,
        user=user,
        entity_type="suppression",
        entity_id=rule.id,
        details=body.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(rule)
    return _out(db, rule)


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, request: Request, user: Editor, db: DB) -> None:
    _unscoped(user)
    rule = db.get(SuppressionRule, rule_id)
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rule not found")
    released = release_rule(db, rule, actor_id=user.id) if rule.enabled else 0
    db.delete(rule)
    audit(
        db,
        "suppression.deleted",
        request=request,
        user=user,
        entity_type="suppression",
        entity_id=rule_id,
        details={"released": released},
    )
    db.commit()
