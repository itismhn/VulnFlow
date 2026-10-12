from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.enums import JobStatus, ReportFormat
from app.schemas.common import ORM
from app.schemas.finding import FindingFilters

TemplateKind = Literal["executive", "technical", "network"]


class Branding(BaseModel):
    company_name: str = ""
    classification: str = "CONFIDENTIAL - INTERNAL USE ONLY"
    primary_color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")
    footer_text: str = ""


class TemplateConfig(BaseModel):
    sections: list[str] = []
    filters: FindingFilters = FindingFilters()
    branding: Branding = Branding()
    intro: str = ""
    top_n: int = Field(default=10, ge=1, le=100)
    group_by: Literal["host", "plugin"] = "plugin"


class TemplateOut(ORM):
    id: int
    name: str
    description: str
    kind: TemplateKind
    builtin: bool
    config: dict[str, Any]
    created_at: datetime


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    kind: TemplateKind
    config: TemplateConfig = TemplateConfig()


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    config: TemplateConfig | None = None


class ReportCreate(BaseModel):
    template_id: int
    format: ReportFormat = ReportFormat.PDF
    name: str | None = Field(default=None, max_length=255)
    filters: FindingFilters | None = None


class UserRef(ORM):
    id: int
    username: str


class TemplateRef(ORM):
    id: int
    name: str
    kind: str


class ReportOut(ORM):
    id: int
    name: str
    format: ReportFormat
    status: JobStatus
    error: str
    size_bytes: int
    filters: dict[str, Any]
    template: TemplateRef | None
    created_by: UserRef | None
    created_at: datetime
    finished_at: datetime | None
