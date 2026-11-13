"""Article view persistence using Celery worker lifecycle resources."""

from app.celery_app import celery_app
from app.celery_runtime import run_with_worker_resources


@celery_app.task(name="app.tasks.article_views.persist_article_views")
def persist_article_views(article_id: int) -> dict:
    async def run(redis) -> dict:
        # The worker lifecycle owns the event loop, ORM and Redis resources.
        from app.core.article_views import persist_article_views as persist
        return await persist(article_id, redis)

    return run_with_worker_resources(run)
