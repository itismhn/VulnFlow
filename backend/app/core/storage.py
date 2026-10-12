from pathlib import Path

from app.core.config import settings


def storage_path(*parts: str) -> Path:
    path = settings.storage_dir.resolve().joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def scan_file_path(sha256: str) -> Path:
    return storage_path("scans", f"{sha256}.nessus")


def report_file_path(job_id: int, ext: str) -> Path:
    return storage_path("reports", f"report-{job_id}.{ext}")
