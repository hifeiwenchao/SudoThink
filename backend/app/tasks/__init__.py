"""Explicitly import task modules so Celery workers can discover them."""
from app.tasks import article_views, delayed, diagnostics  # noqa: F401
