"""Finding lifecycle across a sequence of scans."""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Finding, FindingEvent, Scan
from app.models.enums import FindingStatus
from app.services.demo import CATALOG, DemoHost, write_nessus
from app.services.ingest import ingest_scan

T0 = datetime(2026, 6, 1, 2, 0, tzinfo=UTC)
V = {v.plugin_id: v for v in CATALOG}
SMB, RDP, TLS10, TELNET = V[97833], V[125313], V[104743], V[42263]


def host(ip: str, *vulns, kind: str = "windows") -> DemoHost:  # type: ignore[no-untyped-def]
    return DemoHost(
        ip=ip, hostname=f"h-{ip.split('.')[-1]}", os_kind=kind, os="Windows Server 2019", vulns=list(vulns)
    )


def import_scan(db: Session, tmp: Path, name: str, hosts: list[DemoHost], when: datetime, **kw) -> Scan:  # type: ignore[no-untyped-def]
    path = write_nessus(tmp / f"{name}.nessus", hosts, when, report_name=name, **kw)
    data = path.read_bytes()
    scan = Scan(
        name=path.name, filename=path.name, sha256=hashlib.sha256(data).hexdigest(), file_path=str(path)
    )
    db.add(scan)
    db.flush()
    ingest_scan(db, scan)
    db.commit()
    return scan


def status_of(db: Session, ip_last: str, plugin_id: int) -> str:
    rows = db.scalars(select(Finding).where(Finding.plugin_id == plugin_id)).unique().all()
    for f in rows:
        if str(f.asset.ip).endswith(f".{ip_last}"):
            return f.status
    return "missing"


def test_new_fixed_reopened(db: Session, tmp_path: Path) -> None:
    s1 = import_scan(db, tmp_path, "s1", [host("10.0.0.1", SMB, RDP), host("10.0.0.2", TLS10)], T0)
    assert s1.status == "done" and s1.host_count == 2
    assert s1.new_count == 3 and s1.fixed_count == 0
    assert s1.critical_count == 2 and s1.medium_count == 1

    # Month 2: RDP fixed on .1; .2 not scanned at all (its finding must stay open)
    s2 = import_scan(db, tmp_path, "s2", [host("10.0.0.1", SMB)], T0 + timedelta(days=30))
    assert s2.fixed_count == 1 and s2.new_count == 0
    assert status_of(db, "1", RDP.plugin_id) == FindingStatus.FIXED
    assert status_of(db, "1", SMB.plugin_id) == FindingStatus.OPEN
    assert status_of(db, "2", TLS10.plugin_id) == FindingStatus.OPEN

    # Month 3: RDP is back -> reopened
    s3 = import_scan(db, tmp_path, "s3", [host("10.0.0.1", SMB, RDP)], T0 + timedelta(days=60))
    assert s3.reopened_count == 1
    finding = db.scalars(select(Finding).where(Finding.plugin_id == RDP.plugin_id)).unique().one()
    assert finding.status == FindingStatus.REOPENED and finding.reopen_count == 1
    assert finding.fixed_at is None
    kinds = [
        e.to_status
        for e in db.scalars(
            select(FindingEvent).where(FindingEvent.finding_id == finding.id).order_by(FindingEvent.id)
        )
    ]
    assert kinds == ["open", "fixed", "reopened"]


def test_manual_statuses_are_preserved(db: Session, tmp_path: Path) -> None:
    import_scan(db, tmp_path, "a", [host("10.0.0.1", SMB, RDP)], T0)
    for f in db.scalars(select(Finding)).unique():
        f.status = (
            FindingStatus.RISK_ACCEPTED if f.plugin_id == SMB.plugin_id else FindingStatus.FALSE_POSITIVE
        )
    db.commit()
    import_scan(db, tmp_path, "b", [host("10.0.0.1")], T0 + timedelta(days=7))
    assert status_of(db, "1", SMB.plugin_id) == FindingStatus.RISK_ACCEPTED
    assert status_of(db, "1", RDP.plugin_id) == FindingStatus.FALSE_POSITIVE


def test_uncredentialed_scan_does_not_close_credentialed_findings(db: Session, tmp_path: Path) -> None:
    import_scan(db, tmp_path, "cred", [host("10.0.0.1", SMB)], T0, credentialed=True)
    s2 = import_scan(db, tmp_path, "nocred", [host("10.0.0.1")], T0 + timedelta(days=7), credentialed=False)
    assert s2.fixed_count == 0
    assert status_of(db, "1", SMB.plugin_id) == FindingStatus.OPEN


def test_out_of_order_import_does_not_close_or_bump(db: Session, tmp_path: Path) -> None:
    import_scan(db, tmp_path, "new", [host("10.0.0.1", SMB, RDP)], T0 + timedelta(days=30))
    old = import_scan(db, tmp_path, "old", [host("10.0.0.1", SMB, TLS10)], T0)
    assert old.fixed_count == 0
    smb = db.scalars(select(Finding).where(Finding.plugin_id == SMB.plugin_id)).unique().one()
    assert smb.first_seen == T0
    assert smb.last_seen == T0 + timedelta(days=30)
    assert status_of(db, "1", RDP.plugin_id) == FindingStatus.OPEN


def test_reingest_is_idempotent(db: Session, tmp_path: Path) -> None:
    scan = import_scan(db, tmp_path, "x", [host("10.0.0.1", SMB, RDP)], T0)
    ingest_scan(db, scan)
    db.commit()
    assert len(db.scalars(select(Finding)).unique().all()) == 2
    assert scan.host_count == 1 and scan.critical_count == 2


def test_new_and_reopened_in_same_batch(db: Session, tmp_path: Path) -> None:
    import_scan(db, tmp_path, "a", [host("10.0.0.1", SMB)], T0)
    import_scan(db, tmp_path, "b", [host("10.0.0.1")], T0 + timedelta(days=7))
    s3 = import_scan(db, tmp_path, "c", [host("10.0.0.1", SMB, RDP)], T0 + timedelta(days=14))
    assert s3.reopened_count == 1 and s3.new_count == 1
