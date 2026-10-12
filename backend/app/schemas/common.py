from ipaddress import IPv4Address, IPv6Address
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict

T = TypeVar("T")


def _to_str(v: object) -> object:
    return str(v) if isinstance(v, IPv4Address | IPv6Address) or hasattr(v, "network_address") else v


# psycopg returns ipaddress objects for INET/CIDR columns
IPStr = Annotated[str, BeforeValidator(_to_str)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class SeverityCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0

    @classmethod
    def from_map(cls, counts: dict[int, int]) -> "SeverityCounts":
        return cls(
            critical=counts.get(4, 0),
            high=counts.get(3, 0),
            medium=counts.get(2, 0),
            low=counts.get(1, 0),
            info=counts.get(0, 0),
        )


class Message(BaseModel):
    detail: str
