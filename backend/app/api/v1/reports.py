import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.audit import audit
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import ReportJob, ReportTemplate, User
from app.models.enums import JobStatus, ReportFormat, Role
from app.schemas.common import Page
from app.schemas.report import (
    ReportCreate,
    ReportOut,
    TemplateCreate,
    TemplateOut,
    TemplateUpdate,
)
from app.workers.tasks import generate_report_task

router = APIRouter(tags=["reports"])

Reporter = Annotated[User, Depends(require(Perm.REPORTS_CREATE))]
TemplateManager = Annotated[User, Depends(require(Perm.TEMPLATES_MANAGE))]

MEDIA_TYPES = {
    ReportFormat.PDF: "application/pdf",
    ReportFormat.HTML: "text/html",
    ReportFormat.CSV: "text/csv",
    ReportFormat.XLSX: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


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
    filters = body.filters.model_dump(mode="json", exclude_none=True) if body.filters else {}
    job = ReportJob(
        name=body.name or template.name,
        template_id=template.id,
        format=body.format,
        filters=filters,
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
        media_type=MEDIA_TYPES[ReportFormat(job.format)],
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
