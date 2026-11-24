"""Security-team regressions for partial rescans and lifecycle evidence."""

from datetime import timedelta
from pathlib import Path

import pytest
from lxml import etree
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import FindingEvent, FindingOccurrence
from app.models.enums import FindingStatus
from app.services.demo import write_nessus
from app.services.ingest import ingest_scan
from tests.conftest import ApiClient, login, make_user
from tests.test_api_flow import upload
from tests.test_lifecycle import RDP, SMB, T0, TLS10, host, import_scan


def finding(client: ApiClient, plugin_id: int) -> dict:
    items = client.get(
        "/api/v1/findings", params={"plugin_id": plugin_id, "status": [s.value for s in FindingStatus]}
    ).json()["items"]
    return next(f for f in items if f["plugin"]["id"] == plugin_id)


def test_partial_rescan_preserves_history_and_unscanned_hosts(
    admin_client: ApiClient, tmp_path: Path
) -> None:
    a = upload(
        admin_client,
        write_nessus(tmp_path / "a.nessus", [host("10.10.0.10", SMB, RDP), host("10.20.0.10", TLS10)], T0),
    )["scan_id"]
    original = finding(admin_client, RDP.plugin_id)
    outside_before = finding(admin_client, TLS10.plugin_id)
    b = upload(
        admin_client,
        write_nessus(tmp_path / "b.nessus", [host("10.10.0.10", SMB, TLS10)], T0 + timedelta(days=30)),
    )["scan_id"]
    fixed = finding(admin_client, RDP.plugin_id)
    assert fixed["id"] == original["id"] and fixed["status"] == "fixed"
    outside = admin_client.get("/api/v1/findings", params={"ip": "10.20.0.10"}).json()["items"]
    assert outside and all(
        f["status"] == "open" and f["last_seen"] == outside_before["last_seen"] for f in outside
    )
    diff = admin_client.get(f"/api/v1/scans/{b}/diff", params={"against": a}).json()
    assert (diff["new"], diff["fixed"], diff["persisting"]) == (1, 1, 1)
    upload(
        admin_client,
        write_nessus(tmp_path / "c.nessus", [host("10.10.0.10", SMB, RDP, TLS10)], T0 + timedelta(days=60)),
    )
    reopened = finding(admin_client, RDP.plugin_id)
    assert reopened["id"] == original["id"] and reopened["status"] == "reopened"
    assert reopened["reopen_count"] == 1 and reopened["first_seen"] == original["first_seen"]
    assert reopened["fixed_at"] is None


@pytest.mark.parametrize("protected", ["credentials", "family"])
def test_comparison_does_not_claim_protected_findings_fixed(
    admin_client: ApiClient, tmp_path: Path, protected: str
) -> None:
    a = upload(admin_client, write_nessus(tmp_path / "a.nessus", [host("10.0.0.1", SMB)], T0))["scan_id"]
    opts = {"credentialed": False} if protected == "credentials" else {"disabled_families": (SMB.family,)}
    b = upload(
        admin_client, write_nessus(tmp_path / "b.nessus", [host("10.0.0.1")], T0 + timedelta(days=7), **opts)
    )["scan_id"]
    assert finding(admin_client, SMB.plugin_id)["status"] == "open"
    assert admin_client.get(f"/api/v1/scans/{b}").json()["fixed_count"] == 0
    diff = admin_client.get(f"/api/v1/scans/{b}/diff", params={"against": a}).json()
    assert diff["fixed"] == 0
    assert diff["not_verified"] == 1
    unverified = admin_client.get(
        f"/api/v1/scans/{b}/diff/findings", params={"against": a, "kind": "not_verified"}
    ).json()
    assert unverified["total"] == 1 and unverified["items"][0]["status"] == "open"
    assert (
        admin_client.get(f"/api/v1/scans/{b}/diff/findings", params={"against": a, "kind": "fixed"}).json()[
            "total"
        ]
        == 0
    )


