import mimetypes
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.audit import audit
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import ReportJob, ReportTemplate, User
from app.models.enums import JobStatus, Role
from app.schemas.common import Page
from app.schemas.report import (
    ReportCreate,
    ReportOut,
    ReportPreview,
    TemplateConfig,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
)
from app.services.reporting.assets import MAX_UPLOAD, asset_path, store_asset, validate_assets
from app.services.reporting.engine import build_context, render_html
from app.workers.tasks import generate_report_task

router = APIRouter(tags=["reports"])

Reporter = Annotated[User, Depends(require(Perm.REPORTS_CREATE))]
TemplateManager = Annotated[User, Depends(require(Perm.TEMPLATES_MANAGE))]


def _validate_config(config: TemplateConfig) -> None:
    try:
        validate_assets(config)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/report-assets", status_code=201)
async def upload_report_asset(file: UploadFile, request: Request, user: TemplateManager, db: DB) -> dict:
    data = await file.read(MAX_UPLOAD + 1)
    try:
        asset = store_asset(data, file.filename or "upload")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    audit(
        db,
        "report_asset.uploaded",
        request=request,
        user=user,
        entity_type="report_asset",
        entity_id=asset["id"].split(".")[0],
        details={"asset": asset["id"], "filename": asset["filename"]},
    )
    db.commit()
    return asset


@router.get("/report-assets/{asset_id}")
def get_report_asset(asset_id: str, _: Reporter) -> FileResponse:
    try:
        path = asset_path(asset_id)
    except ValueError as exc:
        raise HTTPException(404, "Asset not found") from exc
    if not path.is_file():
        raise HTTPException(404, "Asset not found")
    return FileResponse(path)


@router.post("/report-preview")
def preview_report(body: ReportPreview, user: Reporter, db: DB, format: str = "html") -> Response:
    _validate_config(body.config)
    job = ReportJob(
        name=body.name,
        filters=body.config.filters.model_dump(mode="json", exclude_none=True),
        template_snapshot={"kind": body.kind, "config": body.config.model_dump(mode="json")},
    )
    ctx = build_context(db, job, user)
    if format == "pdf":
        try:
            from weasyprint import HTML

            return Response(HTML(string=render_html(ctx)).write_pdf(), media_type="application/pdf")
        except OSError as exc:
            raise HTTPException(422, "PDF rendering needs Pango on the server. Use HTML preview.") from exc
    if format != "html":
        raise HTTPException(422, "Manual templates support HTML or PDF preview")
    return Response(render_html(ctx), media_type="text/html")


# ---- Templates -------------------------------------------------------------


@router.get("/report-templates", response_model=list[TemplateOut])
def list_templates(_: Reporter, db: DB) -> list[ReportTemplate]:
    return list(
        db.scalars(select(ReportTemplate).order_by(ReportTemplate.builtin.desc(), ReportTemplate.name))
    )


def _get_template(db: DB, template_id: int) -> ReportTemplate:
    template = db.get(ReportTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found")
    return template


def _commit_unique(db: DB) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "A template with this name already exists") from exc


@router.post("/report-templates", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateCreate, request: Request, user: TemplateManager, db: DB) -> ReportTemplate:
    _validate_config(body.config)
    template = ReportTemplate(
        name=body.name,
        description=body.description,
        kind=body.kind,
        config=body.config.model_dump(mode="json"),
        created_by_id=user.id,
    )
    db.add(template)
    _commit_unique(db)
    audit(
        db,
        "template.created",
        request=request,
        user=user,
        entity_type="template",
        entity_id=template.id,
        details={"name": body.name},
    )
    db.commit()
    return template


@router.patch("/report-templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int, body: TemplateUpdate, request: Request, user: TemplateManager, db: DB
) -> ReportTemplate:
    template = _get_template(db, template_id)
    if template.builtin:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Built-in templates cannot be edited; duplicate it instead"
        )
    if body.name is not None:
        template.name = body.name
    if body.description is not None:
        template.description = body.description
    if body.config is not None:
        _validate_config(body.config)
        template.config = body.config.model_dump(mode="json")
    audit(db, "template.updated", request=request, user=user, entity_type="template", entity_id=template.id)
    _commit_unique(db)
    return template


