"""Explicitly import task modules so Celery workers can discover them."""
from app.tasks import article_views, delayed, diagnostics, todos  # noqa: F401
