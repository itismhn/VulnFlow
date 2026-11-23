from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import JobStatus, ReportFormat
from app.schemas.common import ORM
from app.schemas.finding import FindingFilters

TemplateKind = Literal["executive", "technical", "network"]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
AssetId = Annotated[str, Field(pattern=r"^[a-f0-9]{64}\.(png|jpg)$")]


class PageBlock(BaseModel):
    id: str = Field(max_length=64)
    type: Literal["text", "image"] = "text"
    text: str = Field(default="", max_length=20000)
    asset: AssetId | None = None
    x: float = Field(default=12, ge=0, le=95)
    y: float = Field(default=30, ge=0, le=95)
    width: float = Field(default=76, ge=5, le=100)
    font_size: int = Field(default=24, ge=8, le=96)
    color: Color = "#ffffff"
    bold: bool = False
    align: Literal["left", "center", "right"] = "left"


class OpeningPage(BaseModel):
    id: str = Field(max_length=64)
    background_color: Color = "#0f172a"
    background_asset: AssetId | None = None
    background_fit: Literal["cover", "contain"] = "cover"
    overlay: float = Field(default=0, ge=0, le=0.9)
    blocks: list[PageBlock] = Field(default_factory=list, max_length=40)


class ReportLayout(BaseModel):
    page_size: Literal["A4", "Letter"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    font: Literal["sans-serif", "serif", "monospace"] = "sans-serif"
    font_size: int = Field(default=10, ge=8, le=18)
    margin_mm: int = Field(default=18, ge=10, le=35)
    page_numbers: bool = True
    show_cover: bool = True


class CustomSection(BaseModel):
    id: str = Field(pattern=r"^custom_[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(default="Custom section", max_length=200)
    text: str = Field(default="", max_length=50000)
    page_break: bool = False


class Branding(BaseModel):
    company_name: str = ""
    classification: str = "CONFIDENTIAL - INTERNAL USE ONLY"
    primary_color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")
    footer_text: str = ""
    logo_asset: AssetId | None = None
    logo_width_mm: int = Field(default=35, ge=10, le=100)
    header_text: str = Field(default="", max_length=500)


class TemplateConfig(BaseModel):
    sections: list[str] = []
    filters: FindingFilters = FindingFilters()
    branding: Branding = Branding()
    intro: str = ""
    top_n: int = Field(default=10, ge=1, le=100)
    group_by: Literal["host", "plugin"] = "plugin"
    opening_pages: list[OpeningPage] = Field(default_factory=list, max_length=10)
    layout: ReportLayout = Field(default_factory=ReportLayout)
    section_titles: dict[str, str] = Field(default_factory=dict, max_length=40)
    page_breaks: list[str] = Field(default_factory=list, max_length=40)
    custom_sections: list[CustomSection] = Field(default_factory=list, max_length=30)
    summary_text: str = Field(default="", max_length=50000)
    recommendations_text: str = Field(default="", max_length=50000)

    @model_validator(mode="after")
    def validate_structure(self) -> "TemplateConfig":
        allowed = {
            "summary",
            "kpis",
            "charts",
            "top_vulns",
            "top_hosts",
            "zones",
            "recommendations",
            "details",
            "networks",
        }
        custom_ids = [s.id for s in self.custom_sections]
        if len(set(custom_ids)) != len(custom_ids):
            raise ValueError("Custom section IDs must be unique")
        if len(self.sections) != len(set(self.sections)) or not set(self.sections) <= allowed | set(
            custom_ids
        ):
            raise ValueError("Sections must be unique and refer to supported or custom sections")
        if not set(self.page_breaks) <= allowed | set(custom_ids):
            raise ValueError("Page breaks must refer to supported or custom sections")
        if len({p.id for p in self.opening_pages}) != len(self.opening_pages):
            raise ValueError("Opening page IDs must be unique")
        for page in self.opening_pages:
            if len({b.id for b in page.blocks}) != len(page.blocks):
                raise ValueError("Block IDs must be unique within a page")
        return self


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


class ReportPreview(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: TemplateKind
    config: TemplateConfig = Field(default_factory=TemplateConfig)


class ReportCreate(BaseModel):
    template_id: int
    format: ReportFormat = ReportFormat.PDF
    name: str | None = Field(default=None, max_length=255)
    filters: FindingFilters | None = None
    config: TemplateConfig | None = None


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
    format: str
    status: JobStatus
    error: str
    size_bytes: int
    filters: dict[str, Any]
    template: TemplateRef | None
    created_by: UserRef | None
    created_at: datetime
    finished_at: datetime | None
