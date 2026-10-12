from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import JobStatus
from app.models.mixins import Timestamps
from app.models.user import User


class ReportTemplate(Timestamps, Base):
    __tablename__ = "report_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # executive | technical | network
    kind: Mapped[str] = mapped_column(String(32))
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    # sections, default filters, branding
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class ReportJob(Timestamps, Base):
    __tablename__ = "report_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("report_templates.id", ondelete="SET NULL"))
    format: Mapped[str] = mapped_column(String(8))
    filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED)
    error: Mapped[str] = mapped_column(Text, default="")
    file_path: Mapped[str] = mapped_column(String(512), default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    template: Mapped[ReportTemplate | None] = relationship(lazy="joined")
    created_by: Mapped[User | None] = relationship(lazy="joined")
