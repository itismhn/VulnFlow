from app.core.db import SessionLocal
from app.models import Network, User
from app.models.enums import Role
from tests.conftest import ApiClient, login, make_user


def _net(client: ApiClient, name: str, cidr: str) -> int:
    r = client.post("/api/v1/networks", json={"name": name, "cidr": cidr})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_scoped_user_cannot_change_networks_outside_scope(admin_client: ApiClient) -> None:
    dmz = _net(admin_client, "DMZ", "10.30.0.0/16")
    core = _net(admin_client, "Core", "10.10.0.0/16")
    scoped = make_user("scoped", Role.ANALYST, scope_restricted=True)
    with SessionLocal() as s:
        s.get(User, scoped.id).networks = [s.get(Network, dmz)]
        s.commit()
    admin_client.cookies.clear()
    login(admin_client, "scoped")

    assert admin_client.patch(f"/api/v1/networks/{core}", json={"criticality": 1}).status_code == 404
    assert admin_client.delete(f"/api/v1/networks/{core}").status_code == 404
    assert admin_client.patch(f"/api/v1/networks/{dmz}", json={"criticality": 2}).status_code == 200
    assert admin_client.patch(f"/api/v1/networks/{dmz}", json={"cidr": "10.0.0.0/8"}).status_code == 403
    assert (
        admin_client.post("/api/v1/networks", json={"name": "X", "cidr": "10.99.0.0/16"}).status_code == 403
    )
    files = {"file": ("n.csv", b"name,cidr\nZ,10.50.0.0/16\n", "text/csv")}
    assert admin_client.post("/api/v1/networks/import", files=files).status_code == 403
    assert admin_client.delete(f"/api/v1/networks/{dmz}").status_code == 204


def test_network_names_are_unique(admin_client: ApiClient) -> None:
    a = _net(admin_client, "Core Banking", "10.10.0.0/16")
    r = admin_client.post("/api/v1/networks", json={"name": "core banking", "cidr": "10.99.0.0/16"})
    assert r.status_code == 409 and "name" in r.json()["detail"]
    b = _net(admin_client, "Other", "10.20.0.0/16")
    assert admin_client.patch(f"/api/v1/networks/{b}", json={"name": "CORE BANKING"}).status_code == 409
    assert (
        admin_client.patch(f"/api/v1/networks/{a}", json={"name": "Core Banking", "zone": "Core"}).status_code
        == 200
    )
    files = {"file": ("n.csv", b"name,cidr\nCore Banking,10.77.0.0/16\n", "text/csv")}
    assert admin_client.post("/api/v1/networks/import", files=files).json()["errors"]


def test_logout_requires_csrf(client: ApiClient) -> None:
    make_user()
    login(client)
    r = super(ApiClient, client).request("POST", "/api/v1/auth/logout")
    assert r.status_code == 403
    assert client.post("/api/v1/auth/logout").status_code == 204


def test_audit_export_records_filters(admin_client: ApiClient) -> None:
    from sqlalchemy import select

    from app.models import AuditLog

    assert admin_client.get("/api/v1/audit/export", params={"action": "auth.login"}).status_code == 200
    with SessionLocal() as s:
        row = s.scalars(select(AuditLog).where(AuditLog.action == "audit.exported")).one()
        assert row.details == {"action": "auth.login"}
