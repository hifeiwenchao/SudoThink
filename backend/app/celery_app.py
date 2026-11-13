"""Independent Celery entry point; importing it does not start web resources."""
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown

from app.celery_runtime import initialize_worker_resources, shutdown_worker_resources
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


@worker_process_init.connect
def initialize_worker_process(**kwargs) -> None:
    """Create async resources once in each prefork worker process."""
    initialize_worker_resources()


@worker_process_shutdown.connect
def shutdown_worker_process(**kwargs) -> None:
    """Release async resources when a prefork worker process exits."""
    shutdown_worker_resources()
