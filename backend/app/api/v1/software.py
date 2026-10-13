import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, literal_column, select, tuple_

from app.core.audit import audit
from app.core.db import SessionLocal
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import AssetSoftware, User
from app.schemas.common import Page
from app.schemas.software import (
    SoftwareFilters,
    SoftwareGroup,
    SoftwareInstance,
    SoftwareQuery,
    SoftwareStats,
    VersionCount,
)
from app.services.reporting.xlsx import rows_to_xlsx, safe_cell
from app.services.software import apply_filters, base_query, export_rows, instance_query

router = APIRouter(prefix="/software", tags=["software"])

Reader = Annotated[User, Depends(require(Perm.ASSETS_READ))]
Admin = Annotated[User, Depends(require(Perm.SETTINGS_MANAGE))]

MAX_VERSIONS_PER_GROUP = 50
KEY = (AssetSoftware.vendor, AssetSoftware.product)

GROUP_SORTS: dict[str, Any] = {
    "hosts": literal_column("hosts"),
    "versions": literal_column("version_count"),
    "name": literal_column("name"),
}


def _filtered(stmt: Any, filters: SoftwareFilters) -> Any:
    """apply_filters, turning a malformed IP filter into a 422."""
    try:
        return apply_filters(stmt, filters)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid IP or CIDR") from exc


@router.get("/stats", response_model=SoftwareStats)
def software_stats(user: Reader, db: DB) -> SoftwareStats:
    products, instances, hosts = db.execute(
        base_query(
            user,
            func.count(func.distinct(tuple_(*KEY))),
            func.count(),
            func.count(func.distinct(AssetSoftware.asset_id)),
        )
    ).one()
    by_category: dict[str, int] = dict(
        db.execute(
            base_query(user, AssetSoftware.category, func.count(func.distinct(tuple_(*KEY)))).group_by(
                AssetSoftware.category
            )
        ).all()
    )
    return SoftwareStats(products=products, instances=instances, hosts=hosts, by_category=by_category)


@router.get("", response_model=Page[SoftwareGroup])
def list_software(
    user: Reader,
    db: DB,
    filters: SoftwareQuery,
    sort: str = "-hosts",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Page[SoftwareGroup]:
    """Software grouped by product, with the versions found and how many hosts run each."""
    stmt = _filtered(
        base_query(
            user,
            *KEY,
            # A product found by several plugins can span categories (e.g. application and service)
            func.min(AssetSoftware.category).label("category"),
            func.min(AssetSoftware.name).label("name"),
            func.count(func.distinct(AssetSoftware.asset_id)).label("hosts"),
            func.count(func.distinct(AssetSoftware.version)).label("version_count"),
        ),
        filters,
    ).group_by(*KEY)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    col = GROUP_SORTS.get(sort.lstrip("-"), GROUP_SORTS["hosts"])
    order = col.desc() if sort.startswith("-") else col.asc()
    groups = db.execute(
        stmt.order_by(order, literal_column("name"), *KEY).offset((page - 1) * page_size).limit(page_size)
    ).all()

    versions: dict[tuple[str, str], list[VersionCount]] = {}
    if groups:
        rows = db.execute(
            _filtered(
                base_query(
                    user,
                    *KEY,
                    AssetSoftware.version,
                    func.count(func.distinct(AssetSoftware.asset_id)).label("hosts"),
                ),
                filters,
            )
            .where(tuple_(*KEY).in_([(g.vendor, g.product) for g in groups]))
            .group_by(*KEY, AssetSoftware.version)
            .order_by(func.max(AssetSoftware.version_key).desc())
        )
        for r in rows:
            bucket = versions.setdefault((r.vendor, r.product), [])
            if len(bucket) < MAX_VERSIONS_PER_GROUP:
                bucket.append(VersionCount(version=r.version, hosts=r.hosts))

    return Page(
        items=[
            SoftwareGroup(
                category=g.category,
                vendor=g.vendor,
                product=g.product,
                name=g.name,
                cpe=f"cpe:/{g.category[0] if g.category in ('os', 'hardware') else 'a'}:{g.vendor}:{g.product}"
                if g.vendor
                else "",
                hosts=g.hosts,
                version_count=g.version_count,
                versions=versions.get((g.vendor, g.product), []),
            )
            for g in groups
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/instances", response_model=Page[SoftwareInstance])
def list_instances(
    user: Reader,
    db: DB,
    filters: SoftwareQuery,
    sort: str = "name",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Page[SoftwareInstance]:
    """Every (asset, software, version) row matching the filters: which host runs what."""
    _filtered(select(AssetSoftware.id), filters)
    stmt = instance_query(user, filters, sort)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    return Page(
        items=[SoftwareInstance.model_validate(r._asdict()) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/export")
def export_software(
    request: Request,
    user: Reader,
    db: DB,
    filters: SoftwareQuery,
    format: Literal["csv", "xlsx"] = "csv",
) -> StreamingResponse:
    _filtered(select(AssetSoftware.id), filters)  # validate before streaming starts
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    audit(
        db,
        "software.exported",
        request=request,
        user=user,
        details={"format": format, **filters.model_dump(exclude_none=True, mode="json")},
    )
    db.commit()

    if format == "csv":
        user_id = user.id

        def stream() -> Iterator[str]:
            # Own session: the request-scoped one may close before streaming ends
            with SessionLocal() as session:
                owner = session.get(User, user_id)
                assert owner is not None
                buf = io.StringIO()
                writer = csv.writer(buf)
                for row in export_rows(session, owner, filters):
                    writer.writerow([safe_cell(v) for v in row])
                    yield buf.getvalue()
                    buf.seek(0)
                    buf.truncate()

        return StreamingResponse(
            stream(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="software-{stamp}.csv"'},
        )

    data = rows_to_xlsx("Software", export_rows(db, user, filters))
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="software-{stamp}.xlsx"'},
    )


@router.post("/rebuild", status_code=202)
def rebuild_software(request: Request, user: Admin, db: DB) -> dict[str, str]:
    """Re-derive the inventory from stored findings, e.g. after upgrading."""
    from app.workers.tasks import rebuild_software_task

    audit(db, "software.rebuild_requested", request=request, user=user)
    db.commit()
    rebuild_software_task.delay()
    return {"status": "queued"}
