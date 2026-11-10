"""Full backups (database + stored files). Admin only: an archive holds everything, password hashes included."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.audit import audit
from app.core.config import settings
from app.core.deps import DB, require
from app.core.permissions import Perm
from app.models import User
from app.services import backup

router = APIRouter(tags=["backups"])
Admin = Annotated[User, Depends(require(Perm.SETTINGS_MANAGE))]


class BackupOut(BaseModel):
    name: str
    kind: str
    size_bytes: int
    created_at: datetime
    version: str | None = None
    counts: dict[str, int] = {}
    files: int | None = None


class BackupList(BaseModel):
    items: list[BackupOut]
    running_since: datetime | None
    last_run: dict[str, Any] | None
    directory: str


def _get(name: str) -> backup.BackupInfo:
    try:
        path = backup.backup_file(name)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup not found") from None
    return next(b for b in backup.list_backups() if b.name == path.name)


@router.get("/backups", response_model=BackupList)
def list_backups(_: Admin) -> BackupList:
    return BackupList(
        items=[
            BackupOut(
                name=b.name,
                kind=b.kind,
                size_bytes=b.size_bytes,
                created_at=b.created_at,
                version=b.manifest.get("version"),
                counts=b.manifest.get("counts", {}),
                files=b.manifest.get("files"),
            )
            for b in backup.list_backups()
        ],
        running_since=backup.running_since(),
        last_run=backup.last_run(),
        directory=str(settings.backup_path),
    )


@router.post("/backups", status_code=202)
def start_backup(request: Request, user: Admin, db: DB) -> dict[str, str]:
    from app.workers.tasks import create_backup_task

    if not backup.acquire_lock():
        raise HTTPException(status.HTTP_409_CONFLICT, "A backup is already running")
    audit(db, "backup.requested", request=request, user=user, entity_type="backup")
    db.commit()
    try:
        create_backup_task.delay("manual", locked=True)
    except Exception:
        backup.release_lock()
        raise
    return {"status": "queued"}


@router.get("/backups/{name}/download")
def download_backup(name: str, request: Request, user: Admin, db: DB) -> FileResponse:
    info = _get(name)
    audit(db, "backup.downloaded", request=request, user=user, entity_type="backup", entity_id=info.name)
    db.commit()
    return FileResponse(backup.backup_file(info.name), media_type="application/gzip", filename=info.name)


@router.delete("/backups/{name}", status_code=204)
def delete_backup(name: str, request: Request, user: Admin, db: DB) -> None:
    info = _get(name)
    backup.backup_file(info.name).unlink(missing_ok=True)
    audit(db, "backup.deleted", request=request, user=user, entity_type="backup", entity_id=info.name)
    db.commit()
