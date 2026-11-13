"""Article view persistence with task-local ORM and Redis lifecycles."""
import asyncio

from app.celery_app import celery_app


@celery_app.task(name="app.tasks.article_views.persist_article_views")
def persist_article_views(article_id: int) -> dict:
    async def run() -> dict:
        # Task discovery must not import ORM, Redis, models or the Sanic app.
        from redis.asyncio import from_url
        from tortoise import Tortoise

        from app.core.article_views import persist_article_views as persist
        from app.core.config import TORTOISE_ORM, settings

        redis = from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await Tortoise.init(config=TORTOISE_ORM)
            return await persist(article_id, redis)
        finally:
            try:
                await Tortoise.close_connections()
            finally:
                await redis.aclose()

    return asyncio.run(run())
