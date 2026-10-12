import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.orm import aliased

from app.core.audit import audit
from app.core.config import settings
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.core.storage import scan_file_path, storage_path
from app.models import Asset, Finding, FindingEvent, FindingOccurrence, Scan, ScanHost, User
from app.models.enums import FindingEventKind, FindingStatus, ScanStatus
from app.schemas.common import Page, SeverityCounts
from app.schemas.finding import FindingOut
from app.schemas.scan import ScanDiff, ScanHostOut, ScanOut, ScanUpdate, UploadResult
from app.services.findings_query import apply_sort, base_query
from app.services.ingest import recompute_after_scan_delete
from app.services.parsers import ParseError, get_parser
from app.services.scoping import asset_scope_clause
from app.workers.tasks import ingest_scan_task

router = APIRouter(prefix="/scans", tags=["scans"])

Reader = Annotated[User, Depends(require(Perm.SCANS_READ))]
Uploader = Annotated[User, Depends(require(Perm.SCANS_UPLOAD))]
Manager = Annotated[User, Depends(require(Perm.SCANS_MANAGE))]

_CHUNK = 1024 * 1024


def _visible(user: User) -> list:  # type: ignore[type-arg]
    if not user.scope_restricted:
        return []
    return [
        exists(
            select(1)
            .select_from(ScanHost)
            .join(Asset, Asset.id == ScanHost.asset_id)
            .where(ScanHost.scan_id == Scan.id, asset_scope_clause(user))
        )
    ]


def _get_scan(db: DB, scan_id: int, user: User) -> Scan:
    scan = db.scalar(select(Scan).where(Scan.id == scan_id, *_visible(user)))
    if scan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scan not found")
    return scan


def _scan_out(db: DB, user: User, scans: list[Scan]) -> list[ScanOut]:
    """Serialize scans; a scope-restricted user gets counts for their own hosts only."""
    out = [ScanOut.model_validate(s) for s in scans]
    if not user.scope_restricted or not out:
        return out
    ids = [s.id for s in out]
    scope = asset_scope_clause(user)
    hosts = dict(
        db.execute(
            select(ScanHost.scan_id, func.count())
            .join(Asset, Asset.id == ScanHost.asset_id)
            .where(ScanHost.scan_id.in_(ids), scope)
            .group_by(ScanHost.scan_id)
        ).all()
    )
    severities: dict[int, dict[int, int]] = {}
    for sid, severity, n in db.execute(
        select(FindingOccurrence.scan_id, FindingOccurrence.severity, func.count())
        .join(Finding, Finding.id == FindingOccurrence.finding_id)
        .join(Asset, Asset.id == Finding.asset_id)
        .where(FindingOccurrence.scan_id.in_(ids), scope)
        .group_by(FindingOccurrence.scan_id, FindingOccurrence.severity)
    ):
        severities.setdefault(sid, {})[severity] = n
    # new / fixed / reopened mirror the events the import recorded for this scan
    changes: dict[int | None, dict[str, int]] = {}
    for event_scan, kind, to_status, n in db.execute(
        select(FindingEvent.scan_id, FindingEvent.kind, FindingEvent.to_status, func.count())
        .join(Finding, Finding.id == FindingEvent.finding_id)
        .join(Asset, Asset.id == Finding.asset_id)
        .where(
            FindingEvent.scan_id.in_(ids),
            FindingEvent.kind.in_([FindingEventKind.DETECTED, FindingEventKind.STATUS]),
            scope,
        )
        .group_by(FindingEvent.scan_id, FindingEvent.kind, FindingEvent.to_status)
    ):
        key = "new" if kind == FindingEventKind.DETECTED else to_status
        if key in ("new", FindingStatus.FIXED, FindingStatus.REOPENED):
            bucket = changes.setdefault(event_scan, {})
            bucket[key] = bucket.get(key, 0) + n
    for scan in out:
        sev = severities.get(scan.id, {})
        chg = changes.get(scan.id, {})
        scan.host_count = hosts.get(scan.id, 0)
        scan.info_count = sev.get(0, 0)
        scan.low_count = sev.get(1, 0)
        scan.medium_count = sev.get(2, 0)
        scan.high_count = sev.get(3, 0)
        scan.critical_count = sev.get(4, 0)
        scan.finding_count = sum(v for k, v in sev.items() if k > 0)
        scan.new_count = chg.get("new", 0)
        scan.fixed_count = chg.get(FindingStatus.FIXED, 0)
        scan.reopened_count = chg.get(FindingStatus.REOPENED, 0)
        scan.skipped_hosts = 0
    return out


