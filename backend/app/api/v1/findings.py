import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import String, cast, func, literal, select

from app.core.audit import audit
from app.core.db import SessionLocal
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import (
    Asset,
    Finding,
    FindingEvent,
    FindingOccurrence,
    Network,
    Plugin,
    Scan,
    ScanHost,
    User,
)
from app.models.enums import NotificationKind
from app.schemas.common import Page
from app.schemas.finding import (
    BulkUpdate,
    EventOut,
    FiltersQuery,
    FindingDetail,
    FindingGroup,
    FindingOut,
    FindingUpdate,
    GroupBy,
    OccurrenceOut,
)
from app.services.exporting import SEVERITY_LABELS, finding_rows
from app.services.finding_actions import update_finding
from app.services.findings_query import apply_filters, apply_sort, base_query, severity_counts_expr
from app.services.notifications import notify
from app.services.reporting.xlsx import rows_to_xlsx, safe_cell

router = APIRouter(prefix="/findings", tags=["findings"])

Reader = Annotated[User, Depends(require(Perm.FINDINGS_READ))]
Editor = Annotated[User, Depends(require(Perm.FINDINGS_UPDATE))]


@router.get("", response_model=Page[FindingOut])
def list_findings(
    user: Reader,
    db: DB,
    filters: FiltersQuery,
    sort: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Page[FindingOut]:
    stmt = apply_filters(base_query(user), filters)
    total = db.scalar(select(func.count()).select_from(stmt.with_only_columns(Finding.id).subquery())) or 0
    rows = db.scalars(apply_sort(stmt, sort).offset((page - 1) * page_size).limit(page_size)).unique()
    return Page(
        items=[FindingOut.model_validate(f) for f in rows], total=total, page=page, page_size=page_size
    )


def _group_columns(by: GroupBy) -> tuple[Any, Any, Any, list[Any]]:
    """(key, label, sublabel, group_by columns) for each grouping."""
    if by == "host":
        return (
            Asset.id,
            func.host(Asset.ip),
            func.coalesce(func.nullif(Asset.hostname, ""), Asset.fqdn),
            [Asset.id],
        )
    if by == "plugin":
        return Plugin.id, Plugin.name, Plugin.family, [Plugin.id]
    if by == "network":
        return (
            func.coalesce(Network.id, 0),
            func.coalesce(Network.name, "Unassigned"),
            func.coalesce(cast(Network.cidr, String), ""),
            [Network.id],
        )
    if by == "zone":
        zone = func.coalesce(func.nullif(Network.zone, ""), "Unzoned")
        return zone, zone, literal(""), [zone]
    if by == "severity":
        return Finding.severity, Finding.severity, literal(""), [Finding.severity]
    if by == "status":
        return Finding.status, Finding.status, literal(""), [Finding.status]
    port = func.concat(Finding.port, "/", Finding.protocol)
    return port, port, func.max(Finding.service), [Finding.port, Finding.protocol]


@router.get("/groups", response_model=Page[FindingGroup])
def group_findings(
    user: Reader,
    db: DB,
    filters: FiltersQuery,
    by: GroupBy = "host",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Page[FindingGroup]:
    key, label, sublabel, group_cols = _group_columns(by)
    counts = severity_counts_expr()
    total_col = func.count().label("total")
    max_sev = func.max(Finding.severity).label("max_severity")
    stmt = base_query(
        user, key.label("key"), label.label("label"), sublabel.label("sublabel"), total_col, max_sev, *counts
    )
    if by in ("network", "zone"):
        stmt = stmt.outerjoin(Network, Network.id == Asset.network_id)
    stmt = apply_filters(stmt, filters)
    # Non-key label columns are functionally dependent on the key, add them for Postgres
    extra = [label, sublabel] if by in ("host", "plugin", "network") else []
    stmt = stmt.group_by(*group_cols, *extra)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = [
        func.count().filter(Finding.severity == 4).desc(),
        func.count().filter(Finding.severity == 3).desc(),
        func.count().desc(),
    ]
    if by == "severity":
        order = [Finding.severity.desc()]
    rows = db.execute(stmt.order_by(*order).offset((page - 1) * page_size).limit(page_size))
    items = []
    for r in rows:
        lab = r.label
        if by == "severity":
            lab = SEVERITY_LABELS[int(lab)]
        items.append(
            FindingGroup(
                key=str(r.key),
                label=str(lab),
                sublabel=str(r.sublabel or ""),
                total=r.total,
                critical=r.critical,
                high=r.high,
                medium=r.medium,
                low=r.low,
                info=r.info,
                max_severity=r.max_severity or 0,
            )
        )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/export")
def export_findings(
    request: Request,
    user: Reader,
    db: DB,
    filters: FiltersQuery,
    sort: str | None = None,
    format: Literal["csv", "xlsx"] = "csv",
) -> StreamingResponse:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    audit(
        db,
        "findings.exported",
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
                for row in finding_rows(session, owner, filters, sort):
                    writer.writerow([safe_cell(v) for v in row])
                    yield buf.getvalue()
                    buf.seek(0)
                    buf.truncate()

        return StreamingResponse(
            stream(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="findings-{stamp}.csv"'},
        )

    data = rows_to_xlsx("Findings", finding_rows(db, user, filters, sort))
    return StreamingResponse(
        iter([data]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="findings-{stamp}.xlsx"'},
    )


def _get_finding(db: DB, user: User, finding_id: int) -> Finding:
    finding = db.scalar(base_query(user).where(Finding.id == finding_id))
    if finding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found")
    return finding


@router.get("/{finding_id}", response_model=FindingDetail)
def get_finding(finding_id: int, user: Reader, db: DB) -> FindingDetail:
    finding = _get_finding(db, user, finding_id)
    occurrences = db.execute(
        select(FindingOccurrence.scan_id, Scan.name, ScanHost.started_at, FindingOccurrence.severity)
        .join(Scan, Scan.id == FindingOccurrence.scan_id)
        .outerjoin(ScanHost, (ScanHost.scan_id == Scan.id) & (ScanHost.asset_id == finding.asset_id))
        .where(FindingOccurrence.finding_id == finding.id)
        .order_by(ScanHost.started_at.desc().nulls_last())
    )
    events = db.scalars(
        select(FindingEvent)
        .where(FindingEvent.finding_id == finding.id)
        .order_by(FindingEvent.created_at.desc(), FindingEvent.id.desc())
    )
    detail = FindingDetail.model_validate(
        {
            **FindingOut.model_validate(finding).model_dump(),
            "plugin": finding.plugin,
            "plugin_output": finding.plugin_output,
            "occurrences": [
                OccurrenceOut(scan_id=o[0], scan_name=o[1], observed_at=o[2], severity=o[3])
                for o in occurrences
            ],
            "events": [EventOut.model_validate(e) for e in events],
        }
    )
    return detail


@router.patch("/{finding_id}", response_model=FindingOut)
def patch_finding(finding_id: int, body: FindingUpdate, request: Request, user: Editor, db: DB) -> Finding:
    finding = _get_finding(db, user, finding_id)
    if update_finding(db, finding, body, user):
        audit(
            db,
            "finding.updated",
            request=request,
            user=user,
            entity_type="finding",
            entity_id=finding.id,
            details=body.model_dump(exclude_unset=True, mode="json"),
        )
        db.commit()
        db.refresh(finding)
    return finding


@router.post("/bulk", response_model=dict[str, int])
def bulk_update(body: BulkUpdate, request: Request, user: Editor, db: DB) -> dict[str, int]:
    findings = list(db.scalars(base_query(user).where(Finding.id.in_(body.ids))).unique())
    changed = sum(update_finding(db, f, body, user, notify_users=False) for f in findings)
    if changed and body.assignee_id and not body.clear_assignee:
        notify(
            db,
            [body.assignee_id],
            NotificationKind.ASSIGNED,
            f"{user.username} assigned {changed} findings to you",
            link="/my-work",
            actor=user,
        )
    audit(
        db,
        "finding.bulk_updated",
        request=request,
        user=user,
        entity_type="finding",
        details={"count": changed, **body.model_dump(exclude={"ids"}, exclude_unset=True, mode="json")},
    )
    db.commit()
    return {"updated": changed}
