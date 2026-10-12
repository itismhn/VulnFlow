"""End-to-end API flow: upload -> explore -> networks -> reports."""

import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.models.enums import Role
from app.services.demo import NETWORKS, build_hosts, evolve, write_nessus
from tests.conftest import ApiClient, login, make_user

T0 = datetime(2026, 6, 1, 2, 0, tzinfo=UTC)


def upload(client: ApiClient, path: Path) -> dict:  # type: ignore[type-arg]
    with path.open("rb") as fh:
        r = client.post("/api/v1/scans/upload", files=[("files", (path.name, fh, "application/xml"))])
    assert r.status_code == 200, r.text
    return r.json()[0]


@pytest.fixture
def loaded(admin_client: ApiClient, tmp_path: Path) -> ApiClient:
    for name, cidr, zone, crit in NETWORKS:
        r = admin_client.post(
            "/api/v1/networks", json={"name": name, "cidr": cidr, "zone": zone, "criticality": crit}
        )
        assert r.status_code == 201, r.text
    hosts = build_hosts(per_network=4)
    upload(admin_client, write_nessus(tmp_path / "m1.nessus", hosts, T0))
    upload(
        admin_client,
        write_nessus(tmp_path / "m2.nessus", evolve(hosts, 1, fix_ratio=0.5), T0 + timedelta(days=30)),
    )
    return admin_client


def test_upload_and_scan_history(loaded: ApiClient, tmp_path: Path) -> None:
    scans = loaded.get("/api/v1/scans").json()
    assert scans["total"] == 2
    latest, first = scans["items"]
    assert latest["status"] == "done" and latest["progress"] == 100
    assert latest["host_count"] == 20 and latest["fixed_count"] > 0

    diff = loaded.get(f"/api/v1/scans/{latest['id']}/diff", params={"against": first["id"]}).json()
    assert diff["fixed"] == latest["fixed_count"]
    prev = loaded.get(f"/api/v1/scans/{latest['id']}/previous").json()
    assert prev["id"] == first["id"]
    hosts = loaded.get(f"/api/v1/scans/{latest['id']}/hosts").json()
    assert len(hosts) == 20

    # Same file again is rejected as a duplicate
    again = write_nessus(tmp_path / "dup.nessus", build_hosts(per_network=4), T0)
    result = upload(loaded, again)
    assert result["duplicate_of"] == first["id"]


def test_rejects_garbage_upload(admin_client: ApiClient) -> None:
    r = admin_client.post(
        "/api/v1/scans/upload", files=[("files", ("evil.nessus", io.BytesIO(b"<html/>"), "text/xml"))]
    )
    assert r.json()[0]["error"]


def test_findings_filters_and_groups(loaded: ApiClient) -> None:
    r = loaded.get("/api/v1/findings")
    assert r.status_code == 200, r.text
    all_open = r.json()
    assert all_open["total"] > 0
    assert all(f["severity"] > 0 for f in all_open["items"])

    core = loaded.get("/api/v1/findings", params={"ip": "10.10.0.0/24"}).json()
    assert core["total"] > 0
    assert all(f["asset"]["ip"].startswith("10.10.0.") for f in core["items"])

    crit = loaded.get("/api/v1/findings", params={"severity": [4]}).json()
    assert all(f["severity"] == 4 for f in crit["items"])

    by_net = loaded.get("/api/v1/findings/groups", params={"by": "network"}).json()
    assert {g["label"] for g in by_net["items"]} <= {n[0] for n in NETWORKS}
    assert sum(g["total"] for g in by_net["items"]) == all_open["total"]

    by_sev = loaded.get("/api/v1/findings/groups", params={"by": "severity"}).json()
    assert by_sev["items"][0]["label"] == "Critical"

    for by in ("host", "plugin", "zone", "status", "port"):
        assert loaded.get("/api/v1/findings/groups", params={"by": by}).status_code == 200

    fixed = loaded.get("/api/v1/findings", params={"status": ["fixed"]}).json()
    assert fixed["total"] > 0

    csv_resp = loaded.get("/api/v1/findings/export", params={"format": "csv", "severity": [4]})
    assert csv_resp.status_code == 200 and csv_resp.text.startswith("IP,Hostname")
    xlsx = loaded.get("/api/v1/findings/export", params={"format": "xlsx"})
    assert xlsx.content[:2] == b"PK"


