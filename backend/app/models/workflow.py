"""Remediation workflow: SLAs, risk acceptance, suppression, saved views, notifications, settings."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CIDR, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.enums import AcceptanceStatus
from app.models.mixins import Timestamps
from app.models.user import User


class SlaPolicy(Timestamps, Base):
    """Remediation deadlines in days per severity. `zone=None` is the default policy."""

    __tablename__ = "sla_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone: Mapped[str | None] = mapped_column(String(64), unique=True)
    critical_days: Mapped[int] = mapped_column(Integer, default=15)
    high_days: Mapped[int] = mapped_column(Integer, default=30)
    medium_days: Mapped[int] = mapped_column(Integer, default=90)
    low_days: Mapped[int] = mapped_column(Integer, default=180)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def days_for(self, severity: int) -> int | None:
        return {4: self.critical_days, 3: self.high_days, 2: self.medium_days, 1: self.low_days}.get(severity)


class RiskAcceptance(Timestamps, Base):
    __tablename__ = "risk_acceptances"
    __table_args__ = (Index("ix_risk_acceptances_status_expires", "status", "expires_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default=AcceptanceStatus.PENDING)
    justification: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[date] = mapped_column(Date)
    # Status to restore when the acceptance ends
    previous_status: Mapped[str] = mapped_column(String(20))
    requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str] = mapped_column(Text, default="")

    requested_by: Mapped[User | None] = relationship(foreign_keys=[requested_by_id], lazy="joined")
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_id], lazy="joined")


class SuppressionRule(Timestamps, Base):
    """Marks a plugin as a false positive everywhere (optionally within a range / on a port)."""

    __tablename__ = "suppression_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    plugin_id: Mapped[int] = mapped_column(ForeignKey("plugins.id", ondelete="CASCADE"), index=True)
    cidr: Mapped[str | None] = mapped_column(CIDR)
    port: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    created_by: Mapped[User | None] = relationship(lazy="joined")


class SavedView(Timestamps, Base):
    __tablename__ = "saved_views"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_saved_views_owner_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    # Findings page search params (filters, group, sort)
    query: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    owner: Mapped[User] = relationship(lazy="joined")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_unread", "user_id", "read_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    link: Mapped[str] = mapped_column(String(512), default="")
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    actor: Mapped[User | None] = relationship(foreign_keys=[actor_id], lazy="joined")


class AppSetting(Base):
    """Runtime-editable settings (key/value)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
