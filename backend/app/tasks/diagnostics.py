"""Manual diagnostic tasks with no database, cache or web dependencies."""
from app.celery_app import celery_app


@celery_app.task(name="app.tasks.diagnostics.ping")
def ping() -> str:
    """Return a small response to verify worker execution; never runs on a schedule."""
    return "pong"
