from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery = Celery("report_manager", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_always_eager=settings.task_always_eager,
    task_eager_propagates=False,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    imports=("app.workers.tasks",),
    timezone="UTC",
    beat_schedule={
        # Expire risk acceptances shortly after midnight, and clean up old audit rows
        "daily-maintenance": {"task": "maintenance.daily", "schedule": crontab(minute=5, hour=0)},
        # Catch acceptances that expired while the worker was down
        "hourly-risk-expiry": {"task": "maintenance.expire_risk", "schedule": crontab(minute=17)},
    },
)
