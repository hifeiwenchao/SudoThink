"""Redis view counters and monotonic SQL persistence, independent of API logs."""
import asyncio
import importlib
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Keep module import order independent of local JWT credentials.
os.environ.setdefault("JWT_SECRET", "article-view-tests-only-32-byte-secret")

from redis.asyncio import from_url
from redis.exceptions import ConnectionError as RedisConnectionError
from tortoise import Tortoise, connections

from app.core import article_views as views
from app.models.article import Article
from app.models.user import User


class ArticleViewDatabaseCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(hasattr(views, "record_article_view"), "Redis view recording is missing")
        self.assertTrue(hasattr(views, "persist_article_views"), "Redis view persistence is missing")
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        author = await User.create(username="author", email="author@example.com", password_hash="x")
        self.article = await Article.create(
            id=secrets.randbelow(1_000_000_000) + 1_000_000_000,
            title="Existing article", slug="existing", content="Body", author=author,
            is_published=True, view_count=17,
        )
        self.key = f"article:views:{self.article.id}"

    async def asyncTearDown(self):
        await Tortoise.close_connections()


class ArticleViewTests(ArticleViewDatabaseCase):
    async def test_visit_returns_redis_total_and_schedules_persistence_without_sql_write(self):
        redis = SimpleNamespace(eval=AsyncMock(return_value=18))
        with patch.object(views, "get_redis", return_value=redis), patch.object(
            views, "schedule_task_once", new=AsyncMock(return_value=True)
        ) as schedule:
            self.assertEqual(await views.record_article_view(self.article), 18)
        await self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 17)
        self.assertEqual(redis.eval.await_args.args[1:], (1, self.key, 17))
        schedule.assert_awaited_once_with(
            "app.tasks.article_views.persist_article_views", str(self.article.id), 120,
            args=[self.article.id], redis_client=redis,
        )

    async def test_redis_failure_falls_back_to_database_count_without_scheduling(self):
        redis = SimpleNamespace(eval=AsyncMock(side_effect=RedisConnectionError("offline")))
        with patch.object(views, "get_redis", return_value=redis), patch.object(
            views, "schedule_task_once", new=AsyncMock()
        ) as schedule, self.assertLogs("app.core.article_views", level="WARNING"):
            self.assertEqual(await views.record_article_view(self.article), 17)
        schedule.assert_not_awaited()
        await self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 17)

    async def test_uninitialized_redis_falls_back_without_raising(self):
        with patch.object(views, "get_redis", side_effect=RuntimeError("not initialized")), \
                self.assertLogs("app.core.article_views", level="WARNING"):
            self.assertEqual(await views.record_article_view(self.article), 17)

    async def test_broker_failure_keeps_counter_result_and_next_visit_retries_scheduling(self):
        redis = SimpleNamespace(eval=AsyncMock(side_effect=[18, 19]))
        with patch.object(views, "get_redis", return_value=redis), patch.object(
            views, "schedule_task_once", new=AsyncMock(side_effect=[OSError("broker offline"), True])
        ) as schedule, self.assertLogs("app.core.article_views", level="WARNING"):
            self.assertEqual(await views.record_article_view(self.article), 18)
            self.assertEqual(await views.record_article_view(self.article), 19)
        self.assertEqual(schedule.await_count, 2)
        await self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 17)

    async def test_persist_is_monotonic_when_older_snapshot_finishes_later(self):
        redis = SimpleNamespace(get=AsyncMock(side_effect=["24", "21", "24"]))
        self.assertEqual(await views.persist_article_views(self.article.id, redis), {
            "article_id": self.article.id, "view_count": 24, "updated": True,
        })
        self.assertEqual(await views.persist_article_views(self.article.id, redis), {
            "article_id": self.article.id, "view_count": 21, "updated": False,
        })
        self.assertFalse((await views.persist_article_views(self.article.id, redis))["updated"])
        await self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 24)
        redis.get.assert_awaited_with(self.key)

    async def test_persist_cache_miss_and_deleted_article_are_noops(self):
        missing = SimpleNamespace(get=AsyncMock(return_value=None))
        self.assertEqual(await views.persist_article_views(self.article.id, missing), {
            "article_id": self.article.id, "view_count": None, "updated": False,
        })
        await self.article.delete()
        deleted = SimpleNamespace(get=AsyncMock(return_value="24"))
        self.assertEqual(await views.persist_article_views(self.article.id, deleted), {
            "article_id": self.article.id, "view_count": 24, "updated": False,
        })

    async def test_sql_failure_leaves_cached_snapshot_available_for_retry(self):
        redis = SimpleNamespace(get=AsyncMock(return_value="24"))
        db = connections.get("default")
        await db.execute_script("""
            CREATE TRIGGER reject_view_flush BEFORE UPDATE OF view_count ON articles
            BEGIN SELECT RAISE(ABORT, 'simulated SQL failure'); END;
        """)
        with self.assertRaisesRegex(Exception, "simulated SQL failure"):
            await views.persist_article_views(self.article.id, redis)
        await self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 17)
        await db.execute_script("DROP TRIGGER reject_view_flush;")
        self.assertTrue((await views.persist_article_views(self.article.id, redis))["updated"])
        await self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 24)


