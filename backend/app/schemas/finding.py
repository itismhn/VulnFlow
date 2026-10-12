from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import Depends, Query
from pydantic import BaseModel, Field

from app.models.enums import FindingStatus
from app.schemas.common import ORM, IPStr


class FindingFilters(BaseModel):
    """Shared filter set used by the findings explorer, exports, and reports."""

    q: str | None = None
    severity: list[int] | None = None
    status: list[FindingStatus] | None = None
    ip: str | None = Field(default=None, description="Single IP or CIDR range")
    network_id: list[int] | None = None
    zone: list[str] | None = None
    asset_id: int | None = None
    plugin_id: list[int] | None = None
    family: str | None = None
    cve: str | None = None
    port: int | None = None
    exploitable: bool | None = None
    min_cvss: float | None = None
    min_vpr: float | None = None
    scan_id: int | None = None
    assignee_id: int | None = None
    overdue: bool | None = None
    older_than_days: int | None = None
    include_info: bool = False


class AssetRef(ORM):
    id: int
    ip: IPStr
    hostname: str
    fqdn: str
    os: str
    network_id: int | None


class PluginBrief(ORM):
    id: int
    name: str
    family: str
    cvss3_base: float | None
    vpr_score: float | None
    epss_score: float | None
    exploit_available: bool
    cves: list[str]


class PluginOut(PluginBrief):
    severity: int
    risk_factor: str
    synopsis: str
    description: str
    solution: str
    see_also: list[str]
    cvss2_base: float | None
    cvss2_vector: str
    cvss3_vector: str
    cvss4_base: float | None
    cvss4_vector: str
    cwes: list[str]
    exploit_frameworks: list[str]
    exploitability_ease: str
    publication_date: date | None
    patch_publication_date: date | None
    vuln_publication_date: date | None


class UserBrief(ORM):
    id: int
    username: str
    full_name: str


class FindingOut(ORM):
    id: int
    asset: AssetRef
    plugin: PluginBrief
    port: int
    protocol: str
    service: str
    severity: int
    status: FindingStatus
    first_seen: datetime
    last_seen: datetime
    fixed_at: datetime | None
    reopen_count: int
    assignee: UserBrief | None
    due_date: date | None
    due_source: str | None = None


class OccurrenceOut(BaseModel):
    scan_id: int
    scan_name: str
    observed_at: datetime | None
    severity: int


class EventOut(ORM):
    id: int
    kind: str
    from_status: str | None
    to_status: str | None
    note: str
    scan_id: int | None
    # For events caused by an import: the scan and when it ran (created_at is the import time)
    scan_name: str | None = None
    scan_at: datetime | None = None
    actor: UserBrief | None
    created_at: datetime


class FindingDetail(FindingOut):
    plugin: PluginOut  # type: ignore[assignment]
    plugin_output: str
    occurrences: list[OccurrenceOut]
    events: list[EventOut]


class FindingUpdate(BaseModel):
    status: FindingStatus | None = None
    assignee_id: int | None = None
    clear_assignee: bool = False
    due_date: date | None = None
    clear_due_date: bool = False
    note: str = Field(default="", max_length=5000)


class BulkUpdate(FindingUpdate):
    ids: list[int] = Field(min_length=1, max_length=5000)


GroupBy = Literal["host", "plugin", "network", "zone", "severity", "status", "port"]


class FindingGroup(BaseModel):
    key: str
    label: str
    sublabel: str = ""
    total: int
    critical: int
    high: int
    medium: int
    low: int
    info: int
    max_severity: int


def finding_filters(
    q: str | None = None,
    severity: Annotated[list[int] | None, Query()] = None,
    status: Annotated[list[FindingStatus] | None, Query()] = None,
    ip: Annotated[str | None, Query(description="Single IP or CIDR range")] = None,
    network_id: Annotated[list[int] | None, Query()] = None,
    zone: Annotated[list[str] | None, Query()] = None,
    asset_id: int | None = None,
    plugin_id: Annotated[list[int] | None, Query()] = None,
    family: str | None = None,
    cve: str | None = None,
    port: int | None = None,
    exploitable: bool | None = None,
    min_cvss: float | None = None,
    min_vpr: float | None = None,
    scan_id: int | None = None,
    assignee_id: int | None = None,
    overdue: bool | None = None,
    older_than_days: int | None = None,
    include_info: bool = False,
) -> FindingFilters:
    """FastAPI dependency: build FindingFilters from query parameters."""
    return FindingFilters(**{k: v for k, v in locals().items()})


FiltersQuery = Annotated[FindingFilters, Depends(finding_filters)]
