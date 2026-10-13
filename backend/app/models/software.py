from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.asset import Asset


class AssetSoftware(Base):
    """One OS, application, package, or service version found on an asset.

    Derived from the asset's current informational findings by
    services.software and rebuilt whenever those change, so it is never
    edited directly.
    """

    __tablename__ = "asset_software"
    __table_args__ = (
        Index("ix_asset_software_product_version", "product", "version_key"),
        Index(
            "ix_asset_software_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"), index=True)
    plugin_id: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str] = mapped_column(String(255))
    vendor: Mapped[str] = mapped_column(String(128), default="")
    # Grouping key: CPE product, or the lowercased name when there is no CPE
    product: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(128), default="")
    # Byte-sortable form of `version`, for range filters such as "< 2.17.1"
    version_key: Mapped[str] = mapped_column(String(512, collation="C"), default="")
    cpe: Mapped[str] = mapped_column(String(512), default="")
    port: Mapped[int] = mapped_column(Integer, default=0)
    protocol: Mapped[str] = mapped_column(String(8), default="")
    path: Mapped[str] = mapped_column(String(512), default="")
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    asset: Mapped[Asset] = relationship(lazy="joined")