@unittest.skipUnless(os.getenv("SUDOTHINK_TEST_REDIS_URL"), "isolated Redis URL not configured")
class ArticleViewRedisIntegrationTests(ArticleViewDatabaseCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.redis = from_url(os.environ["SUDOTHINK_TEST_REDIS_URL"], decode_responses=True)
        await self.redis.delete(self.key)

    async def asyncTearDown(self):
        if hasattr(self, "redis"):
            await self.redis.delete(self.key)
            await self.redis.aclose()
        await super().asyncTearDown()

    async def test_concurrent_misses_preserve_all_visits_without_expiring_pending_counts(self):
        with patch.object(views, "get_redis", return_value=self.redis), patch.object(
            views, "schedule_task_once", new=AsyncMock(return_value=False)
        ):
            totals = await asyncio.gather(*(views.record_article_view(self.article) for _ in range(80)))
        self.assertEqual(sorted(totals), list(range(18, 98)))
        self.assertEqual(await self.redis.get(self.key), "97")
        self.assertEqual(await self.redis.ttl(self.key), -1)
        await self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 17)

    async def test_counter_uses_database_floor_and_does_not_clobber_newer_cached_total(self):
        await self.redis.set(self.key, "12", ex=30)
        with patch.object(views, "get_redis", return_value=self.redis), patch.object(
            views, "schedule_task_once", new=AsyncMock(return_value=False)
        ):
            self.assertEqual(await views.record_article_view(self.article), 18)
            await self.redis.set(self.key, "35", ex=30)
            self.assertEqual(await views.record_article_view(self.article), 36)
        self.assertEqual(await self.redis.get(self.key), "36")
        self.assertEqual(await self.redis.ttl(self.key), -1)

    async def test_visit_during_flush_remains_cached_for_later_independent_flush(self):
        await self.redis.set(self.key, "24")
        original_get = self.redis.get

        async def snapshot_then_visit(key):
            snapshot = await original_get(key)
            self.assertEqual(await views.record_article_view(self.article), 25)
            return snapshot

        with patch.object(views, "get_redis", return_value=self.redis), patch.object(
            views, "schedule_task_once", new=AsyncMock(return_value=False)
        ), patch.object(self.redis, "get", side_effect=snapshot_then_visit):
            self.assertTrue((await views.persist_article_views(self.article.id, self.redis))["updated"])
        await self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 24)
        self.assertEqual(await self.redis.get(self.key), "25")
        self.assertTrue((await views.persist_article_views(self.article.id, self.redis))["updated"])
        await self.article.refresh_from_db()
        self.assertEqual(self.article.view_count, 25)
        self.assertEqual(await self.redis.get(self.key), "25")


class ArticleViewTaskTests(unittest.TestCase):
    def test_celery_entrypoint_owns_database_and_redis_lifecycles(self):
        task_module = importlib.import_module("app.tasks.article_views")
        self.assertTrue(hasattr(task_module, "persist_article_views"), "Persist Celery task is missing")
        task = task_module.persist_article_views
        redis = SimpleNamespace(get=AsyncMock(return_value="20"), aclose=AsyncMock())
        with tempfile.TemporaryDirectory() as folder:
            config = {
                "connections": {"default": f"sqlite://{Path(folder) / 'views.sqlite3'}"},
                "apps": {"models": {"models": ["app.models"], "default_connection": "default"}},
            }

            async def prepare():
                await Tortoise.init(config=config)
                try:
                    await Tortoise.generate_schemas()
                    user = await User.create(username="task-user", email="task@example.com", password_hash="x")
                    article = await Article.create(
                        title="Task", slug="task", content="x", author=user, view_count=9,
                    )
                    return article.id
                finally:
                    await Tortoise.close_connections()

            article_id = asyncio.run(prepare())
            with patch("app.core.config.TORTOISE_ORM", config), patch(
                "redis.asyncio.from_url", return_value=redis
            ):
                result = task.apply(args=[article_id])
                self.assertTrue(result.successful(), result.result)
                self.assertTrue(result.get()["updated"])
                self.assertFalse(task.apply(args=[article_id]).get()["updated"])
            self.assertEqual(redis.aclose.await_count, 2)

            async def verify():
                await Tortoise.init(config=config)
                try:
                    self.assertEqual((await Article.get(slug="task")).view_count, 20)
                finally:
                    await Tortoise.close_connections()

            asyncio.run(verify())


if __name__ == "__main__":
    unittest.main()
