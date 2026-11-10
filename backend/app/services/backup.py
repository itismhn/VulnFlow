"""Full backups: one .tar.gz with a database dump plus the uploaded scans and generated reports.

Archive layout:
    manifest.json           what is inside, app version, migration revision
    database.dump           pg_dump custom format
    storage/scans/...       uploaded .nessus files
    storage/reports/...     generated report files

Not included: the .env file (secret key, database password), which must be kept separately,
and Redis, which only holds the task queue.
"""

import io
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import settings

log = logging.getLogger(__name__)

FORMAT = 1
STORAGE_DIRS = ("scans", "reports")
NAME_RE = re.compile(r"^vulnflow-\d{8}-\d{6}-(manual|scheduled)\.tar\.gz$")
LOCK_NAME = ".backup.lock"
LAST_RUN_NAME = ".last-run.json"
# A lock older than this is left over from a crashed run
STALE_LOCK = timedelta(hours=12)


class BackupError(RuntimeError):
    """A problem with a message meant for the administrator."""


@dataclass
class BackupInfo:
    name: str
    kind: str
    size_bytes: int
    created_at: datetime
    manifest: dict[str, Any]


# --- Paths and locking ------------------------------------------------------------------


def backup_dir() -> Path:
    path = settings.backup_path
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def backup_file(name: str) -> Path:
    """Path of an existing backup; the strict name check stops path traversal."""
    if not NAME_RE.match(name):
        raise FileNotFoundError(name)
    path = backup_dir() / name
    if not path.is_file():
        raise FileNotFoundError(name)
    return path


def running_since() -> datetime | None:
    lock = backup_dir() / LOCK_NAME
    try:
        started = datetime.fromtimestamp(lock.stat().st_mtime, UTC)
    except FileNotFoundError:
        return None
    if datetime.now(UTC) - started > STALE_LOCK:
        lock.unlink(missing_ok=True)
        return None
    return started


