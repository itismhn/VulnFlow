import io
import json
import shutil
import tarfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.storage import scan_file_path
from app.models import AppSetting, AuditLog, Network, RefreshToken
from app.models.enums import Role
from app.services import backup
from tests.conftest import ApiClient, login, make_user

pytestmark = pytest.mark.skipif(
    shutil.which("pg_dump") is None and settings.pg_bin_dir is None, reason="no pg_dump"
)


@pytest.fixture(autouse=True)
def _empty_backup_dir() -> Iterator[None]:
    yield
    shutil.rmtree(settings.backup_path, ignore_errors=True)


def test_backup_api_flow(admin_client: ApiClient) -> None:
    admin_client.post("/api/v1/networks", json={"name": "Core", "cidr": "10.10.0.0/16"})
    scan_file_path("a" * 64).write_text("<NessusClientData_v2/>")

    assert admin_client.post("/api/v1/backups").status_code == 202  # runs inline in tests
    body = admin_client.get("/api/v1/backups").json()
    assert body["running_since"] is None
    assert body["last_run"]["ok"] is True
    [item] = body["items"]
    assert item["kind"] == "manual"
    assert item["counts"]["users"] == 1
    assert item["files"] >= 1  # storage is shared with other tests

    r = admin_client.get(f"/api/v1/backups/{item['name']}/download")
    assert r.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
        names = tar.getnames()
    assert names[0] == "manifest.json"
    assert "database.dump" in names
    assert f"storage/scans/{'a' * 64}.nessus" in names

    assert admin_client.get("/api/v1/backups/..%2F..%2Fetc%2Fpasswd/download").status_code == 404
    assert admin_client.delete(f"/api/v1/backups/{item['name']}").status_code == 204
    assert admin_client.get("/api/v1/backups").json()["items"] == []
    with SessionLocal() as s:
        actions = set(s.scalars(select(AuditLog.action)))
    assert {"backup.requested", "backup.created", "backup.downloaded", "backup.deleted"} <= actions


def test_backup_is_admin_only(client: ApiClient) -> None:
    make_user("ana", Role.ANALYST)
    login(client, "ana")
    assert client.get("/api/v1/backups").status_code == 403
    assert client.post("/api/v1/backups").status_code == 403


def test_second_backup_while_running_is_refused(admin_client: ApiClient) -> None:
    assert backup.acquire_lock()
    try:
        assert admin_client.post("/api/v1/backups").status_code == 409
        assert admin_client.get("/api/v1/backups").json()["running_since"] is not None
    finally:
        backup.release_lock()


def test_restore_replaces_data_and_files(admin_client: ApiClient) -> None:
    admin_client.post("/api/v1/networks", json={"name": "Core", "cidr": "10.10.0.0/16"})
    kept = scan_file_path("b" * 64)
    kept.write_text("original")
    with SessionLocal() as s:
        info = backup.create_backup(s)
    archive = settings.backup_path / info.name

    # Changes after the backup: all of them must be undone
    admin_client.post("/api/v1/networks", json={"name": "Later", "cidr": "10.20.0.0/16"})
    kept.unlink()
    scan_file_path("c" * 64).write_text("added later")
    admin_client.cookies.clear()

    manifest = backup.restore_backup(archive)

    assert manifest["counts"]["users"] == 1
    with SessionLocal() as s:
        assert [n.name for n in s.scalars(select(Network))] == ["Core"]
        assert s.scalar(select(RefreshToken.id).where(RefreshToken.revoked_at.is_(None))) is None
        assert s.scalar(select(AuditLog.id).where(AuditLog.action == "backup.restored"))
    assert kept.read_text() == "original"
    assert not scan_file_path("c" * 64).exists()


def test_restore_rejects_unsafe_archives(tmp_path) -> None:
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(bad, "w:gz") as tar:
        for name, data in (
            ("manifest.json", json.dumps({"format": 1, "db_revision": ""}).encode()),
            ("database.dump", b""),
            ("../../evil", b"x"),
        ):
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            tar.addfile(entry, io.BytesIO(data))
    with pytest.raises(backup.BackupError, match="Unexpected entry"):
        backup.restore_backup(bad, force=True)


def test_restore_refuses_backup_from_newer_version(tmp_path) -> None:
    newer = tmp_path / "newer.tar.gz"
    with tarfile.open(newer, "w:gz") as tar:
        data = json.dumps({"format": 1, "db_revision": "9999"}).encode()
        entry = tarfile.TarInfo("manifest.json")
        entry.size = len(data)
        tar.addfile(entry, io.BytesIO(data))
    with pytest.raises(backup.BackupError, match="newer VulnFlow"):
        backup.restore_backup(newer)


def test_schedule_and_retention() -> None:
    make_user()
    with SessionLocal() as s:
        assert not backup.scheduled_due(s)  # off by default
        s.add(AppSetting(key="backup_schedule", value="daily"))
        s.add(AppSetting(key="backup_keep", value=2))
        s.commit()
        assert backup.scheduled_due(s)

    with SessionLocal() as s:
        manual = backup.create_backup(s, "manual").name
    names = [backup.run_backup("scheduled").name for _ in range(3)]
    assert len(set(names)) == 3  # same-second runs don't overwrite each other

    remaining = [b.name for b in backup.list_backups()]
    # The oldest scheduled one is pruned; manual backups are never pruned
    assert sorted(remaining) == sorted([manual, *names[1:]])

    with SessionLocal() as s:
        assert not backup.scheduled_due(s)
        assert backup.scheduled_due(s, now=datetime.now(UTC) + timedelta(days=1))
