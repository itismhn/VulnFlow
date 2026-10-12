from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.audit import audit
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import SlaPolicy, User
from app.schemas.workflow import SlaPolicyIn, SlaPolicyOut
from app.services.sla import apply_sla

router = APIRouter(prefix="/sla-policies", tags=["sla"])

Reader = Annotated[User, Depends(require(Perm.FINDINGS_READ))]
Admin = Annotated[User, Depends(require(Perm.SETTINGS_MANAGE))]


@router.get("", response_model=list[SlaPolicyOut])
def list_policies(_: Reader, db: DB) -> list[SlaPolicy]:
    return list(db.scalars(select(SlaPolicy).order_by(SlaPolicy.zone.is_not(None), SlaPolicy.zone)))


def _save(db: DB, policy: SlaPolicy, request: Request, user: User, action: str) -> dict[str, int]:
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A policy for this zone already exists") from exc
    changed = apply_sla(db)
    audit(
        db,
        action,
        request=request,
        user=user,
        entity_type="sla_policy",
        entity_id=policy.id,
        details={"zone": policy.zone, "recomputed": changed},
    )
    db.commit()
    return {"id": policy.id, "recomputed": changed}


@router.post("", response_model=dict[str, int], status_code=201)
def create_policy(body: SlaPolicyIn, request: Request, user: Admin, db: DB) -> dict[str, int]:
    policy = SlaPolicy(**body.model_dump())
    db.add(policy)
    return _save(db, policy, request, user, "sla_policy.created")


@router.put("/{policy_id}", response_model=dict[str, int])
def update_policy(policy_id: int, body: SlaPolicyIn, request: Request, user: Admin, db: DB) -> dict[str, int]:
    policy = db.get(SlaPolicy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Policy not found")
    values = body.model_dump()
    if policy.zone is None:
        values["zone"] = None  # the default policy stays the default
    for key, value in values.items():
        setattr(policy, key, value)
    return _save(db, policy, request, user, "sla_policy.updated")


@router.delete("/{policy_id}", status_code=204)
def delete_policy(policy_id: int, request: Request, user: Admin, db: DB) -> None:
    policy = db.get(SlaPolicy, policy_id)
    if policy is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Policy not found")
    if policy.zone is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The default policy cannot be deleted; disable it instead"
        )
    db.delete(policy)
    db.flush()
    apply_sla(db)
    audit(db, "sla_policy.deleted", request=request, user=user, entity_type="sla_policy", entity_id=policy_id)
    db.commit()
