import ipaddress
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORM, IPStr, SeverityCounts


def normalize_cidr(v: str) -> str:
    try:
        return str(ipaddress.ip_network(v.strip(), strict=False))
    except ValueError as exc:
        raise ValueError("Invalid CIDR, expected e.g. 10.10.0.0/24") from exc


class NetworkBase(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    cidr: str
    zone: str = Field(default="", max_length=64)
    criticality: int = Field(default=3, ge=1, le=5)
    owner: str = Field(default="", max_length=128)
    description: str = ""

    @field_validator("cidr")
    @classmethod
    def _cidr(cls, v: str) -> str:
        return normalize_cidr(v)


class NetworkCreate(NetworkBase):
    pass


class NetworkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    cidr: str | None = None
    zone: str | None = Field(default=None, max_length=64)
    criticality: int | None = Field(default=None, ge=1, le=5)
    owner: str | None = Field(default=None, max_length=128)
    description: str | None = None

    @field_validator("cidr")
    @classmethod
    def _cidr(cls, v: str | None) -> str | None:
        return normalize_cidr(v) if v else v


class NetworkOut(ORM):
    id: int
    name: str
    cidr: IPStr
    zone: str
    criticality: int
    owner: str
    description: str
    created_at: datetime


class NetworkStats(NetworkOut):
    asset_count: int
    open: SeverityCounts


class NetworkImportResult(BaseModel):
    created: int
    updated: int
    errors: list[str]


class AssetOut(ORM):
    id: int
    ip: IPStr
    hostname: str
    fqdn: str
    netbios: str
    mac: str
    os: str
    criticality: int | None
    tags: list[str]
    first_seen: datetime | None
    last_seen: datetime | None
    network_id: int | None


class AssetRow(AssetOut):
    network_name: str | None
    zone: str | None
    effective_criticality: int
    risk_score: float
    open: SeverityCounts


class AssetUpdate(BaseModel):
    criticality: int | None = Field(default=None, ge=1, le=5)
    clear_criticality: bool = False
    tags: list[str] | None = None


class AssetScanEntry(BaseModel):
    scan_id: int
    scan_name: str
    started_at: datetime | None
    credentialed: bool
    findings: SeverityCounts