def acquire_lock() -> bool:
    running_since()  # clears a stale lock
    try:
        fd = os.open(backup_dir() / LOCK_NAME, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return False
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


def release_lock() -> None:
    (backup_dir() / LOCK_NAME).unlink(missing_ok=True)


def last_run() -> dict[str, Any] | None:
    try:
        data: dict[str, Any] = json.loads((backup_dir() / LAST_RUN_NAME).read_text())
    except (FileNotFoundError, ValueError):
        return None
    return data


def _record_run(kind: str, ok: bool, name: str = "", error: str = "") -> None:
    data = {"kind": kind, "ok": ok, "name": name, "error": error, "at": datetime.now(UTC).isoformat()}
    (backup_dir() / LAST_RUN_NAME).write_text(json.dumps(data))


# --- PostgreSQL tools -------------------------------------------------------------------


def _pg_tool(name: str) -> str:
    if settings.pg_bin_dir:
        candidate = settings.pg_bin_dir / name
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        raise BackupError(f"{name} was not found. Install the PostgreSQL client tools or set RM_PG_BIN_DIR.")
    return found


def _pg_args() -> tuple[list[str], dict[str, str]]:
    """Connection arguments for pg_dump/pg_restore; the password goes in the environment, not argv."""
    url = make_url(settings.database_url)
    args = []
    if url.host:
        args += ["--host", url.host]
    if url.port:
        args += ["--port", str(url.port)]
    if url.username:
        args += ["--username", url.username]
    args += ["--dbname", url.database or ""]
    env = {**os.environ}
    if url.password:
        env["PGPASSWORD"] = str(url.password)
    return args, env


def _run(cmd: list[str], env: dict[str, str]) -> None:
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise BackupError(f"{Path(cmd[0]).name} failed: {' '.join(detail[-3:])[:1000]}")


def _db_revision(db: Session) -> str:
    try:
        return db.scalar(text("SELECT version_num FROM alembic_version")) or ""
    except Exception:  # tests build the schema without Alembic
        db.rollback()
        return ""


# --- Create -----------------------------------------------------------------------------


def _counts(db: Session) -> dict[str, int]:
    from app.models import Asset, Finding, ReportJob, Scan, User

    return {
        name: db.scalar(select(func.count()).select_from(model)) or 0
        for name, model in (
            ("users", User),
            ("scans", Scan),
            ("assets", Asset),
            ("findings", Finding),
            ("reports", ReportJob),
        )
    }


def create_backup(db: Session, kind: str = "manual") -> BackupInfo:
    """Write a backup archive. The caller holds the lock (see acquire_lock)."""
    if kind not in ("manual", "scheduled"):
        raise ValueError(kind)
    out_dir = backup_dir()
    now = datetime.now(UTC)
    # Names have one-second resolution; never overwrite an earlier archive
    while (out_dir / f"vulnflow-{now:%Y%m%d-%H%M%S}-{kind}.tar.gz").exists():
        now += timedelta(seconds=1)
    name = f"vulnflow-{now:%Y%m%d-%H%M%S}-{kind}.tar.gz"
    final = out_dir / name
    partial = out_dir / f".{name}.partial"
    dump = out_dir / f".{name}.dump"
    try:
        args, env = _pg_args()
        # -Z0: the archive is gzipped as a whole, compressing twice only costs time
        _run([_pg_tool("pg_dump"), "--format=custom", "-Z0", "--no-owner", "--file", str(dump), *args], env)

        storage = settings.storage_dir.resolve()
        files = [
            p
            for sub in STORAGE_DIRS
            if (storage / sub).is_dir()
            for p in sorted((storage / sub).iterdir())
            if p.is_file()
        ]
        manifest = {
            "format": FORMAT,
            "app": settings.app_name,
            "version": __version__,
            "created_at": now.isoformat(),
            "kind": kind,
            "db_revision": _db_revision(db),
            "counts": _counts(db),
            "files": len(files),
            "file_bytes": sum(p.stat().st_size for p in files),
        }
        raw = json.dumps(manifest, indent=2).encode()
        # Owner-only from the start: the archive holds password hashes and every finding
        fd = os.open(partial, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as fh, tarfile.open(fileobj=fh, mode="w:gz", compresslevel=6) as tar:
            # The manifest goes first so listing reads only the start of each archive
            entry = tarfile.TarInfo("manifest.json")
            entry.size = len(raw)
            entry.mtime = int(now.timestamp())
            tar.addfile(entry, io.BytesIO(raw))
            tar.add(dump, arcname="database.dump")
            for path in files:
                tar.add(path, arcname=f"storage/{path.parent.name}/{path.name}")
        partial.rename(final)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    finally:
        dump.unlink(missing_ok=True)
    return BackupInfo(name, kind, final.stat().st_size, now, manifest)


def run_backup(kind: str) -> BackupInfo:
    """Create a backup in its own session, record the outcome and apply retention. Lock held by caller."""
    from app.core.audit import audit
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        try:
            info = create_backup(db, kind)
        except Exception as exc:
            log.exception("Backup failed")
            message = str(exc) if isinstance(exc, BackupError) else "Backup failed, see the worker logs."
            _record_run(kind, ok=False, error=message)
            audit(db, "backup.failed", entity_type="backup", details={"kind": kind, "error": message})
            db.commit()
            raise
        removed = prune(db) if kind == "scheduled" else []
        _record_run(kind, ok=True, name=info.name)
        audit(
            db,
            "backup.created",
            entity_type="backup",
            entity_id=info.name,
            details={"kind": kind, "size_bytes": info.size_bytes, "pruned": removed},
        )
        db.commit()
    return info


def prune(db: Session) -> list[str]:
    """Delete the oldest scheduled backups beyond the configured count. Manual ones are kept."""
    from app.services.app_settings import get_setting

    keep = max(1, int(get_setting(db, "backup_keep")))
    scheduled = [b for b in list_backups() if b.kind == "scheduled"]
    removed = []
    for old in scheduled[keep:]:
        (backup_dir() / old.name).unlink(missing_ok=True)
        removed.append(old.name)
    return removed


def scheduled_due(db: Session, now: datetime | None = None) -> bool:
    from app.services.app_settings import get_setting

    schedule = get_setting(db, "backup_schedule")
    if schedule not in ("daily", "weekly"):
        return False
    latest = next((b for b in list_backups() if b.kind == "scheduled"), None)
    if latest is None:
        return True
    # Slack so a run a few minutes early the next day or week still counts as due
    interval = timedelta(hours=20) if schedule == "daily" else timedelta(days=6, hours=20)
    return (now or datetime.now(UTC)) - latest.created_at >= interval


# --- List -------------------------------------------------------------------------------


def read_manifest(path: Path) -> dict[str, Any]:
    with tarfile.open(path, "r:gz") as tar:
        member = tar.next()
        if member is None or member.name != "manifest.json":
            raise BackupError("Not a VulnFlow backup: manifest.json is missing")
        fh = tar.extractfile(member)
        if fh is None:
            raise BackupError("Not a VulnFlow backup: manifest.json is unreadable")
        data: dict[str, Any] = json.loads(fh.read())
    return data


def list_backups() -> list[BackupInfo]:
    """Newest first."""
    items = []
    for path in backup_dir().iterdir():
        match = NAME_RE.match(path.name)
        if not match or not path.is_file():
            continue
        try:
            manifest = read_manifest(path)
            created = datetime.fromisoformat(manifest["created_at"])
        except Exception:
            manifest = {"error": "unreadable"}
            created = datetime.fromtimestamp(path.stat().st_mtime, UTC)
        items.append(BackupInfo(path.name, match.group(1), path.stat().st_size, created, manifest))
    return sorted(items, key=lambda b: b.created_at, reverse=True)


# --- Restore ----------------------------------------------------------------------------


def _alembic_config() -> Any:
    from alembic.config import Config

    root = Path(__file__).resolve().parents[2]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def _check_revision(revision: str) -> None:
    if not revision:
        return
    from alembic.script import ScriptDirectory

    try:
        ScriptDirectory.from_config(_alembic_config()).get_revision(revision)
    except Exception as exc:
        raise BackupError(
            f"The backup is from a newer VulnFlow (database revision {revision}). Upgrade VulnFlow first."
        ) from exc


def _safe_members(tar: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = tar.getmembers()
    allowed = re.compile(r"^(manifest\.json|database\.dump|storage/(scans|reports)/[A-Za-z0-9._-]+)$")
    for m in members:
        if not m.isfile() or not allowed.match(m.name):
            raise BackupError(f"Unexpected entry in backup: {m.name!r}")
    if "database.dump" not in {m.name for m in members}:
        raise BackupError("The backup has no database dump")
    return members


def other_connections(db: Session) -> int:
    return (
        db.scalar(
            text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND pid <> pg_backend_pid() AND backend_type = 'client backend'"
            )
        )
        or 0
    )


def restore_backup(
    archive: Path, *, force: bool = False, say: Callable[[str], None] = log.info
) -> dict[str, Any]:
    """Replace the database and stored files with the archive's contents.

    Run it with the api and worker stopped. Everything currently in VulnFlow is replaced.
    """
    from app.core.audit import audit
    from app.core.db import SessionLocal, engine
    from app.core.storage import scan_file_path, storage_path

    manifest = read_manifest(archive)
    if manifest.get("format") != FORMAT:
        raise BackupError(f"Unsupported backup format {manifest.get('format')!r}")
    revision = str(manifest.get("db_revision") or "")
    _check_revision(revision)

    engine.dispose()
    with SessionLocal() as db:
        busy = other_connections(db)
    if busy and not force:
        raise BackupError(
            f"{busy} other connection(s) to the database are open. Stop the api and worker first, "
            "or pass --force."
        )

    storage = settings.storage_dir.resolve()
    storage.mkdir(parents=True, exist_ok=True)
    # Extract next to the live files so the final swap is a rename, not a copy
    with tempfile.TemporaryDirectory(dir=storage, prefix=".restore-") as tmp:
        work = Path(tmp)
        say("Unpacking archive…")
        with tarfile.open(archive, "r:gz") as tar:
            members = _safe_members(tar)
            tar.extractall(work, members=members, filter="data")

        say("Restoring database…")
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        engine.dispose()
        args, env = _pg_args()
        _run(
            [
                _pg_tool("pg_restore"),
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                *args,
                str(work / "database.dump"),
            ],
            env,
        )

        say("Restoring files…")
        for sub in STORAGE_DIRS:
            target = storage / sub
            if target.exists():
                shutil.rmtree(target)
            source = work / "storage" / sub
            if source.is_dir():
                source.rename(target)
            else:
                target.mkdir()

    if revision:
        from alembic import command

        say("Applying database migrations…")
        command.upgrade(_alembic_config(), "head")

    with SessionLocal() as db:
        # Paths are absolute; point them at this server's storage folder
        for scan_id, sha in db.execute(text("SELECT id, sha256 FROM scans")).all():
            db.execute(
                text("UPDATE scans SET file_path = :p WHERE id = :id"),
                {"p": str(scan_file_path(sha)), "id": scan_id},
            )
        for job_id, path in db.execute(
            text("SELECT id, file_path FROM report_jobs WHERE file_path <> ''")
        ).all():
            new = storage_path("reports", Path(path).name)
            db.execute(
                text("UPDATE report_jobs SET file_path = :p WHERE id = :id"), {"p": str(new), "id": job_id}
            )
        # Sessions from the backup's point in time are not trusted: everyone signs in again
        db.execute(text("UPDATE refresh_tokens SET revoked_at = now() WHERE revoked_at IS NULL"))
        audit(
            db,
            "backup.restored",
            entity_type="backup",
            entity_id=archive.name,
            details={"created_at": manifest.get("created_at"), "version": manifest.get("version")},
        )
        db.commit()
    return manifest
