"""Explicitly import task modules so Celery workers can discover them."""
from app.tasks import diagnostics  # noqa: F401
