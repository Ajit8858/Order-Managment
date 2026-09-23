from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "order_management",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.email_tasks",
        "app.tasks.invoice_tasks",
        "app.tasks.inventory_tasks",
        "app.tasks.cleanup_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=10,
    task_time_limit=300,
)

# Scheduled/periodic jobs (run `celery -A app.celery_app beat`)
celery_app.conf.beat_schedule = {
    "cleanup-expired-refresh-tokens-daily": {
        "task": "app.tasks.cleanup_tasks.cleanup_expired_refresh_tokens",
        "schedule": crontab(hour=3, minute=0),
    },
    "cleanup-stale-pending-orders-hourly": {
        "task": "app.tasks.cleanup_tasks.cancel_stale_pending_orders",
        "schedule": crontab(minute=0),
    },
}
