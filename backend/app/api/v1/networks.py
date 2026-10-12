import csv
import io
import ipaddress
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app.core.audit import audit
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import Asset, Finding, Network, User, user_networks
from app.models.enums import ACTIVE_STATUSES
from app.schemas.asset import (
    NetworkCreate,
    NetworkImportResult,
    NetworkOut,
    NetworkStats,
    NetworkUpdate,
)
from app.schemas.common import SeverityCounts
from app.services import networks as network_service
from app.services import sla
from app.services.scoping import asset_scope_clause

router = APIRouter(prefix="/networks", tags=["networks"])

Reader = Annotated[User, Depends(require(Perm.NETWORKS_READ))]
Manager = Annotated[User, Depends(require(Perm.NETWORKS_MANAGE))]


def _visible_networks(user: User) -> list:  # type: ignore[type-arg]
    """Scoped users see their own networks and any networks nested inside them."""
    if not user.scope_restricted:
        return []
    granted = aliased(Network)
    return [
        exists(
            select(1)
            .select_from(user_networks.join(granted, granted.id == user_networks.c.network_id))
            .where(user_networks.c.user_id == user.id, Network.cidr.op("<<=")(granted.cidr))
        )
    ]


@router.get("", response_model=list[NetworkStats])
def list_networks(user: Reader, db: DB) -> list[NetworkStats]:
    nets = list(db.scalars(select(Network).where(*_visible_networks(user)).order_by(Network.cidr)))
    if not nets:
        return []
    # Count assets and active findings contained in each range (nested ranges included)
    asset_q = (
        select(Network.id, func.count(func.distinct(Asset.id)))
        .join(Asset, Asset.ip.op("<<=")(Network.cidr))
        .where(Network.id.in_([n.id for n in nets]))
        .group_by(Network.id)
    )
    if user.scope_restricted:
        asset_q = asset_q.where(asset_scope_clause(user))
    assets = dict(db.execute(asset_q).all())

    sev_q = (
        select(Network.id, Finding.severity, func.count())
        .join(Asset, Asset.ip.op("<<=")(Network.cidr))
        .join(
            Finding,
            and_(
                Finding.asset_id == Asset.id,
                Finding.status.in_([s.value for s in ACTIVE_STATUSES]),
                Finding.severity > 0,
            ),
        )
        .where(Network.id.in_([n.id for n in nets]))
        .group_by(Network.id, Finding.severity)
    )
    if user.scope_restricted:
        sev_q = sev_q.where(asset_scope_clause(user))
    sev: dict[int, dict[int, int]] = {}
    for nid, s, n in db.execute(sev_q):
        sev.setdefault(nid, {})[s] = n

    return [
        NetworkStats(
            **NetworkOut.model_validate(n).model_dump(),
            asset_count=assets.get(n.id, 0),
            open=SeverityCounts.from_map(sev.get(n.id, {})),
        )
        for n in nets
    ]


@router.get("/zones", response_model=list[str])
def list_zones(user: Reader, db: DB) -> list[str]:
    return list(
        db.scalars(
            select(Network.zone)
            .where(Network.zone != "", *_visible_networks(user))
            .distinct()
            .order_by(Network.zone)
        )
    )


@router.get("/{network_id}", response_model=NetworkOut)
def get_network(network_id: int, user: Reader, db: DB) -> Network:
    net = db.scalar(select(Network).where(Network.id == network_id, *_visible_networks(user)))
    if net is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Network not found")
    return net


def _commit_or_conflict(db: DB) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A network with this CIDR already exists") from exc


@router.post("", response_model=NetworkOut, status_code=201)
def create_network(body: NetworkCreate, request: Request, user: Manager, db: DB) -> Network:
    net = Network(**body.model_dump())
    db.add(net)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A network with this CIDR already exists") from exc
    network_service.reassign_assets(db)
    sla.apply_sla(db)
    audit(
        db,
        "network.created",
        request=request,
        user=user,
        entity_type="network",
        entity_id=net.id,
        details=body.model_dump(),
    )
    _commit_or_conflict(db)
    return net


