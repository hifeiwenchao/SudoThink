"""Admin statistics and user pagination, backed by an isolated SQLite database."""
import json
import os
import unittest
from types import SimpleNamespace

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "admin-statistics-tests-only-32-byte-secret")

from tortoise import Tortoise

from app.api.admin.dashboard import dashboard
from app.api.admin.users import list_users
from app.api.comment import reject_comment
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import create_access_token
from app.models.article import Article
from app.models.comment import Comment
from app.models.user import User


class AdminStatisticsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.admin = await User.create(
            username="admin", email="admin@example.com", password_hash="unused", is_admin=True
        )

    async def asyncTearDown(self):
        await Tortoise.close_connections()

    def request(self, user=None, **args):
        headers = {}
        if user is not None:
            headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
        return SimpleNamespace(headers=headers, ctx=SimpleNamespace(), args=args)

    def data(self, response):
        self.assertEqual(response.status, 200)
        body = json.loads(response.body)
        self.assertEqual(body["code"], 0)
        return body["data"]

    async def add_readers(self):
        reader = await User.create(
            username="reader", email="reader@example.com", password_hash="unused"
        )
        inactive = await User.create(
            username="inactive", email="inactive@example.com", password_hash="unused",
            is_active=False,
        )
        return reader, inactive

    async def test_dashboard_returns_zero_content_counts_for_a_new_installation(self):
        result = self.data(await dashboard(self.request(self.admin)))
        self.assertEqual(result, {
            "total_users": 1, "total_articles": 0, "total_comments": 0, "pending_comments": 0,
        })

    async def test_dashboard_counts_all_content_and_only_pending_comments_as_pending(self):
        reader, _ = await self.add_readers()
        published = await Article.create(
            title="Published", slug="published", content="Body", author=self.admin,
            is_published=True,
        )
        draft = await Article.create(
            title="Draft", slug="draft", content="Body", author=self.admin,
        )
        await Comment.create(content="Pending", article=published, author=reader)
        rejected = await Comment.create(content="Rejected", article=published, author=reader)
        await reject_comment(self.request(self.admin), rejected.id)
        for article in (published, published, draft):
            await Comment.create(
                content="Approved", article=article, author=reader, is_approved=True
            )

        result = self.data(await dashboard(self.request(self.admin)))
        self.assertEqual(result, {
            "total_users": 3, "total_articles": 2, "total_comments": 5, "pending_comments": 1,
        })

    async def test_user_list_reports_full_total_on_paginated_and_empty_pages(self):
        reader, inactive = await self.add_readers()
        first = self.data(await list_users(self.request(self.admin, page="1", size="2")))
        second = self.data(await list_users(self.request(self.admin, page="2", size="2")))
        empty = self.data(await list_users(self.request(self.admin, page="3", size="2")))

        self.assertEqual([first["total"], second["total"], empty["total"]], [3, 3, 3])
        self.assertEqual([first["page"], second["page"], empty["page"]], [1, 2, 3])
        self.assertEqual([first["size"], second["size"], empty["size"]], [2, 2, 2])
        self.assertEqual([len(first["items"]), len(second["items"]), len(empty["items"])], [2, 1, 0])
        self.assertCountEqual(
            [item["id"] for item in first["items"] + second["items"]],
            [self.admin.id, reader.id, inactive.id],
        )

    async def test_statistics_and_user_list_require_an_active_administrator(self):
        reader, inactive = await self.add_readers()
        for handler in (dashboard, list_users):
            for user, error in (
                (None, UnauthorizedError), (reader, ForbiddenError), (inactive, UnauthorizedError),
            ):
                with self.subTest(handler=handler.__name__, user=user), self.assertRaises(error):
                    await handler(self.request(user))


if __name__ == "__main__":
    unittest.main()
