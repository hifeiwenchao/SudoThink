"""API log cleanup through the Celery worker's lifecycle resources."""
from app.celery_app import celery_app
from app.celery_runtime import run_with_worker_resources


@celery_app.task(name="app.tasks.request_logs.cleanup_request_logs", ignore_result=True)
def cleanup_request_logs() -> dict:
    async def run(redis):
        from app.core.request_log_retention import cleanup_request_logs
        return await cleanup_request_logs()

    return run_with_worker_resources(run)