@router.delete("/report-templates/{template_id}", status_code=204)
def delete_template(template_id: int, request: Request, user: TemplateManager, db: DB) -> None:
    template = _get_template(db, template_id)
    if template.builtin:
        raise HTTPException(status.HTTP_409_CONFLICT, "Built-in templates cannot be deleted")
    audit(
        db,
        "template.deleted",
        request=request,
        user=user,
        entity_type="template",
        entity_id=template.id,
        details={"name": template.name},
    )
    db.delete(template)
    db.commit()


# ---- Report jobs -----------------------------------------------------------


def _visible_reports(user: User) -> list:  # type: ignore[type-arg]
    # Admins see every report; others only their own (reports carry scoped data)
    return [] if user.role == Role.ADMIN else [ReportJob.created_by_id == user.id]


@router.get("/reports", response_model=Page[ReportOut])
def list_reports(
    user: Reporter,
    db: DB,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[ReportOut]:
    conds = _visible_reports(user)
    total = db.scalar(select(func.count()).select_from(ReportJob).where(*conds)) or 0
    rows = db.scalars(
        select(ReportJob)
        .where(*conds)
        .order_by(ReportJob.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return Page(
        items=[ReportOut.model_validate(r) for r in rows], total=total, page=page, page_size=page_size
    )


@router.post("/reports", response_model=ReportOut, status_code=201)
def create_report(body: ReportCreate, request: Request, user: Reporter, db: DB) -> ReportJob:
    template = _get_template(db, body.template_id)
    config = body.config or TemplateConfig.model_validate(template.config)
    _validate_config(config)
    filters = (body.filters if body.filters is not None else config.filters).model_dump(
        mode="json", exclude_none=True
    )
    job = ReportJob(
        name=body.name or template.name,
        template_id=template.id,
        format=body.format,
        filters=filters,
        template_snapshot={"kind": template.kind, "config": config.model_dump(mode="json")},
        created_by_id=user.id,
        status=JobStatus.QUEUED,
    )
    db.add(job)
    db.flush()
    audit(
        db,
        "report.requested",
        request=request,
        user=user,
        entity_type="report",
        entity_id=job.id,
        details={"template": template.name, "format": body.format},
    )
    db.commit()
    generate_report_task.delay(job.id)
    db.refresh(job)
    return job


def _get_report(db: DB, user: User, report_id: int) -> ReportJob:
    job = db.scalar(select(ReportJob).where(ReportJob.id == report_id, *_visible_reports(user)))
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    return job


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: int, user: Reporter, db: DB) -> ReportJob:
    return _get_report(db, user, report_id)


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, request: Request, user: Reporter, db: DB) -> FileResponse:
    job = _get_report(db, user, report_id)
    if job.status != JobStatus.DONE or not job.file_path or not Path(job.file_path).exists():
        raise HTTPException(status.HTTP_409_CONFLICT, "Report is not ready")
    audit(db, "report.downloaded", request=request, user=user, entity_type="report", entity_id=job.id)
    db.commit()
    safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "", job.name).strip() or "report"
    stamp = job.created_at.strftime("%Y%m%d")
    return FileResponse(
        job.file_path,
        media_type=mimetypes.guess_type(job.file_path)[0] or "application/octet-stream",
        filename=f"{safe_name}-{stamp}.{job.format}",
    )


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: int, request: Request, user: Reporter, db: DB) -> None:
    job = _get_report(db, user, report_id)
    if job.file_path:
        Path(job.file_path).unlink(missing_ok=True)
    audit(db, "report.deleted", request=request, user=user, entity_type="report", entity_id=job.id)
    db.delete(job)
    db.commit()