def test_reparse_does_not_duplicate_timeline(db: Session, tmp_path: Path) -> None:
    scan = import_scan(db, tmp_path, "baseline", [host("10.0.0.1", SMB)], T0)
    before = db.scalar(select(func.count()).select_from(FindingEvent))
    occurrences = db.scalar(select(func.count()).select_from(FindingOccurrence))
    ingest_scan(db, scan)
    db.commit()
    assert db.scalar(select(func.count()).select_from(FindingEvent)) == before
    assert db.scalar(select(func.count()).select_from(FindingOccurrence)) == occurrences


def test_delete_first_fix_keeps_later_clean_evidence(admin_client: ApiClient, tmp_path: Path) -> None:
    upload(admin_client, write_nessus(tmp_path / "a.nessus", [host("10.0.0.1", SMB)], T0))
    b = upload(admin_client, write_nessus(tmp_path / "b.nessus", [host("10.0.0.1")], T0 + timedelta(days=7)))[
        "scan_id"
    ]
    upload(admin_client, write_nessus(tmp_path / "c.nessus", [host("10.0.0.1")], T0 + timedelta(days=14)))
    assert admin_client.delete(f"/api/v1/scans/{b}").status_code == 204
    after = finding(admin_client, SMB.plugin_id)
    assert after["status"] == "fixed"
    assert after["fixed_at"].startswith((T0 + timedelta(days=14)).date().isoformat())


def test_delete_reopening_restores_fix_date(admin_client: ApiClient, tmp_path: Path) -> None:
    upload(admin_client, write_nessus(tmp_path / "a.nessus", [host("10.0.0.1", SMB)], T0))
    upload(admin_client, write_nessus(tmp_path / "b.nessus", [host("10.0.0.1")], T0 + timedelta(days=7)))
    c = upload(
        admin_client, write_nessus(tmp_path / "c.nessus", [host("10.0.0.1", SMB)], T0 + timedelta(days=14))
    )["scan_id"]
    assert admin_client.delete(f"/api/v1/scans/{c}").status_code == 204
    after = finding(admin_client, SMB.plugin_id)
    assert after["status"] == "fixed"
    assert after["fixed_at"] and after["fixed_at"].startswith((T0 + timedelta(days=7)).date().isoformat())
    assert after["reopen_count"] == 0


def test_late_parse_error_rolls_back_prior_batches(admin_client: ApiClient, tmp_path: Path) -> None:
    upload(admin_client, write_nessus(tmp_path / "a.nessus", [host("10.0.0.1", SMB)], T0))
    before = admin_client.get("/api/v1/findings").json()["total"]
    path = write_nessus(
        tmp_path / "broken.nessus",
        [host(f"10.2.{i // 250}.{i % 250 + 1}", SMB) for i in range(550)],
        T0 + timedelta(days=7),
    )
    path.write_bytes(path.read_bytes().replace(b"</NessusClientData_v2>", b""))
    sid = upload(admin_client, path)["scan_id"]
    assert admin_client.get(f"/api/v1/scans/{sid}").json()["status"] == "failed"
    assert admin_client.get("/api/v1/findings").json()["total"] == before
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(FindingOccurrence).where(FindingOccurrence.scan_id == sid)
            )
            == 0
        )


@pytest.mark.parametrize("days", [0, -7])
def test_comparison_requires_a_later_host_scan(admin_client: ApiClient, tmp_path: Path, days: int) -> None:
    a = upload(admin_client, write_nessus(tmp_path / "a.nessus", [host("10.0.0.1", SMB)], T0))["scan_id"]
    b = upload(
        admin_client, write_nessus(tmp_path / "b.nessus", [host("10.0.0.1")], T0 + timedelta(days=days))
    )["scan_id"]
    diff = admin_client.get(f"/api/v1/scans/{b}/diff", params={"against": a}).json()
    assert diff["fixed"] == 0 and diff["not_verified"] == 1
    assert finding(admin_client, SMB.plugin_id)["status"] == "open"