def test_finding_detail_and_workflow(loaded: ApiClient) -> None:
    fid = loaded.get("/api/v1/findings").json()["items"][0]["id"]
    detail = loaded.get(f"/api/v1/findings/{fid}").json()
    assert detail["plugin"]["solution"] and detail["occurrences"]

    r = loaded.patch(f"/api/v1/findings/{fid}", json={"status": "false_positive"})
    assert r.status_code == 422  # justification required
    r = loaded.patch(f"/api/v1/findings/{fid}", json={"status": "in_progress", "note": "Patch scheduled"})
    assert r.json()["status"] == "in_progress"
    events = loaded.get(f"/api/v1/findings/{fid}").json()["events"]
    assert events[0]["to_status"] == "in_progress" and events[0]["note"] == "Patch scheduled"

    ids = [f["id"] for f in loaded.get("/api/v1/findings", params={"page_size": 5}).json()["items"]]
    me = loaded.get("/api/v1/auth/me").json()
    r = loaded.post(
        "/api/v1/findings/bulk", json={"ids": ids, "assignee_id": me["id"], "due_date": "2027-01-01"}
    )
    assert r.json()["updated"] == 5
    mine = loaded.get("/api/v1/findings", params={"assignee_id": me["id"]}).json()
    assert mine["total"] == 5


def test_assets_networks_vulns_dashboard(loaded: ApiClient) -> None:
    assets = loaded.get("/api/v1/assets").json()
    assert assets["total"] == 20
    top = assets["items"][0]
    assert top["network_name"] and top["risk_score"] >= assets["items"][-1]["risk_score"]
    assert loaded.get(f"/api/v1/assets/{top['id']}/scans").json()

    nets = loaded.get("/api/v1/networks").json()
    assert sum(n["asset_count"] for n in nets) == 20
    assert loaded.get("/api/v1/assets", params={"unassigned": True}).json()["total"] == 0

    vulns = loaded.get("/api/v1/vulnerabilities").json()
    assert vulns["items"][0]["severity"] == 4
    pid = vulns["items"][0]["plugin_id"]
    assert loaded.get(f"/api/v1/vulnerabilities/{pid}").json()["hosts"] >= 1

    dash = loaded.get("/api/v1/dashboard").json()
    assert dash["kpis"]["open"]["critical"] >= 0 and dash["kpis"]["assets"] == 20
    assert dash["trend"] and dash["top_hosts"] and dash["by_zone"]
    assert dash["kpis"]["fixed_30d"] >= 0

    hits = loaded.get("/api/v1/search", params={"q": "10.10.0"}).json()
    assert any(h["kind"] == "asset" for h in hits)

    r = loaded.post("/api/v1/networks", json={"name": "Dup", "cidr": "10.10.0.0/24"})
    assert r.status_code == 409


def test_network_csv_import(admin_client: ApiClient) -> None:
    csv_data = "name,cidr,zone,criticality\nCore,10.1.0.0/16,Core,5\nBad,not-a-cidr,,\n"
    r = admin_client.post("/api/v1/networks/import", files={"file": ("n.csv", csv_data, "text/csv")})
    body = r.json()
    assert body["created"] == 1 and len(body["errors"]) == 1


def test_scoped_user_isolation(loaded: ApiClient, client: ApiClient) -> None:
    nets = {n["name"]: n["id"] for n in loaded.get("/api/v1/networks").json()}
    r = loaded.post(
        "/api/v1/users",
        json={
            "username": "branch",
            "email": "branch@example.com",
            "role": "viewer",
            "password": "Sup3r-Secret-Pass!",
            "scope_restricted": True,
            "network_ids": [nets["Branch Network"]],
        },
    )
    assert r.status_code == 201
    loaded.post("/api/v1/auth/logout")

    from app.core.db import SessionLocal
    from app.models import User

    with SessionLocal() as s:
        u = s.query(User).filter_by(username="branch").one()
        u.must_change_password = False
        s.commit()
    login(client, "branch")

    findings = client.get("/api/v1/findings", params={"page_size": 500}).json()
    assert findings["total"] > 0
    assert all(f["asset"]["ip"].startswith("10.40.") for f in findings["items"])
    assets = client.get("/api/v1/assets").json()
    assert all(a["ip"].startswith("10.40.") for a in assets["items"])
    visible_nets = client.get("/api/v1/networks").json()
    assert [n["name"] for n in visible_nets] == ["Branch Network"]
    dash = client.get("/api/v1/dashboard").json()
    assert dash["kpis"]["assets"] == len(assets["items"])
    other = loaded  # same TestClient instance, now logged in as branch
    core_asset = client.get("/api/v1/findings", params={"ip": "10.10.0.0/24"}).json()
    assert core_asset["total"] == 0
    assert other is client

    # Scan summaries only count the user's own hosts and findings
    open_counts = dash["kpis"]["open"]
    scan = client.get("/api/v1/scans").json()["items"][0]
    assert scan["host_count"] == len(assets["items"])
    assert scan["critical_count"] == open_counts["critical"]
    assert scan["finding_count"] == sum(open_counts[k] for k in ("critical", "high", "medium", "low"))
    assert client.get(f"/api/v1/scans/{scan['id']}").json()["host_count"] == scan["host_count"]


