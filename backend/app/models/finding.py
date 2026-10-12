from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.asset import Asset
from app.models.enums import FindingStatus
from app.models.mixins import Timestamps
from app.models.user import User


class Plugin(Base):
    """Vulnerability definition (one Nessus plugin)."""

    __tablename__ = "plugins"
    __table_args__ = (
        Index(
            "ix_plugins_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(512))
    family: Mapped[str] = mapped_column(String(128), default="", index=True)
    severity: Mapped[int] = mapped_column(SmallInteger, default=0)
    risk_factor: Mapped[str] = mapped_column(String(16), default="")
    synopsis: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    solution: Mapped[str] = mapped_column(Text, default="")
    see_also: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    cvss2_base: Mapped[float | None] = mapped_column(Float)
    cvss2_vector: Mapped[str] = mapped_column(String(128), default="")
    cvss3_base: Mapped[float | None] = mapped_column(Float)
    cvss3_vector: Mapped[str] = mapped_column(String(128), default="")
    cvss4_base: Mapped[float | None] = mapped_column(Float)
    cvss4_vector: Mapped[str] = mapped_column(String(256), default="")
    vpr_score: Mapped[float | None] = mapped_column(Float)
    epss_score: Mapped[float | None] = mapped_column(Float)
    cves: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    cwes: Mapped[list[str]] = mapped_column(ARRAY(String(32)), default=list)
    exploit_available: Mapped[bool] = mapped_column(Boolean, default=False)
    exploit_frameworks: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    exploitability_ease: Mapped[str] = mapped_column(String(128), default="")
    publication_date: Mapped[date | None] = mapped_column(Date)
    patch_publication_date: Mapped[date | None] = mapped_column(Date)
    vuln_publication_date: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Finding(Timestamps, Base):
    """A vulnerability on one asset/port, tracked across scans."""

    __tablename__ = "findings"
    __table_args__ = (
        UniqueConstraint("asset_id", "plugin_id", "port", "protocol", name="uq_findings_identity"),
        Index("ix_findings_status_severity", "status", "severity"),
        Index("ix_findings_plugin_status", "plugin_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    plugin_id: Mapped[int] = mapped_column(ForeignKey("plugins.id"))
    port: Mapped[int] = mapped_column(Integer, default=0)
    protocol: Mapped[str] = mapped_column(String(8), default="tcp")
    service: Mapped[str] = mapped_column(String(64), default="")
    severity: Mapped[int] = mapped_column(SmallInteger, index=True)
    status: Mapped[str] = mapped_column(String(20), default=FindingStatus.OPEN)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fixed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopen_count: Mapped[int] = mapped_column(Integer, default=0)
    plugin_output: Mapped[str] = mapped_column(Text, default="")
    last_scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id", ondelete="SET NULL"))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    due_date: Mapped[date | None] = mapped_column(Date)

    asset: Mapped[Asset] = relationship(lazy="joined")
    plugin: Mapped[Plugin] = relationship(lazy="joined")
    assignee: Mapped[User | None] = relationship(lazy="joined")


class FindingOccurrence(Base):
    """A finding as observed in one particular scan."""

    __tablename__ = "finding_occurrences"
    __table_args__ = (UniqueConstraint("finding_id", "scan_id", name="uq_occurrence"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"))
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), index=True)
    severity: Mapped[int] = mapped_column(SmallInteger)
    plugin_output: Mapped[str] = mapped_column(Text, default="")


class FindingEvent(Base):
    """Timeline entry: detection, status change, assignment, or comment."""

    __tablename__ = "finding_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default="")
    scan_id: Mapped[int | None] = mapped_column(ForeignKey("scans.id", ondelete="SET NULL"))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    actor: Mapped[User | None] = relationship(lazy="joined")
