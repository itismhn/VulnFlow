from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import AcceptanceStatus
from app.schemas.common import ORM, IPStr
from app.schemas.finding import FindingOut, UserBrief

Days = Field(ge=1, le=3650)


class SlaPolicyIn(BaseModel):
    zone: str | None = Field(default=None, max_length=64)
    critical_days: int = Days
    high_days: int = Days
    medium_days: int = Days
    low_days: int = Days
    enabled: bool = True


class SlaPolicyOut(ORM):
    id: int
    zone: str | None
    critical_days: int
    high_days: int
    medium_days: int
    low_days: int
    enabled: bool
    updated_at: datetime


class RiskRequestIn(BaseModel):
    finding_ids: list[int] = Field(min_length=1, max_length=1000)
    justification: str = Field(min_length=1, max_length=5000)
    expires_at: date


class RiskDecisionIn(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=5000)


class RiskRevokeIn(BaseModel):
    note: str = Field(default="", max_length=5000)


class RiskAcceptanceOut(ORM):
    id: int
    finding_id: int
    status: AcceptanceStatus
    justification: str
    expires_at: date
    previous_status: str
    requested_by: UserBrief | None
    decided_by: UserBrief | None
    decided_at: datetime | None
    decision_note: str
    created_at: datetime


class RiskAcceptanceRow(RiskAcceptanceOut):
    finding: FindingOut


class SuppressionIn(BaseModel):
    plugin_id: int
    cidr: str | None = Field(default=None, max_length=64)
    port: int | None = Field(default=None, ge=0, le=65535)
    reason: str = Field(min_length=1, max_length=2000)


class SuppressionUpdate(BaseModel):
    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    enabled: bool | None = None


class SuppressionOut(ORM):
    id: int
    plugin_id: int
    plugin_name: str = ""
    cidr: IPStr | None
    port: int | None
    reason: str
    enabled: bool
    created_by: UserBrief | None
    created_at: datetime
    matched: int = 0


class SavedViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    shared: bool = False
    query: dict[str, Any] = Field(default_factory=dict)


class SavedViewOut(ORM):
    id: int
    name: str
    shared: bool
    query: dict[str, Any]
    owner: UserBrief
    updated_at: datetime


class NotificationOut(ORM):
    id: int
    kind: str
    title: str
    body: str
    link: str
    actor: UserBrief | None
    read_at: datetime | None
    created_at: datetime


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread: int


class SettingsOut(BaseModel):
    risk_self_approval: bool
    risk_max_days: int
    audit_retention_days: int
    branding_company: str
    branding_classification: str


class SettingsUpdate(BaseModel):
    risk_self_approval: bool | None = None
    risk_max_days: int | None = Field(default=None, ge=1, le=3650)
    audit_retention_days: int | None = Field(default=None, ge=0, le=3650)
    branding_company: str | None = Field(default=None, max_length=128)
    branding_classification: str | None = Field(default=None, max_length=128)
