from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select

from app.core.audit import audit
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import Finding, RiskAcceptance, User
from app.models.enums import AcceptanceStatus
from app.schemas.common import Page
from app.schemas.finding import FindingOut
from app.schemas.workflow import (
    RiskAcceptanceOut,
    RiskAcceptanceRow,
    RiskDecisionIn,
    RiskRequestIn,
    RiskRevokeIn,
)
from app.services import risk
from app.services.findings_query import base_query

router = APIRouter(prefix="/risk-acceptances", tags=["risk"])

Reader = Annotated[User, Depends(require(Perm.FINDINGS_READ))]
Requester = Annotated[User, Depends(require(Perm.RISK_REQUEST))]
Approver = Annotated[User, Depends(require(Perm.RISK_APPROVE))]


def _row(ra: RiskAcceptance, finding: Finding) -> RiskAcceptanceRow:
    return RiskAcceptanceRow.model_validate(
        {**RiskAcceptanceOut.model_validate(ra).model_dump(), "finding": FindingOut.model_validate(finding)}
    )


@router.get("", response_model=Page[RiskAcceptanceRow])
def list_acceptances(
    user: Reader,
    db: DB,
    status_: Annotated[list[AcceptanceStatus] | None, Query(alias="status")] = None,
    mine: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[RiskAcceptanceRow]:
    visible = base_query(user, Finding.id).scalar_subquery()
    conds: list[Any] = [RiskAcceptance.finding_id.in_(visible)]
    if status_:
        conds.append(RiskAcceptance.status.in_([s.value for s in status_]))
    if mine:
        conds.append(RiskAcceptance.requested_by_id == user.id)
    total = db.scalar(select(func.count()).select_from(RiskAcceptance).where(*conds)) or 0
    rows = db.execute(
        select(RiskAcceptance, Finding)
        .join(Finding, Finding.id == RiskAcceptance.finding_id)
        .where(*conds)
        .order_by(
            (RiskAcceptance.status == AcceptanceStatus.PENDING).desc(),
            RiskAcceptance.created_at.desc(),
            RiskAcceptance.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique()
    return Page(items=[_row(ra, f) for ra, f in rows], total=total, page=page, page_size=page_size)


@router.get("/finding/{finding_id}", response_model=list[RiskAcceptanceOut])
def finding_acceptances(finding_id: int, user: Reader, db: DB) -> list[RiskAcceptance]:
    if db.scalar(base_query(user, Finding.id).where(Finding.id == finding_id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found")
    return list(
        db.scalars(
            select(RiskAcceptance)
            .where(RiskAcceptance.finding_id == finding_id)
            .order_by(RiskAcceptance.created_at.desc(), RiskAcceptance.id.desc())
        ).unique()
    )


@router.post("", response_model=dict[str, int], status_code=201)
def request_acceptance(body: RiskRequestIn, request: Request, user: Requester, db: DB) -> dict[str, int]:
    findings = list(db.scalars(base_query(user).where(Finding.id.in_(body.finding_ids))).unique())
    if len(findings) != len(set(body.finding_ids)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more findings were not found")
    created = [risk.request_acceptance(db, f, body.justification, body.expires_at, user) for f in findings]
    audit(
        db,
        "risk.requested",
        request=request,
        user=user,
        entity_type="finding",
        entity_id=",".join(str(f.id) for f in findings)[:120],
        details={"count": len(created), "expires_at": body.expires_at.isoformat()},
    )
    db.commit()
    return {"created": len(created)}


def _get(db: DB, user: User, ra_id: int) -> RiskAcceptance:
    ra = db.get(RiskAcceptance, ra_id)
    visible = ra is not None and db.scalar(base_query(user, Finding.id).where(Finding.id == ra.finding_id))
    if ra is None or not visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return ra


@router.post("/{ra_id}/decision", response_model=RiskAcceptanceOut)
def decide(ra_id: int, body: RiskDecisionIn, request: Request, user: Approver, db: DB) -> RiskAcceptance:
    ra = risk.decide(db, _get(db, user, ra_id), body.approve, body.note, user)
    audit(
        db,
        "risk.approved" if body.approve else "risk.rejected",
        request=request,
        user=user,
        entity_type="finding",
        entity_id=ra.finding_id,
        details={"acceptance_id": ra.id, "note": body.note[:500]},
    )
    db.commit()
    db.refresh(ra)
    return ra


@router.post("/{ra_id}/revoke", response_model=RiskAcceptanceOut)
def revoke(ra_id: int, body: RiskRevokeIn, request: Request, user: Requester, db: DB) -> RiskAcceptance:
    ra = risk.revoke(db, _get(db, user, ra_id), body.note, user)
    audit(
        db,
        "risk.revoked",
        request=request,
        user=user,
        entity_type="finding",
        entity_id=ra.finding_id,
        details={"acceptance_id": ra.id},
    )
    db.commit()
    db.refresh(ra)
    return ra
