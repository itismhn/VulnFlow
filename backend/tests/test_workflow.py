"""Phase 2 remediation workflow: SLAs, risk acceptance, suppression, views, notifications."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Finding, RiskAcceptance
from app.models.enums import FindingStatus, Role
from app.services.demo import NETWORKS, build_hosts, write_nessus
from app.services.risk import expire_due
from tests.conftest import ApiClient, login, make_user
from tests.test_api_flow import T0, upload


@pytest.fixture
def scanned(admin_client: ApiClient, tmp_path: Path) -> ApiClient:
    for name, cidr, zone, crit in NETWORKS:
        r = admin_client.post(
            "/api/v1/networks", json={"name": name, "cidr": cidr, "zone": zone, "criticality": crit}
        )
        assert r.status_code == 201, r.text
    upload(admin_client, write_nessus(tmp_path / "m1.nessus", build_hosts(per_network=3), T0))
    return admin_client


def first_finding(client: ApiClient, **params: object) -> dict:  # type: ignore[type-arg]
    items = client.get("/api/v1/findings", params={"sort": "-severity", **params}).json()["items"]
    assert items
    return items[0]


def test_sla_due_dates_follow_policy(scanned: ApiClient) -> None:
    f = first_finding(scanned, severity=4)
    first_seen = date.fromisoformat(f["first_seen"][:10])
    assert f["due_source"] == "sla"
    assert f["due_date"] == (first_seen + timedelta(days=15)).isoformat()

    policies = scanned.get("/api/v1/sla-policies").json()
    default = next(p for p in policies if p["zone"] is None)
    r = scanned.put(
        f"/api/v1/sla-policies/{default['id']}",
        json={**default, "critical_days": 7},
    )
    assert r.status_code == 200 and r.json()["recomputed"] > 0
    assert (
        scanned.get(f"/api/v1/findings/{f['id']}").json()["due_date"]
        == (first_seen + timedelta(days=7)).isoformat()
    )

    # A zone-specific policy wins over the default
    zone = scanned.get("/api/v1/networks/zones").json()[0]
    assert (
        scanned.post(
            "/api/v1/sla-policies",
            json={"zone": zone, "critical_days": 3, "high_days": 5, "medium_days": 10, "low_days": 20},
        ).status_code
        == 201
    )
    in_zone = first_finding(scanned, severity=4, zone=zone)
    seen = date.fromisoformat(in_zone["first_seen"][:10])
    assert in_zone["due_date"] == (seen + timedelta(days=3)).isoformat()

    # Manual dates are never overwritten by policy changes
    manual = (date.today() + timedelta(days=99)).isoformat()
    scanned.patch(f"/api/v1/findings/{f['id']}", json={"due_date": manual})
    scanned.put(f"/api/v1/sla-policies/{default['id']}", json={**default, "critical_days": 1})
    after = scanned.get(f"/api/v1/findings/{f['id']}").json()
    assert after["due_date"] == manual and after["due_source"] == "manual"

    # ...until handed back to the policy
    scanned.patch(f"/api/v1/findings/{f['id']}", json={"clear_due_date": True})
    assert scanned.get(f"/api/v1/findings/{f['id']}").json()["due_source"] in (None, "sla")
    assert scanned.delete(f"/api/v1/sla-policies/{default['id']}").status_code == 409


def test_risk_acceptance_needs_second_admin(scanned: ApiClient) -> None:
    make_user("boss", Role.ADMIN)
    f = first_finding(scanned)
    # The old shortcut is gone
    r = scanned.patch(f"/api/v1/findings/{f['id']}", json={"status": "risk_accepted", "note": "x"})
    assert r.status_code == 422

    expires = (date.today() + timedelta(days=30)).isoformat()
    r = scanned.post(
        "/api/v1/risk-acceptances",
        json={"finding_ids": [f["id"]], "justification": "Compensating WAF rule", "expires_at": expires},
    )
    assert r.status_code == 201, r.text
    dup = scanned.post(
        "/api/v1/risk-acceptances",
        json={"finding_ids": [f["id"]], "justification": "again", "expires_at": expires},
    )
    assert dup.status_code == 409
    ra = scanned.get("/api/v1/risk-acceptances", params={"status": "pending"}).json()["items"][0]

    # Requester cannot approve their own request by default
    r = scanned.post(f"/api/v1/risk-acceptances/{ra['id']}/decision", json={"approve": True})
    assert r.status_code == 403

    scanned.cookies.clear()
    login(scanned, "boss")
    assert scanned.get("/api/v1/notifications").json()["unread"] >= 1
    r = scanned.post(f"/api/v1/risk-acceptances/{ra['id']}/decision", json={"approve": True, "note": "ok"})
    assert r.status_code == 200, r.text
    detail = scanned.get(f"/api/v1/findings/{f['id']}").json()
    assert detail["status"] == "risk_accepted"

    # Expiry restores the previous status
    with SessionLocal() as db:
        assert expire_due(db, today=date.today() + timedelta(days=31)) == 1
        db.commit()
        finding = db.get(Finding, f["id"])
        assert finding is not None and finding.status == f["status"]
        ra_row = db.scalar(select(RiskAcceptance))
        assert ra_row is not None and ra_row.status == "expired"


def test_revoke_and_analyst_permissions(scanned: ApiClient) -> None:
    f = first_finding(scanned)
    make_user("ana", Role.ANALYST)
    make_user("viv", Role.VIEWER)
    scanned.cookies.clear()
    login(scanned, "viv")
    expires = (date.today() + timedelta(days=10)).isoformat()
    body = {"finding_ids": [f["id"]], "justification": "legacy", "expires_at": expires}
    assert scanned.post("/api/v1/risk-acceptances", json=body).status_code == 403

    scanned.cookies.clear()
    login(scanned, "ana")
    assert scanned.post("/api/v1/risk-acceptances", json=body).status_code == 201
    ra = scanned.get("/api/v1/risk-acceptances").json()["items"][0]
    assert (
        scanned.post(f"/api/v1/risk-acceptances/{ra['id']}/decision", json={"approve": True}).status_code
        == 403
    )

    scanned.cookies.clear()
    login(scanned, "admin")
    scanned.post(f"/api/v1/risk-acceptances/{ra['id']}/decision", json={"approve": True})
    r = scanned.post(f"/api/v1/risk-acceptances/{ra['id']}/revoke", json={"note": "WAF removed"})
    assert r.status_code == 200 and r.json()["status"] == "revoked"
    assert scanned.get(f"/api/v1/findings/{f['id']}").json()["status"] == f["status"]


def test_suppression_rule_marks_and_releases(scanned: ApiClient) -> None:
    f = first_finding(scanned)
    plugin_id = f["plugin"]["id"]
    before = scanned.get("/api/v1/findings", params={"plugin_id": plugin_id}).json()["total"]
    assert before > 0
    r = scanned.post("/api/v1/suppressions", json={"plugin_id": plugin_id, "reason": "Scanner bug"})
    assert r.status_code == 201, r.text
    rule = r.json()
    assert rule["matched"] == before
    assert scanned.get("/api/v1/findings", params={"plugin_id": plugin_id}).json()["total"] == 0

    assert scanned.delete(f"/api/v1/suppressions/{rule['id']}").status_code == 204
    assert scanned.get("/api/v1/findings", params={"plugin_id": plugin_id}).json()["total"] == before


def test_suppression_applies_at_import(scanned: ApiClient, tmp_path: Path) -> None:
    f = first_finding(scanned)
    plugin_id = f["plugin"]["id"]
    scanned.post("/api/v1/suppressions", json={"plugin_id": plugin_id, "reason": "Accepted design"})
    hosts = build_hosts(per_network=3)
    upload(scanned, write_nessus(tmp_path / "m2.nessus", hosts, T0 + timedelta(days=30)))
    with SessionLocal() as db:
        statuses = set(db.scalars(select(Finding.status).where(Finding.plugin_id == plugin_id)))
    assert statuses == {FindingStatus.FALSE_POSITIVE}


def test_mentions_and_assignment_notify(scanned: ApiClient) -> None:
    ana = make_user("ana", Role.ANALYST)
    f = first_finding(scanned)
    scanned.patch(f"/api/v1/findings/{f['id']}", json={"note": "@ana please check this"})
    scanned.patch(f"/api/v1/findings/{f['id']}", json={"assignee_id": ana.id})
    scanned.cookies.clear()
    login(scanned, "ana")
    notes = scanned.get("/api/v1/notifications").json()
    kinds = sorted(n["kind"] for n in notes["items"])
    assert kinds == ["assigned", "mention"] and notes["unread"] == 2
    scanned.post("/api/v1/notifications/read")
    assert scanned.get("/api/v1/notifications").json()["unread"] == 0


def test_mention_respects_scope(scanned: ApiClient) -> None:
    make_user("branch", Role.ANALYST, scope_restricted=True)
    f = first_finding(scanned)
    scanned.patch(f"/api/v1/findings/{f['id']}", json={"note": "fyi @branch"})
    scanned.cookies.clear()
    login(scanned, "branch")
    assert scanned.get("/api/v1/notifications").json()["unread"] == 0


def test_saved_views(scanned: ApiClient) -> None:
    r = scanned.post("/api/v1/views", json={"name": "Crit DMZ", "query": {"severity": [4]}, "shared": True})
    assert r.status_code == 201
    assert scanned.post("/api/v1/views", json={"name": "Crit DMZ"}).status_code == 409
    make_user("ana", Role.ANALYST)
    scanned.cookies.clear()
    login(scanned, "ana")
    views = scanned.get("/api/v1/views").json()
    assert [v["name"] for v in views] == ["Crit DMZ"]
    assert scanned.delete(f"/api/v1/views/{views[0]['id']}").status_code == 403


def test_scan_diff_findings_and_metrics(scanned: ApiClient, tmp_path: Path) -> None:
    from app.services.demo import evolve

    hosts = build_hosts(per_network=3)
    upload(
        scanned,
        write_nessus(tmp_path / "m2.nessus", evolve(hosts, 1, fix_ratio=0.5), T0 + timedelta(days=30)),
    )
    latest, first = scanned.get("/api/v1/scans").json()["items"]
    diff = scanned.get(f"/api/v1/scans/{latest['id']}/diff", params={"against": first["id"]}).json()
    fixed = scanned.get(
        f"/api/v1/scans/{latest['id']}/diff/findings", params={"against": first["id"], "kind": "fixed"}
    ).json()
    assert fixed["total"] == diff["fixed"] > 0

    m = scanned.get("/api/v1/metrics").json()
    assert len(m["velocity"]) == 12
    assert {r["key"] for r in m["sla_by_severity"]} <= {"critical", "high", "medium", "low"}


def test_settings_and_audit_export(scanned: ApiClient) -> None:
    r = scanned.put("/api/v1/settings", json={"risk_self_approval": True, "risk_max_days": 30})
    assert r.status_code == 200 and r.json()["risk_max_days"] == 30
    f = first_finding(scanned)
    too_far = (date.today() + timedelta(days=60)).isoformat()
    body = {"finding_ids": [f["id"]], "justification": "x", "expires_at": too_far}
    assert scanned.post("/api/v1/risk-acceptances", json=body).status_code == 422

    csv_text = scanned.get("/api/v1/audit/export").text
    assert csv_text.startswith("time,actor,action") and "settings.updated" in csv_text

    make_user("ana", Role.ANALYST)
    scanned.cookies.clear()
    login(scanned, "ana")
    assert scanned.put("/api/v1/settings", json={"risk_max_days": 5}).status_code == 403
