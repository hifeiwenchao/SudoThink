"""Independent Celery entry point; importing it does not start web resources."""
from celery import Celery

from app.core.config import settings


# Delayed once jobs are published by their first trigger; beat remains available
# for independent periodic jobs without scanning all article counters.
BEAT_SCHEDULE: dict = {}

celery_app = Celery("sudothink")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND or None,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_accept_content=["json"],
    timezone=settings.CELERY_TIMEZONE,
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    worker_concurrency=settings.CELERY_WORKER_CONCURRENCY,
    worker_prefetch_multiplier=1,
    task_default_queue="sudothink",
    task_default_exchange="sudothink",
    task_default_routing_key="sudothink",
    control_exchange="sudothink",
    beat_schedule=BEAT_SCHEDULE,
)
celery_app.autodiscover_tasks(["app"])
