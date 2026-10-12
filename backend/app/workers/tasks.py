import logging
from datetime import UTC, datetime

from sqlalchemy import update

from app.core.db import SessionLocal
from app.models import ReportJob, Scan
from app.models.enums import JobStatus, ScanStatus
from app.services.ingest import ingest_scan
from app.services.parsers import ParseError
from app.workers.celery_app import celery

log = logging.getLogger(__name__)


def _set_scan(scan_id: int, **values: object) -> None:
    with SessionLocal() as db:
        db.execute(update(Scan).where(Scan.id == scan_id).values(**values))
        db.commit()


@celery.task(name="scans.ingest")
def ingest_scan_task(scan_id: int) -> None:
    _set_scan(scan_id, status=ScanStatus.PARSING, progress=1, error="")
    with SessionLocal() as db:
        scan = db.get(Scan, scan_id)
        if scan is None:
            return
        try:
            ingest_scan(db, scan, progress=lambda p: _set_scan(scan_id, progress=p))
            db.commit()
        except ParseError as exc:
            db.rollback()
            _set_scan(scan_id, status=ScanStatus.FAILED, error=str(exc)[:2000])
        except Exception:
            db.rollback()
            log.exception("Ingest of scan %s failed", scan_id)
            _set_scan(
                scan_id,
                status=ScanStatus.FAILED,
                error="Import failed. An administrator can find details in the server logs.",
            )


@celery.task(name="reports.generate")
def generate_report_task(job_id: int) -> None:
    from app.services.reporting.engine import render_report

    with SessionLocal() as db:
        job = db.get(ReportJob, job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        db.commit()
        try:
            render_report(db, job)
            job.status = JobStatus.DONE
        except Exception as exc:
            db.rollback()
            log.exception("Report %s failed", job_id)
            job = db.get(ReportJob, job_id)
            assert job is not None
            job.status = JobStatus.FAILED
            # RuntimeError carries a message meant for users; anything else stays in the logs
            job.error = (
                str(exc)[:2000]
                if isinstance(exc, RuntimeError)
                else "Report generation failed. An administrator can find details in the server logs."
            )
        job.finished_at = datetime.now(UTC)
        db.commit()


@celery.task(name="maintenance.expire_risk")
def expire_risk_task() -> int:
    from app.services.risk import expire_due

    with SessionLocal() as db:
        count = expire_due(db)
        db.commit()
    if count:
        log.info("Expired %s risk acceptances", count)
    return count


@celery.task(name="maintenance.daily")
def daily_maintenance_task() -> dict[str, int]:
    from app.services.maintenance import run_daily

    with SessionLocal() as db:
        result = run_daily(db)
        db.commit()
    log.info("Daily maintenance: %s", result)
    return result