@router.get("", response_model=Page[ScanOut])
def list_scans(
    user: Reader,
    db: DB,
    q: str | None = None,
    scan_status: Annotated[ScanStatus | None, Query(alias="status")] = None,
    archived: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
) -> Page[ScanOut]:
    conds = [Scan.archived.is_(archived), *_visible(user)]
    if q:
        conds.append(
            or_(Scan.name.ilike(f"%{q}%"), Scan.filename.ilike(f"%{q}%"), Scan.policy_name.ilike(f"%{q}%"))
        )
    if scan_status:
        conds.append(Scan.status == scan_status)
    total = db.scalar(select(func.count()).select_from(Scan).where(*conds)) or 0
    rows = db.scalars(
        select(Scan)
        .where(*conds)
        .order_by(Scan.started_at.desc().nulls_first(), Scan.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(items=_scan_out(db, user, list(rows)), total=total, page=page, page_size=page_size)


async def _save_upload(upload: UploadFile) -> tuple[Path, str, int]:
    limit = settings.max_upload_mb * 1024 * 1024
    digest = hashlib.sha256()
    size = 0
    tmp_dir = storage_path("tmp", "x").parent
    with tempfile.NamedTemporaryFile(dir=tmp_dir, delete=False, suffix=".upload") as tmp:
        while chunk := await upload.read(_CHUNK):
            size += len(chunk)
            if size > limit:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise ParseError(f"File exceeds the {settings.max_upload_mb} MB limit")
            digest.update(chunk)
            tmp.write(chunk)
    return Path(tmp.name), digest.hexdigest(), size


@router.post("/upload", response_model=list[UploadResult])
async def upload_scans(
    files: list[UploadFile], request: Request, user: Uploader, db: DB
) -> list[UploadResult]:
    results: list[UploadResult] = []
    for upload in files:
        name = Path(upload.filename or "scan.nessus").name[:255]
        if not name.lower().endswith((".nessus", ".xml")):
            results.append(UploadResult(filename=name, error="Only .nessus files are supported"))
            continue
        tmp: Path | None = None
        try:
            tmp, sha, size = await _save_upload(upload)
            get_parser(tmp)  # rejects non-Nessus content early
        except ParseError as exc:
            if tmp:
                tmp.unlink(missing_ok=True)
            results.append(UploadResult(filename=name, error=str(exc)))
            continue

        duplicate = db.scalar(select(Scan.id).where(Scan.sha256 == sha))
        if duplicate:
            tmp.unlink(missing_ok=True)
            results.append(
                UploadResult(filename=name, duplicate_of=duplicate, error="This file was already imported")
            )
            continue

        dest = scan_file_path(sha)
        shutil.move(tmp, dest)
        scan = Scan(
            name=name,
            filename=name,
            sha256=sha,
            file_path=str(dest),
            size_bytes=size,
            uploaded_by_id=user.id,
            status=ScanStatus.QUEUED,
        )
        db.add(scan)
        db.flush()
        audit(
            db,
            "scan.uploaded",
            request=request,
            user=user,
            entity_type="scan",
            entity_id=scan.id,
            details={"filename": name, "size": size},
        )
        db.commit()
        results.append(UploadResult(filename=name, scan_id=scan.id))
        ingest_scan_task.delay(scan.id)
    return results


@router.get("/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: int, user: Reader, db: DB) -> ScanOut:
    return _scan_out(db, user, [_get_scan(db, scan_id, user)])[0]


@router.patch("/{scan_id}", response_model=ScanOut)
def update_scan(scan_id: int, body: ScanUpdate, request: Request, user: Uploader, db: DB) -> ScanOut:
    scan = _get_scan(db, scan_id, user)
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(scan, key, value)
    audit(
        db, "scan.updated", request=request, user=user, entity_type="scan", entity_id=scan.id, details=changes
    )
    db.commit()
    return _scan_out(db, user, [scan])[0]


@router.post("/{scan_id}/reparse", response_model=ScanOut)
def reparse_scan(scan_id: int, request: Request, user: Manager, db: DB) -> ScanOut:
    scan = _get_scan(db, scan_id, user)
    if scan.status in (ScanStatus.QUEUED, ScanStatus.PARSING):
        raise HTTPException(status.HTTP_409_CONFLICT, "Scan is already being processed")
    scan.status = ScanStatus.QUEUED
    scan.progress = 0
    audit(db, "scan.reparse", request=request, user=user, entity_type="scan", entity_id=scan.id)
    db.commit()
    ingest_scan_task.delay(scan.id)
    db.refresh(scan)
    return _scan_out(db, user, [scan])[0]


@router.delete("/{scan_id}", status_code=204)
def delete_scan(scan_id: int, request: Request, user: Manager, db: DB) -> None:
    scan = _get_scan(db, scan_id, user)
    if scan.status == ScanStatus.PARSING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Scan is being processed")
    asset_ids = list(db.scalars(select(ScanHost.asset_id).where(ScanHost.scan_id == scan.id)))

    # Undo status changes this scan caused (auto-fix / reopen) before forgetting it
    db.execute(
        text(
            """
            UPDATE findings f SET status = e.from_status,
                fixed_at = CASE WHEN e.from_status = 'fixed' THEN f.fixed_at ELSE NULL END
            FROM finding_events e
            WHERE e.finding_id = f.id AND e.scan_id = :sid AND e.kind = :kind
              AND f.status = e.to_status AND e.from_status IS NOT NULL
            """
        ),
        {"sid": scan.id, "kind": FindingEventKind.STATUS.value},
    )
    file_path = Path(scan.file_path)
    audit(
        db,
        "scan.deleted",
        request=request,
        user=user,
        entity_type="scan",
        entity_id=scan.id,
        details={"name": scan.name},
    )
    db.delete(scan)
    db.flush()
    recompute_after_scan_delete(db, asset_ids)
    db.commit()
    file_path.unlink(missing_ok=True)


@router.get("/{scan_id}/download")
def download_scan(scan_id: int, request: Request, user: Manager, db: DB) -> FileResponse:
    scan = _get_scan(db, scan_id, user)
    audit(db, "scan.downloaded", request=request, user=user, entity_type="scan", entity_id=scan.id)
    db.commit()
    return FileResponse(scan.file_path, filename=scan.filename, media_type="application/xml")


@router.get("/{scan_id}/hosts", response_model=list[ScanHostOut])
def scan_hosts(scan_id: int, user: Reader, db: DB) -> list[ScanHostOut]:
    _get_scan(db, scan_id, user)
    counts = (
        select(
            Finding.asset_id,
            FindingOccurrence.severity,
            func.count().label("n"),
        )
        .join(Finding, Finding.id == FindingOccurrence.finding_id)
        .where(FindingOccurrence.scan_id == scan_id)
        .group_by(Finding.asset_id, FindingOccurrence.severity)
    )
    per_asset: dict[int, dict[int, int]] = {}
    for asset_id, sev, n in db.execute(counts):
        per_asset.setdefault(asset_id, {})[sev] = n

    stmt = (
        select(ScanHost, Asset)
        .join(Asset, Asset.id == ScanHost.asset_id)
        .where(ScanHost.scan_id == scan_id)
        .order_by(Asset.ip)
    )
    if user.scope_restricted:
        stmt = stmt.where(asset_scope_clause(user))
    out = []
    for sh, asset in db.execute(stmt):
        out.append(
            ScanHostOut(
                asset_id=asset.id,
                ip=asset.ip,
                hostname=asset.hostname or asset.fqdn,
                os=sh.os or asset.os,
                credentialed=sh.credentialed,
                started_at=sh.started_at,
                counts=SeverityCounts.from_map(per_asset.get(asset.id, {})),
            )
        )
    out.sort(key=lambda h: (-h.counts.critical, -h.counts.high, -h.counts.medium))
    return out


def _diff_sets(db: DB, user: User, scan_id: int, against: int) -> tuple[set[int], set[int]]:
    """Finding ids (info excluded) on hosts covered by both scans: (base, current)."""
    _get_scan(db, scan_id, user)
    _get_scan(db, against, user)
    sh_a, sh_b = aliased(ScanHost), aliased(ScanHost)
    common_assets = (
        select(sh_a.asset_id)
        .join(sh_b, and_(sh_b.asset_id == sh_a.asset_id, sh_b.scan_id == scan_id))
        .where(sh_a.scan_id == against)
    )

    def finding_ids(sid: int) -> set[int]:
        stmt = (
            select(FindingOccurrence.finding_id)
            .join(Finding, Finding.id == FindingOccurrence.finding_id)
            .join(Asset, Asset.id == Finding.asset_id)
            .where(
                FindingOccurrence.scan_id == sid,
                FindingOccurrence.severity > 0,
                Finding.asset_id.in_(common_assets),
            )
        )
        if user.scope_restricted:
            stmt = stmt.where(asset_scope_clause(user))
        return set(db.scalars(stmt))

    return finding_ids(against), finding_ids(scan_id)


@router.get("/{scan_id}/diff", response_model=ScanDiff)
def diff_scans(scan_id: int, user: Reader, db: DB, against: int) -> ScanDiff:
    """Compare findings on hosts covered by both scans (info severity excluded)."""
    base, current = _diff_sets(db, user, scan_id, against)
    return ScanDiff(
        base_scan_id=against,
        compare_scan_id=scan_id,
        new=len(current - base),
        fixed=len(base - current),
        persisting=len(base & current),
    )


@router.get("/{scan_id}/diff/findings", response_model=Page[FindingOut])
def diff_findings(
    scan_id: int,
    user: Reader,
    db: DB,
    against: int,
    kind: Literal["new", "fixed", "persisting"],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=500)] = 50,
) -> Page[FindingOut]:
    base, current = _diff_sets(db, user, scan_id, against)
    ids = {"new": current - base, "fixed": base - current, "persisting": base & current}[kind]
    if not ids:
        return Page(items=[], total=0, page=page, page_size=page_size)
    rows = db.scalars(
        apply_sort(base_query(user).where(Finding.id.in_(ids)), "-severity")
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique()
    return Page(
        items=[FindingOut.model_validate(f) for f in rows], total=len(ids), page=page, page_size=page_size
    )


@router.get("/{scan_id}/previous", response_model=ScanOut | None)
def previous_scan(scan_id: int, user: Reader, db: DB) -> ScanOut | None:
    """Most recent earlier scan that shares at least one host with this one."""
    scan = _get_scan(db, scan_id, user)
    if scan.started_at is None:
        return None
    sh_a, sh_b = aliased(ScanHost), aliased(ScanHost)
    previous = db.scalar(
        select(Scan)
        .where(
            Scan.id != scan.id,
            Scan.status == ScanStatus.DONE,
            Scan.started_at < scan.started_at,
            exists(
                select(1)
                .select_from(sh_a)
                .join(sh_b, sh_b.asset_id == sh_a.asset_id)
                .where(sh_a.scan_id == Scan.id, sh_b.scan_id == scan.id)
            ),
            *_visible(user),
        )
        .order_by(Scan.started_at.desc())
        .limit(1)
    )
    return _scan_out(db, user, [previous])[0] if previous else None
