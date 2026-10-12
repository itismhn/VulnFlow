from celery import Celery

from app.core.config import settings

celery = Celery("report_manager", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(
    task_always_eager=settings.task_always_eager,
    task_eager_propagates=False,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    imports=("app.workers.tasks",),
)
