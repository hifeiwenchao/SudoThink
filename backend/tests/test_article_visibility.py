"""Article visibility and editor reads, backed by an isolated SQLite database.

Run inside the backend environment with:
    python -m unittest discover -s tests
"""
import json
import os
import unittest
from types import SimpleNamespace

from tortoise import Tortoise

# Keep the isolated test environment independent of local credentials.
os.environ.setdefault("JWT_SECRET", "article-visibility-tests-only-32-byte-secret")

from app.api import article as public_articles
from app.api.admin import articles as admin_articles
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

    async def test_public_can_read_published_article_and_records_view(self):
        response = await public_articles.get_article(self.request(), self.published.id)
        data = json.loads(response.body)["data"]
        self.assertEqual(data["content"], "<p>Public body</p>")
        await self.published.refresh_from_db()
        self.assertEqual(self.published.view_count, 8)

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
