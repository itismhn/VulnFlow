from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, CIDR, INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.mixins import Timestamps

user_networks = Table(
    "user_networks",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("network_id", ForeignKey("networks.id", ondelete="CASCADE"), primary_key=True),
)


class Network(Timestamps, Base):
    """A named IP range (CIDR) such as "Core Banking" or "Branch Tehran"."""

    __tablename__ = "networks"
    __table_args__ = (
        Index("ix_networks_cidr_gist", "cidr", postgresql_using="gist", postgresql_ops={"cidr": "inet_ops"}),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    cidr: Mapped[str] = mapped_column(CIDR, unique=True)
    zone: Mapped[str] = mapped_column(String(64), default="", index=True)
    criticality: Mapped[int] = mapped_column(Integer, default=3)
    owner: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")


class Asset(Timestamps, Base):
    __tablename__ = "assets"
    __table_args__ = (
        Index("ix_assets_ip_gist", "ip", postgresql_using="gist", postgresql_ops={"ip": "inet_ops"}),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(INET, unique=True)
    hostname: Mapped[str] = mapped_column(String(255), default="")
    fqdn: Mapped[str] = mapped_column(String(255), default="")
    netbios: Mapped[str] = mapped_column(String(128), default="")
    mac: Mapped[str] = mapped_column(String(255), default="")
    os: Mapped[str] = mapped_column(String(255), default="")
    # Overrides the network criticality when set
    criticality: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Most specific network containing `ip`; maintained by services.networks
    network_id: Mapped[int | None] = mapped_column(ForeignKey("networks.id", ondelete="SET NULL"), index=True)

    network: Mapped[Network | None] = relationship(lazy="joined")
