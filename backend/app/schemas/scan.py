from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ScanStatus
from app.schemas.common import ORM, IPStr, SeverityCounts


class UserRef(ORM):
    id: int
    username: str


class ScanOut(ORM):
    id: int
    name: str
    filename: str
    size_bytes: int
    scanner: str
    policy_name: str
    started_at: datetime | None
    finished_at: datetime | None
    status: ScanStatus
    progress: int
    error: str
    host_count: int
    finding_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    info_count: int
    new_count: int
    fixed_count: int
    reopened_count: int
    skipped_hosts: int
    notes: str
    archived: bool
    created_at: datetime
    parsed_at: datetime | None
    uploaded_by: UserRef | None


class ScanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    notes: str | None = None
    archived: bool | None = None


class UploadResult(BaseModel):
    filename: str
    scan_id: int | None = None
    duplicate_of: int | None = None
    error: str | None = None


class ScanHostOut(BaseModel):
    asset_id: int
    ip: IPStr
    hostname: str
    os: str
    credentialed: bool
    started_at: datetime | None
    counts: SeverityCounts


class ScanDiff(BaseModel):
    base_scan_id: int
    compare_scan_id: int
    new: int
    fixed: int
    persisting: int