@pytest.mark.parametrize("fmt", ["csv", "xlsx", "html", "pdf"])
def test_reports(loaded: ApiClient, fmt: str) -> None:
    if fmt == "pdf":
        try:
            import weasyprint  # noqa: F401
        except OSError:
            pytest.skip("WeasyPrint system libraries (pango) not installed")
    templates = loaded.get("/api/v1/report-templates").json()
    assert {t["kind"] for t in templates} == {"executive", "technical", "network"}
    for t in templates:
        r = loaded.post("/api/v1/reports", json={"template_id": t["id"], "format": fmt})
        assert r.status_code == 201
        job = loaded.get(f"/api/v1/reports/{r.json()['id']}").json()
        assert job["status"] == "done", job["error"]
        dl = loaded.get(f"/api/v1/reports/{job['id']}/download")
        assert dl.status_code == 200 and len(dl.content) > 200
        if fmt == "html":
            assert "CONFIDENTIAL" in dl.text


def test_custom_template_and_builtin_protection(loaded: ApiClient) -> None:
    builtin = loaded.get("/api/v1/report-templates").json()[0]
    assert loaded.delete(f"/api/v1/report-templates/{builtin['id']}").status_code == 409
    r = loaded.post(
        "/api/v1/report-templates",
        json={
            "name": "Core banking criticals",
            "kind": "technical",
            "config": {
                "sections": ["summary", "details"],
                "filters": {"severity": [4], "zone": ["Core Banking"]},
                "branding": {"company_name": "Example Bank", "primary_color": "#0f766e"},
            },
        },
    )
    assert r.status_code == 201
    job = loaded.post("/api/v1/reports", json={"template_id": r.json()["id"], "format": "html"}).json()
    html = loaded.get(f"/api/v1/reports/{job['id']}/download").text
    assert "Example Bank" in html and "Zones: Core Banking" in html


def test_delete_scan_reverts_auto_fix(loaded: ApiClient) -> None:
    latest = loaded.get("/api/v1/scans").json()["items"][0]
    assert latest["fixed_count"] > 0
    before = loaded.get("/api/v1/findings", params={"status": ["fixed"]}).json()["total"]
    assert before > 0
    assert loaded.delete(f"/api/v1/scans/{latest['id']}").status_code == 204
    after = loaded.get("/api/v1/findings", params={"status": ["fixed"]}).json()["total"]
    assert after == 0
    assert loaded.get("/api/v1/scans").json()["total"] == 1


def test_analyst_cannot_delete_scan(loaded: ApiClient, client: ApiClient) -> None:
    sid = loaded.get("/api/v1/scans").json()["items"][0]["id"]
    loaded.post("/api/v1/auth/logout")
    make_user("ann", Role.ANALYST)
    login(client, "ann")
    assert client.delete(f"/api/v1/scans/{sid}").status_code == 403
    assert client.patch(f"/api/v1/scans/{sid}", json={"notes": "checked"}).status_code == 200


def test_network_map(loaded: ApiClient) -> None:
    nets = {n["name"]: n for n in loaded.get("/api/v1/networks").json()}
    m = loaded.get(f"/api/v1/networks/{nets['Core Banking']['id']}/map").json()
    assert m["mode"] == "host" and len(m["cells"]) == 4
    assert all(c["address"].startswith("10.10.0.") for c in m["cells"])
    r = loaded.post("/api/v1/networks", json={"name": "All private", "cidr": "10.0.0.0/8"})
    blocks = loaded.get(f"/api/v1/networks/{r.json()['id']}/map").json()
    assert blocks["mode"] == "block" and {c["address"] for c in blocks["cells"]} >= {
        "10.10.0.0/24",
        "10.40.0.0/24",
    }
