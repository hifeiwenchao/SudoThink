"""Unified comment administration against an isolated SQLite database."""
import json
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "admin-comment-tests-only-32-byte-secret")

from tortoise import Tortoise

from app.api.admin import comments
from app.core.exceptions import ForbiddenError, UnauthorizedError, ValidationError
from app.core.security import create_access_token
from app.models.article import Article
from app.models.comment import Comment
from app.models.user import User


class AdminCommentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.admin = await User.create(
            username="admin", email="admin@example.com", password_hash="unused", is_admin=True,
        )
        self.reader = await User.create(
            username="reader", email="reader@example.com", password_hash="unused",
        )
        self.inactive = await User.create(
            username="inactive", email="inactive@example.com", password_hash="unused",
            is_admin=True, is_active=False,
        )
        self.published = await Article.create(
            title="Published", slug="published", content="Body", author=self.admin,
            is_published=True,
        )
        self.draft = await Article.create(
            title="Draft", slug="draft", content="Body", author=self.admin,
        )
        self.records = {}
        for article in (self.published, self.draft):
            for state, approved, rejected in (
                ("pending", False, False), ("approved", True, False), ("rejected", False, True),
            ):
                record = await Comment.create(
                    article=article, author=self.reader, content=f"{article.title} {state}",
                    nickname="读者", email="private@example.com", ip_address="203.0.113.7",
                    is_approved=approved, is_rejected=rejected,
                )
                self.records[(article.id, state)] = record.id
        # Tie timestamps to verify the secondary ordering prevents unstable pages.
        await Comment.all().update(created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))

    async def asyncTearDown(self):
        await Tortoise.close_connections()

    def request(self, user=None, **args):
        headers = {} if user is None else {"Authorization": f"Bearer {create_access_token(user.id)}"}
        return SimpleNamespace(headers=headers, ctx=SimpleNamespace(), args=args)

    def data(self, response):
        self.assertEqual(response.status, 200)
        body = json.loads(response.body)
        self.assertEqual(body["code"], 0)
        return body["data"]

    async def test_default_and_all_status_include_every_state_with_private_review_context(self):
        for args in ({}, {"status": "all"}):
            with self.subTest(args=args):
                result = self.data(await comments.list_comments(self.request(self.admin, **args)))
                self.assertEqual((result["total"], result["page"], result["size"]), (6, 1, 10))
                self.assertEqual([item["id"] for item in result["items"]], [6, 5, 4, 3, 2, 1])
                self.assertEqual(
                    [item["status"] for item in result["items"]],
                    ["rejected", "approved", "pending", "rejected", "approved", "pending"],
                )
                for item in result["items"]:
                    self.assertEqual(item["is_approved"], item["status"] == "approved")
                    self.assertEqual((item["email"], item["ip_address"]), ("private@example.com", "203.0.113.7"))
                    self.assertEqual(item["author"]["id"], self.reader.id)
                self.assertEqual(result["items"][0]["article"], {
                    "id": self.draft.id, "title": "Draft", "is_published": False,
                })
                self.assertEqual(result["items"][-1]["article"], {
                    "id": self.published.id, "title": "Published", "is_published": True,
                })

    async def test_status_and_article_filters_combine_with_stable_pagination(self):
        for status in ("pending", "approved", "rejected"):
            with self.subTest(status=status):
                first = self.data(await comments.list_comments(
                    self.request(self.admin, status=status, size="1"),
                ))
                second = self.data(await comments.list_comments(
                    self.request(self.admin, status=status, page="2", size="1"),
                ))
                empty = self.data(await comments.list_comments(
                    self.request(self.admin, status=status, page="3", size="1"),
                ))
                self.assertEqual([first["total"], second["total"], empty["total"]], [2, 2, 2])
                self.assertEqual([item["id"] for item in first["items"]], [self.records[(self.draft.id, status)]])
                self.assertEqual([item["id"] for item in second["items"]], [self.records[(self.published.id, status)]])
                self.assertEqual(empty["items"], [])
                combined = self.data(await comments.list_comments(self.request(
                    self.admin, status=status, article_id=str(self.published.id),
                )))
                self.assertEqual(combined["total"], 1)
                self.assertEqual([item["id"] for item in combined["items"]], [self.records[(self.published.id, status)]])

    async def test_article_filter_with_no_status_includes_all_article_states(self):
        result = self.data(await comments.list_comments(self.request(
            self.admin, article_id=str(self.draft.id),
        )))
        self.assertEqual(result["total"], 3)
        self.assertEqual([item["status"] for item in result["items"]], ["rejected", "approved", "pending"])
        missing = self.data(await comments.list_comments(self.request(self.admin, article_id="99999")))
        self.assertEqual((missing["total"], missing["items"]), (0, []))

    async def test_approved_status_takes_precedence_for_inconsistent_legacy_flags(self):
        record = await Comment.create(
            article=self.published, content="Legacy mixed flags", is_approved=True, is_rejected=True,
        )
        approved = self.data(await comments.list_comments(self.request(self.admin, status="approved")))
        self.assertEqual(next(item for item in approved["items"] if item["id"] == record.id)["status"], "approved")
        for status in ("rejected", "pending"):
            result = self.data(await comments.list_comments(self.request(self.admin, status=status)))
            self.assertNotIn(record.id, [item["id"] for item in result["items"]])

    async def test_filters_and_pagination_require_strict_supported_values(self):
        invalid = (
            {"status": ""}, {"status": "unknown"}, {"status": "Pending"},
            {"status": None}, {"status": ["pending"]},
            {"article_id": ""}, {"article_id": "0"}, {"article_id": "-1"},
            {"article_id": "+1"}, {"article_id": "1.0"}, {"article_id": " 1"},
            {"article_id": "１"}, {"article_id": "1" * 11}, {"article_id": 1},
            {"article_id": None}, {"page": "abc"}, {"page": "0"}, {"page": "1.0"},
            {"page": "１"}, {"page": "1" * 11}, {"size": "0"}, {"size": "101"},
        )
        for args in invalid:
            with self.subTest(args=args), self.assertRaises(ValidationError):
                await comments.list_comments(self.request(self.admin, **args))

    async def test_list_requires_an_active_administrator(self):
        for user, error in (
            (None, UnauthorizedError), (self.reader, ForbiddenError), (self.inactive, UnauthorizedError),
        ):
            with self.subTest(user=user), self.assertRaises(error):
                await comments.list_comments(self.request(user))


if __name__ == "__main__":
    unittest.main()
