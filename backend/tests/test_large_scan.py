"""A scan large enough that one batch exceeds Postgres' 65,535 bind-parameter limit."""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Finding, FindingOccurrence, Scan
from app.services.ingest import ingest_scan

HOSTS = 120
PORTS = 80


def _write(path: Path, start: str) -> None:
    with path.open("w") as fh:
        fh.write('<?xml version="1.0" ?>\n<NessusClientData_v2><Report name="big">\n')
        for h in range(HOSTS):
            ip = f"10.1.{h // 250}.{h % 250 + 1}"
            fh.write(
                f'<ReportHost name="{ip}"><HostProperties>'
                f'<tag name="host-ip">{ip}</tag><tag name="HOST_START">{start}</tag>'
                "</HostProperties>"
            )
            for p in range(PORTS):
                fh.write(
                    f'<ReportItem port="{1000 + p}" svc_name="x" protocol="tcp" severity="2" '
                    f'pluginID="{10000 + p % 7}" pluginName="P{p % 7}" pluginFamily="General">'
                    "<plugin_output>out</plugin_output></ReportItem>"
                )
            fh.write("</ReportHost>\n")
        fh.write("</Report></NessusClientData_v2>\n")


def _ingest(db: Session, path: Path, name: str) -> Scan:
    scan = Scan(name=name, filename=name, sha256=name * 8, file_path=str(path), size_bytes=1)
    db.add(scan)
    db.flush()
    ingest_scan(db, scan)
    db.commit()
    return scan


def test_large_batch_imports(db: Session, tmp_path: Path) -> None:
    first = tmp_path / "a.nessus"
    _write(first, "Mon Jan  5 10:00:00 2026")
    _ingest(db, first, "a")
    assert db.scalar(select(func.count()).select_from(Finding)) == HOSTS * PORTS

    # A later scan with no findings on the same hosts fixes them all at once
    second = tmp_path / "b.nessus"
    with second.open("w") as fh:
        fh.write('<NessusClientData_v2><Report name="b">')
        for h in range(HOSTS):
            ip = f"10.1.{h // 250}.{h % 250 + 1}"
            fh.write(
                f'<ReportHost name="{ip}"><HostProperties><tag name="host-ip">{ip}</tag>'
                '<tag name="HOST_START">Mon Feb  2 10:00:00 2026</tag></HostProperties></ReportHost>'
            )
        fh.write("</Report></NessusClientData_v2>")
    scan = _ingest(db, second, "b")
    assert scan.fixed_count == HOSTS * PORTS
    assert db.scalar(select(func.count()).select_from(FindingOccurrence)) == HOSTS * PORTS
