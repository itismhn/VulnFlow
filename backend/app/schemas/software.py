from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, Query
from pydantic import BaseModel, Field

from app.schemas.common import IPStr

Category = Literal["os", "application", "package", "service", "hardware"]


class SoftwareFilters(BaseModel):
    q: str | None = None
    category: list[Category] | None = None
    vendor: str | None = None
    product: str | None = None
    version: str | None = Field(
        default=None, description="Version expression: '19.3', '2.4.*', '<2.17.1', '>=2.0 <2.17.1'"
    )
    asset_id: int | None = None
    network_id: list[int] | None = None
    zone: list[str] | None = None
    ip: str | None = Field(default=None, description="Single IP or CIDR range")


def software_filters(
    q: str | None = None,
    category: Annotated[list[Category] | None, Query()] = None,
    vendor: str | None = None,
    product: str | None = None,
    version: str | None = None,
    asset_id: int | None = None,
    network_id: Annotated[list[int] | None, Query()] = None,
    zone: Annotated[list[str] | None, Query()] = None,
    ip: str | None = None,
) -> SoftwareFilters:
    return SoftwareFilters(**{k: v for k, v in locals().items()})


SoftwareQuery = Annotated[SoftwareFilters, Depends(software_filters)]


class VersionCount(BaseModel):
    version: str
    hosts: int


class SoftwareGroup(BaseModel):
    category: str
    vendor: str
    product: str
    name: str
    cpe: str
    hosts: int
    version_count: int
    versions: list[VersionCount]


class SoftwareInstance(BaseModel):
    id: int
    asset_id: int
    ip: IPStr
    hostname: str
    network_name: str | None
    zone: str | None
    category: str
    name: str
    vendor: str
    product: str
    version: str
    cpe: str
    port: int
    protocol: str
    path: str
    plugin_id: int | None
    finding_id: int | None
    first_seen: datetime | None
    last_seen: datetime | None


class SoftwareStats(BaseModel):
    products: int
    instances: int
    hosts: int
    by_category: dict[str, int]
