"""Article visibility and editor reads, backed by an isolated SQLite database.

Run inside the backend environment with:
    python -m unittest discover -s tests
"""
import json
import os
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sanic import Sanic
from tortoise import Tortoise

# Keep the isolated test environment independent of local credentials.
os.environ.setdefault("JWT_SECRET", "article-visibility-tests-only-32-byte-secret")

from app.api import article as public_articles
from app.api.admin import articles as admin_articles
from app.core import article_views
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError
from app.core.security import create_access_token
from app.models.article import Article
from app.models.category import Category
from app.models.tag import Tag
from app.models.user import User


class ArticleVisibilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]}
        )
        await Tortoise.generate_schemas()
        self.admin = await User.create(
            username="editor", email="editor@example.com", password_hash="unused", is_admin=True
        )
        self.reader = await User.create(
            username="reader", email="reader@example.com", password_hash="unused"
        )
        category = await Category.create(name="Engineering", slug="engineering")
        self.draft = await Article.create(
            title="Private draft",
            slug="private-draft",
            content="<h2>Work in progress</h2><p>Private body</p>",
            author=self.admin,
            category=category,
            is_published=False,
            view_count=5,
        )
        tag = await Tag.create(name="Python", slug="python")
        await self.draft.tags.add(tag)
        self.published = await Article.create(
            title="Published article",
            slug="published-article",
            content="<p>Public body</p>",
            author=self.admin,
            is_published=True,
            view_count=7,
        )

    async def asyncTearDown(self):
        await Tortoise.close_connections()

    def request(self, user=None):
        headers = {}
        if user is not None:
            headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
        return SimpleNamespace(headers=headers, ctx=SimpleNamespace())

    def editor_handler(self):
        handler = getattr(admin_articles, "get_article_admin", None)
        self.assertIsNotNone(handler, "The authenticated editor detail endpoint is missing")
        return handler

    async def test_public_cannot_read_draft_or_increment_its_views(self):
        with self.assertRaises(NotFoundError):
            await public_articles.get_article(self.request(), self.draft.id)
        await self.draft.refresh_from_db()
        self.assertEqual(self.draft.view_count, 5)

    async def test_public_detail_returns_realtime_views_without_immediate_sql_increment(self):
        with patch.object(public_articles, "record_article_view", create=True, new=AsyncMock(return_value=8)):
            response = await public_articles.get_article(self.request(), self.published.id)
        data = json.loads(response.body)["data"]
        self.assertEqual(data["content"], "<p>Public body</p>")
        await self.published.refresh_from_db()
        self.assertEqual(data["view_count"], 8)
        self.assertEqual(self.published.view_count, 7)

    async def test_head_detail_does_not_increment_views(self):
        request = self.request()
        request.method = "HEAD"
        with patch.object(public_articles, "record_article_view", create=True, new=AsyncMock()) as record:
            response = await public_articles.get_article(request, self.published.id)
        self.assertEqual(json.loads(response.body)["data"]["view_count"], 7)
        record.assert_not_awaited()

    async def test_failed_detail_serialization_does_not_increment_views(self):
        with patch.object(public_articles, "_serialize", new=AsyncMock(side_effect=RuntimeError("bad body"))), \
                patch.object(public_articles, "record_article_view", create=True, new=AsyncMock()) as record:
            with self.assertRaisesRegex(RuntimeError, "bad body"):
                await public_articles.get_article(self.request(), self.published.id)
        record.assert_not_awaited()

    async def test_public_detail_route_accepts_a_trailing_slash(self):
        app = Sanic("article_visibility_slash_route", configure_logging=False)
        app.blueprint(public_articles.bp, url_prefix="/api/articles")
        app.router.finalize()
        route, handler, params = app.router.get(f"/api/articles/{self.published.id}/", "GET", "")
        self.assertIs(handler, public_articles.get_article)
        self.assertEqual(params, {"aid": self.published.id})

    async def test_editor_save_preserves_views_persisted_after_its_initial_read(self):
        self.assertTrue(hasattr(article_views, "persist_article_views"))
        redis = SimpleNamespace(get=AsyncMock(return_value="8"))
        old_updated_at = datetime.now(timezone.utc) - timedelta(days=1)
        await Article.filter(id=self.published.id).update(updated_at=old_updated_at)
        category = await Category.create(name="Updated category", slug="updated-category")
        tag = await Tag.create(name="Updated tag", slug="updated-tag")
        original_transaction = public_articles.in_transaction

        @asynccontextmanager
        async def persist_before_editor_transaction():
            self.assertTrue((await article_views.persist_article_views(self.published.id, redis))["updated"])
            async with original_transaction() as connection:
                yield connection

        request = self.request(self.admin)
        request.json = {
            "title": "Edited title", "summary": "Edited summary", "content": "Edited body",
            "cover": "https://blog.test/edited-cover.png", "is_published": False,
            "category_id": category.id, "tag_ids": [tag.id],
        }
        with patch.object(public_articles, "in_transaction", persist_before_editor_transaction):
            await public_articles.update_article(request, self.published.id)

        await self.published.refresh_from_db()
        self.assertEqual(self.published.view_count, 8)
        self.assertEqual(self.published.title, "Edited title")
        self.assertEqual(self.published.summary, "Edited summary")
        self.assertEqual(self.published.content, "Edited body")
        self.assertEqual(self.published.cover, "https://blog.test/edited-cover.png")
        self.assertFalse(self.published.is_published)
        self.assertEqual(self.published.category_id, category.id)
        self.assertEqual(await self.published.tags.all().values_list("id", flat=True), [tag.id])
        self.assertGreater(self.published.updated_at, old_updated_at)
        self.assertFalse((await article_views.persist_article_views(self.published.id, redis))["updated"])

    async def test_editor_publish_keeps_first_publication_time_and_can_clear_category(self):
        request = self.request(self.admin)
        request.json = {"is_published": True, "category_id": None}
        await public_articles.update_article(request, self.draft.id)
        await self.draft.refresh_from_db()
        self.assertTrue(self.draft.is_published)
        self.assertIsNotNone(self.draft.published_at)
        self.assertIsNone(self.draft.category_id)
        first_published_at = self.draft.published_at

        request.json = {"is_published": False}
        await public_articles.update_article(request, self.draft.id)
        request.json = {"is_published": True}
        await public_articles.update_article(request, self.draft.id)
        await self.draft.refresh_from_db()
        self.assertEqual(self.draft.published_at, first_published_at)

    async def test_admin_can_read_full_draft_without_recording_view(self):
        response = await self.editor_handler()(self.request(self.admin), self.draft.id)
        data = json.loads(response.body)["data"]
        self.assertFalse(data["is_published"])
        self.assertEqual(data["content"], "<h2>Work in progress</h2><p>Private body</p>")
        self.assertEqual(data["category"]["slug"], "engineering")
        self.assertEqual(data["tags"][0]["slug"], "python")
        await self.draft.refresh_from_db()
        self.assertEqual(self.draft.view_count, 5)

    async def test_editor_read_requires_login(self):
        handler = self.editor_handler()
        with self.assertRaises(UnauthorizedError):
            await handler(self.request(), self.draft.id)

    async def test_editor_read_requires_admin(self):
        handler = self.editor_handler()
        with self.assertRaises(ForbiddenError):
            await handler(self.request(self.reader), self.draft.id)

    async def test_editor_returns_not_found_for_missing_article(self):
        handler = self.editor_handler()
        with self.assertRaises(NotFoundError):
            await handler(self.request(self.admin), 99999)


if __name__ == "__main__":
    unittest.main()