@router.patch("/{network_id}", response_model=NetworkOut)
def update_network(network_id: int, body: NetworkUpdate, request: Request, user: Manager, db: DB) -> Network:
    net = db.get(Network, network_id)
    if net is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Network not found")
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changes.items():
        setattr(net, key, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A network with this CIDR already exists") from exc
    if "cidr" in changes:
        network_service.reassign_assets(db)
    if changes.keys() & {"cidr", "zone"}:
        sla.apply_sla(db)
    audit(
        db,
        "network.updated",
        request=request,
        user=user,
        entity_type="network",
        entity_id=net.id,
        details=changes,
    )
    _commit_or_conflict(db)
    return net


@router.delete("/{network_id}", status_code=204)
def delete_network(network_id: int, request: Request, user: Manager, db: DB) -> None:
    net = db.get(Network, network_id)
    if net is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Network not found")
    audit(
        db,
        "network.deleted",
        request=request,
        user=user,
        entity_type="network",
        entity_id=net.id,
        details={"name": net.name, "cidr": str(net.cidr)},
    )
    db.delete(net)
    db.flush()
    network_service.reassign_assets(db)
    sla.apply_sla(db)
    db.commit()


@router.post("/import", response_model=NetworkImportResult)
async def import_networks(file: UploadFile, request: Request, user: Manager, db: DB) -> NetworkImportResult:
    """CSV with header: name,cidr,zone,criticality,owner,description (upserts on cidr)."""
    raw = (await file.read(5 * 1024 * 1024)).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    created = updated = 0
    errors: list[str] = []
    for line, row in enumerate(reader, start=2):
        clean = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        if not clean.get("criticality"):
            clean.pop("criticality", None)
        try:
            data = NetworkCreate(**clean)  # type: ignore[arg-type]
        except ValidationError as exc:
            errors.append(f"Line {line}: {exc.errors()[0]['msg']}")
            continue
        existing = db.scalar(select(Network).where(Network.cidr == data.cidr))
        if existing:
            for key, value in data.model_dump().items():
                setattr(existing, key, value)
            updated += 1
        else:
            db.add(Network(**data.model_dump()))
            created += 1
        db.flush()
    network_service.reassign_assets(db)
    sla.apply_sla(db)
    audit(
        db,
        "network.imported",
        request=request,
        user=user,
        entity_type="network",
        details={"created": created, "updated": updated, "errors": len(errors)},
    )
    db.commit()
    return NetworkImportResult(created=created, updated=updated, errors=errors[:50])


class MapCell(BaseModel):
    """One heatmap cell: a host (host mode) or a /24 block (block mode)."""

    address: str
    asset_id: int | None = None
    label: str = ""
    hosts: int = 1
    # Highest active severity, or -1 when scanned and clean
    max_severity: int


class NetworkMap(BaseModel):
    mode: Literal["host", "block"]
    cidr: str
    cells: list[MapCell]


HOST_MODE_MIN_PREFIX = 22  # up to 1024 addresses drawn one cell per address


@router.get("/{network_id}/map", response_model=NetworkMap)
def network_map(network_id: int, user: Reader, db: DB) -> NetworkMap:
    net = get_network(network_id, user, db)
    cidr = ipaddress.ip_network(str(net.cidr))
    worst = func.coalesce(
        func.max(Finding.severity).filter(
            Finding.status.in_([s.value for s in ACTIVE_STATUSES]), Finding.severity > 0
        ),
        -1,
    )
    in_range = Asset.ip.op("<<=")(net.cidr)
    host_mode = (cidr.version == 4 and cidr.prefixlen >= HOST_MODE_MIN_PREFIX) or cidr.version == 6
    if host_mode:
        stmt = (
            select(Asset.id, Asset.ip, Asset.hostname, Asset.fqdn, worst.label("worst"))
            .outerjoin(Finding, Finding.asset_id == Asset.id)
            .where(in_range)
            .group_by(Asset.id)
            .order_by(Asset.ip)
            .limit(4096)
        )
        if user.scope_restricted:
            stmt = stmt.where(asset_scope_clause(user))
        cells = [
            MapCell(address=str(r.ip), asset_id=r.id, label=r.hostname or r.fqdn, max_severity=r.worst)
            for r in db.execute(stmt)
        ]
        return NetworkMap(mode="host", cidr=str(cidr), cells=cells)

    block = func.network(func.set_masklen(Asset.ip, 24))
    stmt = (
        select(block.label("block"), func.count(func.distinct(Asset.id)).label("hosts"), worst.label("worst"))
        .outerjoin(Finding, Finding.asset_id == Asset.id)
        .where(in_range)
        .group_by(block)
        .order_by(block)
        .limit(4096)
    )
    if user.scope_restricted:
        stmt = stmt.where(asset_scope_clause(user))
    cells = [MapCell(address=str(r.block), hosts=r.hosts, max_severity=r.worst) for r in db.execute(stmt)]
    return NetworkMap(mode="block", cidr=str(cidr), cells=cells)
