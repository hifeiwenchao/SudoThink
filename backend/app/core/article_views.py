"""Realtime Redis article views with delayed, monotonic SQL persistence."""
import logging

from redis.exceptions import RedisError

from app.core.delayed_tasks import schedule_task_once
from app.core.redis import get_redis
from app.models.article import Article


logger = logging.getLogger(__name__)
_PERSIST_TASK = "app.tasks.article_views.persist_article_views"

# Each visit reconciles with its DB snapshot before incrementing. The script is
# atomic even when concurrent requests all start with an empty/stale cache.
_INCREMENT_VIEWS = """
local key = KEYS[1]
local base = tonumber(ARGV[1])
redis.call('SET', key, ARGV[1], 'NX')
local current = tonumber(redis.call('GET', key))
if not current or current < base then
    redis.call('SET', key, ARGV[1])
end
redis.call('PERSIST', key)
return redis.call('INCR', key)
"""


async def record_article_view(article: Article) -> int:
    """Return the realtime total; Redis failures leave the DB count unchanged."""
    try:
        redis = get_redis()
        total = int(await redis.eval(
            _INCREMENT_VIEWS, 1, f"article:views:{article.id}", article.view_count,
        ))
    except (RedisError, RuntimeError) as exc:
        logger.warning("Article view counter unavailable (%s)", type(exc).__name__)
        return article.view_count

    try:
        await schedule_task_once(
            _PERSIST_TASK, str(article.id), 120, args=[article.id], redis_client=redis,
        )
    except Exception as exc:
        # Keep the incremented total. A later visit can retry publishing if the
        # scheduler could not create this window; do not fail the public read.
        logger.warning("Article view persistence scheduling failed (%s)", type(exc).__name__)
    return total


async def persist_article_views(article_id: int, redis_client) -> dict:
    """Write one cached snapshot without changing Redis or decreasing SQL views.

    The caller owns ORM and Redis lifecycles. Increments after this read remain
    in Redis until a later independent request schedules another persistence.
    """
    raw_total = await redis_client.get(f"article:views:{article_id}")
    if raw_total is None:
        return {"article_id": article_id, "view_count": None, "updated": False}
    snapshot = int(raw_total)
    updated = await Article.filter(id=article_id, view_count__lt=snapshot).update(
        view_count=snapshot,
    )
    return {"article_id": article_id, "view_count": snapshot, "updated": bool(updated)}
