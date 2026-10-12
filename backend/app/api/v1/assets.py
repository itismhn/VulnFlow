import ipaddress
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import lazyload

from app.core.audit import audit
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import Asset, Finding, FindingOccurrence, Network, Scan, ScanHost, User
from app.models.enums import ACTIVE_STATUSES
from app.schemas.asset import AssetOut, AssetRow, AssetScanEntry, AssetUpdate
from app.schemas.common import Page, SeverityCounts
from app.services.findings_query import SEVERITY_WEIGHT
from app.services.scoping import scope_assets

router = APIRouter(prefix="/assets", tags=["assets"])

Reader = Annotated[User, Depends(require(Perm.ASSETS_READ))]
Editor = Annotated[User, Depends(require(Perm.ASSETS_UPDATE))]

EFFECTIVE_CRITICALITY = func.coalesce(Asset.criticality, Network.criticality, 3)
RISK_SCORE = func.coalesce(func.sum(SEVERITY_WEIGHT), 0.0) * EFFECTIVE_CRITICALITY / 3.0


def _asset_rows_query(user: User) -> Any:
    active = and_(
        Finding.asset_id == Asset.id,
        Finding.status.in_([s.value for s in ACTIVE_STATUSES]),
        Finding.severity > 0,
    )
    counts = [
        func.count(Finding.id).filter(Finding.severity == sev).label(name)
        for sev, name in ((4, "critical"), (3, "high"), (2, "medium"), (1, "low"))
    ]
    risk = RISK_SCORE.label("risk_score")
    stmt = (
        select(
            Asset,
            Network.name.label("network_name"),
            Network.zone.label("zone"),
            EFFECTIVE_CRITICALITY.label("effective_criticality"),
            risk,
            *counts,
        )
        .outerjoin(Network, Network.id == Asset.network_id)
        .outerjoin(Finding, active)
        .group_by(Asset.id, Network.id)
    )
    # Avoid the joined eager load of Asset.network, which would wrap LIMIT queries in a subquery
    return scope_assets(stmt.options(lazyload(Asset.network)), user)


def _row(r: Any) -> AssetRow:
    return AssetRow(
        **AssetOut.model_validate(r.Asset).model_dump(),
        network_name=r.network_name,
        zone=r.zone,
        effective_criticality=r.effective_criticality,
        risk_score=round(float(r.risk_score), 1),
        open=SeverityCounts(critical=r.critical, high=r.high, medium=r.medium, low=r.low),
    )


SORTS: dict[str, Any] = {
    "risk": RISK_SCORE,
    "critical": func.count(Finding.id).filter(Finding.severity == 4),
    "ip": Asset.ip,
    "hostname": Asset.hostname,
    "last_seen": Asset.last_seen,
}


@router.get("", response_model=Page[AssetRow])
def list_assets(
    user: Reader,
    db: DB,
    q: str | None = None,
    ip: str | None = None,
    network_id: int | None = None,
    zone: str | None = None,
    unassigned: bool = False,
    with_findings: bool = False,
    sort: str = "-risk",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Page[AssetRow]:
    stmt = _asset_rows_query(user)
    if q:
        stmt = stmt.where(
            or_(
                func.host(Asset.ip).like(f"{q.strip()}%"),
                Asset.hostname.ilike(f"%{q}%"),
                Asset.fqdn.ilike(f"%{q}%"),
                Asset.os.ilike(f"%{q}%"),
                Asset.netbios.ilike(f"%{q}%"),
            )
        )
    if ip:
        try:
            stmt = stmt.where(Asset.ip.op("<<=")(str(ipaddress.ip_network(ip.strip(), strict=False))))
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid IP or CIDR") from exc
    if network_id:
        net = db.get(Network, network_id)
        if net is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Network not found")
        stmt = stmt.where(Asset.ip.op("<<=")(net.cidr))
    if zone:
        stmt = stmt.where(Network.zone == zone)
    if unassigned:
        stmt = stmt.where(Asset.network_id.is_(None))
    if with_findings:
        stmt = stmt.having(func.count(Finding.id) > 0)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = SORTS.get(sort.lstrip("-"), SORTS["risk"])
    order_clause = col.desc().nulls_last() if sort.startswith("-") else col.asc().nulls_last()
    rows = db.execute(stmt.order_by(order_clause, Asset.ip).offset((page - 1) * page_size).limit(page_size))
    return Page(items=[_row(r) for r in rows], total=total, page=page, page_size=page_size)


def _get_row(db: DB, user: User, asset_id: int) -> Any:
    row = db.execute(_asset_rows_query(user).where(Asset.id == asset_id)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return row


@router.get("/{asset_id}", response_model=AssetRow)
def get_asset(asset_id: int, user: Reader, db: DB) -> AssetRow:
    return _row(_get_row(db, user, asset_id))


@router.get("/{asset_id}/scans", response_model=list[AssetScanEntry])
def asset_scans(asset_id: int, user: Reader, db: DB) -> list[AssetScanEntry]:
    _get_row(db, user, asset_id)
    counts: dict[int, dict[int, int]] = {}
    for scan_id, sev, n in db.execute(
        select(FindingOccurrence.scan_id, FindingOccurrence.severity, func.count())
        .join(Finding, Finding.id == FindingOccurrence.finding_id)
        .where(Finding.asset_id == asset_id)
        .group_by(FindingOccurrence.scan_id, FindingOccurrence.severity)
    ):
        counts.setdefault(scan_id, {})[sev] = n
    rows = db.execute(
        select(ScanHost, Scan.name)
        .join(Scan, Scan.id == ScanHost.scan_id)
        .where(ScanHost.asset_id == asset_id)
        .order_by(ScanHost.started_at.desc().nulls_last())
    )
    return [
        AssetScanEntry(
            scan_id=sh.scan_id,
            scan_name=name,
            started_at=sh.started_at,
            credentialed=sh.credentialed,
            findings=SeverityCounts.from_map(counts.get(sh.scan_id, {})),
        )
        for sh, name in rows
    ]


@router.patch("/{asset_id}", response_model=AssetRow)
def update_asset(asset_id: int, body: AssetUpdate, request: Request, user: Editor, db: DB) -> AssetRow:
    _get_row(db, user, asset_id)
    asset = db.get(Asset, asset_id)
    assert asset is not None
    if body.clear_criticality:
        asset.criticality = None
    elif body.criticality is not None:
        asset.criticality = body.criticality
    if body.tags is not None:
        asset.tags = sorted({t.strip()[:64] for t in body.tags if t.strip()})
    audit(
        db,
        "asset.updated",
        request=request,
        user=user,
        entity_type="asset",
        entity_id=asset.id,
        details=body.model_dump(exclude_unset=True),
    )
    db.commit()
    return _row(_get_row(db, user, asset_id))
