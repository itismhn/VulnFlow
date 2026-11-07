from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


# Postgres accepts at most 65,535 bind parameters per statement; stay well below
_MAX_BIND_PARAMS = 30_000


def chunked[T: Mapping[str, Any]](rows: Sequence[T]) -> Iterator[Sequence[T]]:
    """Split rows for a multi-row INSERT so each statement fits the parameter limit."""
    if not rows:
        return
    size = max(1, _MAX_BIND_PARAMS // max(1, len(rows[0])))
    for start in range(0, len(rows), size):
        yield rows[start : start + size]
