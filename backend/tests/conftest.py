import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

os.environ.setdefault("RM_DATABASE_URL", "postgresql+psycopg://localhost/rm_test")
os.environ["RM_TASK_ALWAYS_EAGER"] = "true"
os.environ["RM_STORAGE_DIR"] = tempfile.mkdtemp(prefix="rm-test-")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import Base, SessionLocal, engine
from app.core.security import CSRF_COOKIE, CSRF_HEADER, hash_password
from app.models import User
from app.models.enums import Role

PASSWORD = "Sup3r-Secret-Pass!"


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def make_user(
    username: str = "admin", role: Role = Role.ADMIN, must_change: bool = False, **extra: object
) -> User:
    with SessionLocal() as session:
        user = User(
            username=username,
            email=f"{username}@example.com",
            role=role,
            password_hash=hash_password(PASSWORD),
            must_change_password=must_change,
            **extra,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


class ApiClient(TestClient):
    """TestClient that echoes the CSRF cookie into the header like the SPA does."""

    def request(self, method, url, **kwargs):  # type: ignore[override]
        token = self.cookies.get(CSRF_COOKIE)
        if token:
            kwargs.setdefault("headers", {})
            kwargs["headers"] = {**(kwargs["headers"] or {}), CSRF_HEADER: token}
        return super().request(method, url, **kwargs)


@pytest.fixture
def client() -> Iterator[ApiClient]:
    from app.main import app

    with ApiClient(app) as c:
        yield c


def login(client: ApiClient, username: str = "admin", password: str = PASSWORD) -> None:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text


@pytest.fixture
def admin_client(client: ApiClient) -> ApiClient:
    make_user()
    login(client)
    return client


@pytest.fixture
def demo_dir(tmp_path: Path) -> Path:
    return tmp_path