@pytest.mark.parametrize("missing", ["start", "end", "both", "reversed"])
def test_incomplete_host_dates_cannot_prove_a_fix(
    admin_client: ApiClient, tmp_path: Path, missing: str
) -> None:
    a = upload(admin_client, write_nessus(tmp_path / "a.nessus", [host("10.0.0.1", SMB)], T0))["scan_id"]
    path = write_nessus(tmp_path / "b.nessus", [host("10.0.0.1")], T0 + timedelta(days=7))
    tree = etree.parse(str(path))
    for tag in tree.xpath("//HostProperties/tag"):
        name = tag.get("name", "")
        remove_start = missing in ("start", "both") and name.startswith("HOST_START")
        remove_end = missing in ("end", "both") and name.startswith("HOST_END")
        if remove_start or remove_end:
            tag.getparent().remove(tag)
        elif missing == "reversed" and name == "HOST_END_TIMESTAMP":
            tag.text = str(int(T0.timestamp()))
    tree.write(str(path), encoding="UTF-8", xml_declaration=True)
    b = upload(admin_client, path)["scan_id"]
    scan = admin_client.get(f"/api/v1/scans/{b}").json()
    assert scan["status"] == "done" and scan["fixed_count"] == 0
    assert finding(admin_client, SMB.plugin_id)["status"] == "open"
    diff = admin_client.get(f"/api/v1/scans/{b}/diff", params={"against": a}).json()
    assert diff["fixed"] == 0 and diff["not_verified"] == 1


@pytest.mark.parametrize("manual_status", ["open", "in_progress", "fixed"])
def test_delete_scan_preserves_later_manual_status(
    admin_client: ApiClient, tmp_path: Path, manual_status: str
) -> None:
    upload(admin_client, write_nessus(tmp_path / "a.nessus", [host("10.0.0.1", SMB)], T0))
    b = upload(admin_client, write_nessus(tmp_path / "b.nessus", [host("10.0.0.1")], T0 + timedelta(days=7)))[
        "scan_id"
    ]
    f = finding(admin_client, SMB.plugin_id)
    for status in ["open", "in_progress", manual_status]:
        assert (
            admin_client.patch(
                f"/api/v1/findings/{f['id']}", json={"status": status, "note": "Manual investigation"}
            ).status_code
            == 200
        )
    before = finding(admin_client, SMB.plugin_id)
    assert admin_client.delete(f"/api/v1/scans/{b}").status_code == 204
    after = finding(admin_client, SMB.plugin_id)
    assert (after["status"], after["fixed_at"]) == (before["status"], before["fixed_at"])


def test_scoped_analyst_cannot_close_findings_outside_scope(admin_client: ApiClient, tmp_path: Path) -> None:
    from app.models import Network, User
    from app.models.enums import Role

    upload(admin_client, write_nessus(tmp_path / "a.nessus", [host("10.20.0.1", SMB)], T0))
    outside = finding(admin_client, SMB.plugin_id)
    network = admin_client.post("/api/v1/networks", json={"name": "Core", "cidr": "10.10.0.0/24"}).json()
    make_user("scoped", Role.ANALYST, scope_restricted=True)
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.username == "scoped"))
        u.networks = [db.get(Network, network["id"])]
        db.commit()
    admin_client.post("/api/v1/auth/logout")
    login(admin_client, "scoped")
    hidden = admin_client.get("/api/v1/dashboard").json()["kpis"]
    assert hidden["scans"] == 0 and hidden["last_scan_at"] is None
    result = upload(
        admin_client,
        write_nessus(
            tmp_path / "b.nessus", [host("10.10.0.1", SMB), host("10.20.0.1")], T0 + timedelta(days=7)
        ),
    )
    assert result["scan_id"] is None and result["error"]
    accepted = upload(
        admin_client,
        write_nessus(tmp_path / "allowed.nessus", [host("10.10.0.2", SMB)], T0 + timedelta(days=7)),
    )
    assert accepted["scan_id"] is not None and accepted["error"] is None
    assert admin_client.get(f"/api/v1/scans/{accepted['scan_id']}").json()["status"] == "done"
    assert admin_client.get("/api/v1/dashboard").json()["kpis"]["scans"] == 1
    admin_client.post("/api/v1/auth/logout")
    login(admin_client)
    assert admin_client.get(f"/api/v1/findings/{outside['id']}").json()["status"] == "open"
