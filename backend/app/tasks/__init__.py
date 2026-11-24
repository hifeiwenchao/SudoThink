"""Explicitly import task modules so Celery workers can discover them."""
from app.tasks import article_views, delayed, diagnostics, todos, request_logs  # noqa: F401
