from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, literal_column, select

from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import Finding, Plugin, User
from app.schemas.common import Page
from app.schemas.finding import FiltersQuery, FindingFilters, PluginOut
from app.services.findings_query import apply_filters, base_query

router = APIRouter(prefix="/vulnerabilities", tags=["vulnerabilities"])

Reader = Annotated[User, Depends(require(Perm.FINDINGS_READ))]


class VulnRow(BaseModel):
    plugin_id: int
    name: str
    family: str
    severity: int
    cvss3_base: float | None
    vpr_score: float | None
    epss_score: float | None
    exploit_available: bool
    cves: list[str]
    hosts: int
    instances: int


class VulnDetail(BaseModel):
    plugin: PluginOut
    hosts: int
    instances: int


SORTS = {
    "severity": literal_column("severity"),
    "hosts": literal_column("hosts"),
    "cvss": Plugin.cvss3_base,
    "vpr": Plugin.vpr_score,
    "name": Plugin.name,
}


@router.get("", response_model=Page[VulnRow])
def list_vulnerabilities(
    user: Reader,
    db: DB,
    filters: FiltersQuery,
    sort: str = "-severity",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Page[VulnRow]:
    stmt = base_query(
        user,
        Plugin.id.label("plugin_id"),
        Plugin.name,
        Plugin.family,
        func.max(Finding.severity).label("severity"),
        Plugin.cvss3_base,
        Plugin.vpr_score,
        Plugin.epss_score,
        Plugin.exploit_available,
        Plugin.cves,
        func.count(func.distinct(Finding.asset_id)).label("hosts"),
        func.count().label("instances"),
    )
    stmt = apply_filters(stmt, filters).group_by(Plugin.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = SORTS.get(sort.lstrip("-"), SORTS["severity"])
    order = col.desc().nulls_last() if sort.startswith("-") else col.asc().nulls_last()
    rows = db.execute(
        stmt.order_by(order, literal_column("hosts").desc(), Plugin.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(
        items=[VulnRow.model_validate(r._asdict()) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{plugin_id}", response_model=VulnDetail)
def get_vulnerability(plugin_id: int, user: Reader, db: DB) -> VulnDetail:
    plugin = db.get(Plugin, plugin_id)
    if plugin is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vulnerability not found")
    filters = FindingFilters(plugin_id=[plugin_id], include_info=True)
    hosts, instances = db.execute(
        apply_filters(base_query(user, func.count(func.distinct(Finding.asset_id)), func.count()), filters)
    ).one()
    return VulnDetail(plugin=PluginOut.model_validate(plugin), hosts=hosts, instances=instances)
