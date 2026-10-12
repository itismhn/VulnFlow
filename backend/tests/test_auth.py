from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import REFRESH_COOKIE
from app.models import AuditLog
from app.models.enums import Role
from app.services.maintenance import purge_audit
from tests.conftest import PASSWORD, ApiClient, login, make_user


def test_login_me_logout(client: ApiClient) -> None:
    make_user()
    login(client)
    me = client.get("/api/v1/auth/me").json()
    assert me["username"] == "admin" and "users:manage" in me["permissions"]
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_and_lockout(client: ApiClient) -> None:
    make_user()
    for _ in range(settings.max_failed_logins):
        r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "nope"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": PASSWORD})
    assert r.status_code == 401 and "locked" in r.json()["detail"]


def test_unknown_user_same_error(client: ApiClient) -> None:
    r = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "x"})
    assert r.status_code == 401 and r.json()["detail"] == "Invalid username or password"


def test_csrf_required_for_cookie_writes(client: ApiClient) -> None:
    make_user()
    login(client)
    r = super(ApiClient, client).request("POST", "/api/v1/networks", json={"name": "x", "cidr": "10.0.0.0/8"})
    assert r.status_code == 403 and "CSRF" in r.json()["detail"]


def test_must_change_password_gate(client: ApiClient) -> None:
    make_user(must_change=True)
    login(client)
    assert client.get("/api/v1/scans").status_code == 403
    r = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "weak"},
    )
    assert r.status_code == 422
    r = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "An0ther-Strong-Pass!"},
    )
    assert r.status_code == 200 and r.json()["must_change_password"] is False
    assert client.get("/api/v1/scans").status_code == 200


def test_refresh_rotation_and_reuse_detection(client: ApiClient) -> None:
    make_user()
    login(client)
    old_refresh = client.cookies.get(REFRESH_COOKIE)
    assert client.post("/api/v1/auth/refresh").status_code == 200
    # Replaying the rotated token revokes every session
    client.cookies.set(REFRESH_COOKIE, old_refresh, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_admin_user_management(admin_client: ApiClient) -> None:
    r = admin_client.post(
        "/api/v1/users",
        json={"username": "ana", "email": "ana@example.com", "role": "analyst", "password": "short"},
    )
    assert r.status_code == 422
    r = admin_client.post(
        "/api/v1/users",
        json={"username": "ana", "email": "ana@example.com", "role": "analyst", "password": PASSWORD},
    )
    assert r.status_code == 201 and r.json()["must_change_password"] is True
    uid = r.json()["id"]
    assert admin_client.patch(f"/api/v1/users/{uid}", json={"role": "viewer"}).json()["role"] == "viewer"

    me = admin_client.get("/api/v1/auth/me").json()
    r = admin_client.patch(f"/api/v1/users/{me['id']}", json={"role": "analyst"})
    assert r.status_code == 409  # last admin
    audit = admin_client.get("/api/v1/audit").json()
    assert any(a["action"] == "user.created" for a in audit["items"])


def test_viewer_cannot_manage(client: ApiClient) -> None:
    make_user("val", Role.VIEWER)
    login(client, "val")
    assert client.get("/api/v1/users").status_code == 403
    assert client.post("/api/v1/networks", json={"name": "n", "cidr": "10.0.0.0/8"}).status_code == 403
    assert client.get("/api/v1/findings").status_code == 200


def test_audit_log_is_append_only_in_database(db: Session) -> None:
    db.add_all(
        [
            AuditLog(action="auth.login", created_at=datetime.now(UTC) - timedelta(days=800)),
            AuditLog(action="auth.login"),
        ]
    )
    db.commit()
    for stmt in (update(AuditLog).values(action="tampered"), delete(AuditLog)):
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(stmt)
        db.rollback()

    # Retention purge may still remove expired rows, and only those
    assert purge_audit(db) == 1
    db.commit()
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "auth.login")) == 1
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(delete(AuditLog))
    db.rollback()
