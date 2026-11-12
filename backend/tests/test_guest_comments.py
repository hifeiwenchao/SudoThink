"""Anonymous comments, moderation and privacy on isolated SQLite."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "guest-comment-tests-only-32-byte-secret")

from tortoise import Tortoise
from app.api import comment as comments
from app.api.admin import comments as admin_comments
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from app.core.security import create_access_token
from app.models.article import Article
from app.models.comment import Comment
from app.models.user import User


class GuestCommentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.admin = await User.create(username="admin", email="admin@example.com", password_hash="unused", is_admin=True)
        self.reader = await User.create(username="reader", email="reader@example.com", password_hash="unused", nickname="旧昵称")
        self.article = await Article.create(title="Published", slug="published", content="Body", author=self.admin, is_published=True)
        self.draft = await Article.create(title="Draft", slug="draft", content="Body", author=self.admin)
        for attribute, value in (
            ("get_comment_ip", lambda request: "203.0.113.42"),
            ("locate_comment_ip", AsyncMock(return_value="浙江省杭州市")),
            ("enforce_comment_rate_limit", AsyncMock()),
        ):
            patcher = patch.object(comments, attribute, new=value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    async def asyncTearDown(self):
        await Tortoise.close_connections()

    def request(self, payload=None, user=None, args=None, headers=None):
        request_headers = {} if user is None else {"Authorization": f"Bearer {create_access_token(user.id)}"}
        request_headers.update(headers or {})
        return SimpleNamespace(json=payload, args=args or {}, headers=request_headers, ctx=SimpleNamespace(), ip="203.0.113.42")

    def data(self, response):
        body = json.loads(response.body)
        self.assertEqual(body["code"], 0)
        return body["data"]

    async def submit(self, payload=None, aid=None, headers=None):
        return await comments.create_comment(self.request(payload or {"nickname": "访客_42", "content": " 评论内容 "}, headers=headers), aid or self.article.id)

    async def test_visitor_submits_pending_comment_without_creating_user_or_returning_pii(self):
        response = await self.submit({"nickname": " 访客_42 ", "email": " guest@example.com ", "content": " 评论内容 "})
        data = self.data(response)
        self.assertEqual(set(data), {"id", "is_approved"})
        self.assertFalse(data["is_approved"])
        comment = await Comment.get(id=data["id"])
        self.assertIsNone(comment.author_id)
        self.assertEqual(comment.nickname, "访客_42")
        self.assertEqual(comment.email, "guest@example.com")
        self.assertEqual(comment.content, "评论内容")
        self.assertEqual(comment.ip_address, "203.0.113.42")
        self.assertEqual(comment.location, "浙江省杭州市")
        self.assertEqual(await User.all().count(), 2)
        self.assertEqual(self.data(await comments.list_comments(self.request(), self.article.id))["total"], 0)
        self.assertIn("审核", json.loads(response.body)["message"])

    async def test_submission_records_only_the_request_user_agent_and_bounds_its_length(self):
        for user_agent, expected in (
            (None, ""), ("", ""), ("ExampleBrowser/123.0", "ExampleBrowser/123.0"),
            ("x" * 2048, "x" * 1024),
        ):
            with self.subTest(length=None if user_agent is None else len(user_agent)):
                headers = {} if user_agent is None else {"user-agent": user_agent}
                created = self.data(await self.submit(headers=headers))
                record = await Comment.get(id=created["id"])
                self.assertEqual(getattr(record, "user_agent", None), expected)
                self.assertNotIn("user_agent", created)

    async def test_nickname_email_content_and_untrusted_metadata_are_validated(self):
        invalid = (
            {}, {"nickname": "", "content": "text"}, {"nickname": "a b", "content": "text"},
            {"nickname": "访客😀", "content": "text"}, {"nickname": "é", "content": "text"},
            {"nickname": "〆", "content": "text"}, {"nickname": "\u2e9a", "content": "text"},
            {"nickname": "a" * 33, "content": "text"}, {"nickname": "a", "content": "   "},
            {"nickname": "a", "content": "x" * 1001}, {"nickname": "a", "content": "x", "email": "invalid"},
            {"nickname": "a", "content": "x", "email": "a" * 255},
            {"nickname": "a", "content": "x", "ip_address": "1.1.1.1"},
            {"nickname": "a", "content": "x", "ip": "1.1.1.1"},
            {"nickname": "a", "content": "x", "location": "伪造"},
            {"nickname": "a", "content": "x", "user_agent": "ForgedBrowser/1.0"},
            {"nickname": "a", "content": "x", "parent_id": True},
            {"nickname": "a", "content": "x", "parent_id": -1},
        )
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                await comments.create_comment(self.request(payload), self.article.id)
        self.assertEqual(await Comment.all().count(), 0)

    async def test_optional_email_and_unicode_han_nickname_are_supported(self):
        for email in (None, "", "   "):
            payload = {"nickname": "𠮷中English_09々〇⼀", "content": "text"}
            if email is not None:
                payload["email"] = email
            created = self.data(await self.submit(payload))
            self.assertEqual((await Comment.get(id=created["id"])).email, "")

    async def test_drafts_and_missing_articles_are_hidden_for_list_and_submission(self):
        for aid in (self.draft.id, 99999):
            for handler in (comments.create_comment, comments.list_comments):
                with self.subTest(aid=aid, handler=handler.__name__), self.assertRaises(NotFoundError):
                    await handler(self.request({"nickname": "a", "content": "text"}), aid)
        self.assertEqual(await Comment.all().count(), 0)

    async def test_public_list_is_paginated_approved_only_and_has_no_private_fields(self):
        first = await Comment.create(article=self.article, author=self.reader, content="Legacy", is_approved=True)
        second = await Comment.create(article=self.article, nickname="访客", email="private@example.com", ip_address="203.0.113.9", location="日本", content="Guest", is_approved=True)
        await Comment.create(article=self.article, nickname="隐藏", content="Pending")
        result = self.data(await comments.list_comments(self.request(args={"page": "2", "size": "1"}), self.article.id))
        self.assertEqual((result["total"], result["page"], result["size"]), (2, 2, 1))
        self.assertEqual([item["id"] for item in result["items"]], [first.id])
        item = result["items"][0]
        self.assertEqual(item["nickname"], "旧昵称")
        self.assertEqual(set(item), {"id", "content", "nickname", "location", "created_at", "parent_id", "reply_to"})
        self.assertIsNone(item["reply_to"])
        latest = self.data(await comments.list_comments(self.request(args={"size": "50"}), self.article.id))["items"][0]
        self.assertEqual((latest["id"], latest["nickname"], latest["location"]), (second.id, "访客", "日本"))

    async def test_public_pagination_rejects_bad_values(self):
        for args in ({"page": "abc"}, {"page": "0"}, {"page": "1.5"}, {"size": "0"}, {"size": "51"}, {"size": "-1"}, {"page": ""}):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                await comments.list_comments(self.request(args=args), self.article.id)

    async def test_locations_display_city_names_without_rewriting_saved_locations(self):
        cases = (
            ("江苏省南京市", "南京"),
            ("浙江省杭州市", "杭州"),
            ("北京市", "北京"),
            ("台湾省台北市", "台北"),
            ("新疆维吾尔自治区伊犁哈萨克自治州", "伊犁哈萨克自治州"),
            ("南京", "南京"),
            ("美国", "美国"),
            ("香港", "香港"),
            ("广东省", "广东省"),
            ("", "未知"),
        )
        expected = {}
        for location, display in cases:
            record = await Comment.create(
                article=self.article, nickname="读者", content="Text",
                location=location, is_approved=True,
            )
            expected[record.id] = (location, display)
        result = self.data(await comments.list_comments(self.request(), self.article.id))
        for item in result["items"]:
            saved, display = expected[item["id"]]
            self.assertEqual(item["location"], display)
            self.assertEqual((await Comment.get(id=item["id"])).location, saved)

        pending = await Comment.create(
            article=self.article, nickname="待审读者", content="Pending", location="浙江省杭州市",
        )
        moderation = self.data(await admin_comments.list_comments(self.request(user=self.admin, args={"status": "pending"})))
        self.assertEqual(moderation["items"][0]["id"], pending.id)
        self.assertEqual(moderation["items"][0]["location"], "杭州")

    async def test_reply_requires_approved_parent_from_same_article(self):
        approved = await Comment.create(article=self.article, author=self.reader, content="Approved", is_approved=True)
        pending = await Comment.create(article=self.article, author=self.reader, content="Pending")
        foreign = await Comment.create(article=self.draft, author=self.reader, content="Other article", is_approved=True)
        for parent, error in ((pending.id, ValidationError), (foreign.id, NotFoundError), (99999, NotFoundError)):
            with self.subTest(parent=parent), self.assertRaises(error):
                await self.submit({"nickname": "reply", "content": "text", "parent_id": parent})
        created = self.data(await self.submit({"nickname": "reply", "content": "text", "parent_id": approved.id}))
        self.assertEqual((await Comment.get(id=created["id"])).parent_id, approved.id)

    async def test_guest_reply_is_pending_then_publicly_identifies_approved_guest_parent(self):
        parent = self.data(await self.submit({
            "nickname": "父游客", "email": "parent@example.com", "content": "Parent text",
        }))
        await comments.approve_comment(self.request(user=self.admin), parent["id"])
        child = self.data(await self.submit({
            "nickname": "回复游客", "content": "Reply text", "parent_id": parent["id"],
        }))
        pending_public = self.data(await comments.list_comments(self.request(), self.article.id))
        self.assertEqual([item["id"] for item in pending_public["items"]], [parent["id"]])
        await comments.approve_comment(self.request(user=self.admin), child["id"])
        public = self.data(await comments.list_comments(self.request(), self.article.id))
        reply = next(item for item in public["items"] if item["id"] == child["id"])
        self.assertEqual(reply["parent_id"], parent["id"])
        self.assertEqual(reply.get("reply_to"), {"id": parent["id"], "nickname": "父游客"})
        self.assertEqual(public["total"], 2)
        self.assertNotIn("email", reply)
        self.assertNotIn("ip_address", reply)

    async def test_rejected_parent_keeps_public_reply_without_disclosing_parent_context(self):
        parent = self.data(await self.submit({
            "nickname": "父游客", "email": "parent@example.com", "content": "Parent private text",
        }))
        await comments.approve_comment(self.request(user=self.admin), parent["id"])
        child = self.data(await self.submit({
            "nickname": "回复游客", "content": "Reply text", "parent_id": parent["id"],
        }))
        await comments.approve_comment(self.request(user=self.admin), child["id"])
        await comments.reject_comment(self.request(user=self.admin), parent["id"])
        public = self.data(await comments.list_comments(self.request(), self.article.id))
        self.assertEqual((public["total"], public["items"][0]["id"]), (1, child["id"]))
        reply = public["items"][0]
        self.assertEqual(reply["parent_id"], parent["id"])
        self.assertIn("reply_to", reply)
        self.assertIsNone(reply["reply_to"])
        for private_context in ("父游客", "parent@example.com", "Parent private text", "203.0.113.42"):
            self.assertNotIn(private_context, json.dumps(public, ensure_ascii=False))

    async def test_admin_can_review_private_guest_context_and_approve(self):
        created = self.data(await self.submit(
            {"nickname": "访客", "email": "guest@example.com", "content": "Text"},
            headers={"user-agent": "PrivateBrowser/1.0"},
        ))
        result = self.data(await admin_comments.list_comments(self.request(user=self.admin, args={"status": "pending"})))
        item = result["items"][0]
        self.assertEqual(item["id"], created["id"])
        self.assertEqual((item["nickname"], item["email"], item["ip_address"]), ("访客", "guest@example.com", "203.0.113.42"))
        self.assertEqual(item.get("user_agent"), "PrivateBrowser/1.0")
        self.assertIsNone(item["author"])
        self.assertEqual(item["article"]["id"], self.article.id)
        await comments.approve_comment(self.request(user=self.admin), created["id"])
        public = self.data(await comments.list_comments(self.request(), self.article.id))
        self.assertEqual(public["total"], 1)
        self.assertNotIn("user_agent", public["items"][0])
        self.assertNotIn("PrivateBrowser/1.0", json.dumps(public))

    async def test_article_author_can_moderate_without_receiving_guest_private_fields(self):
        self.article.author = self.reader
        await self.article.save(update_fields=["author_id"])
        created = self.data(await self.submit({
            "nickname": "访客", "email": "guest@example.com", "content": "Text",
        }, headers={"user-agent": "PrivateBrowser/1.0"}))

        pending = self.data(await comments.list_pending_comments(
            self.request(user=self.reader), self.article.id,
        ))
        self.assertEqual([item["id"] for item in pending], [created["id"]])
        for approved in (False, True):
            response = (
                self.data(await comments.approve_comment(
                    self.request(user=self.reader), created["id"],
                )) if approved else pending[0]
            )
            with self.subTest(approved=approved):
                self.assertEqual(response["nickname"], "访客")
                self.assertEqual(response["is_approved"], approved)
                self.assertNotIn("email", response)
                self.assertNotIn("ip_address", response)
                self.assertNotIn("user_agent", response)
                self.assertNotIn("location_detail", response)
        # Repeated approvals have the same privacy boundary as the first approval.
        repeated = self.data(await comments.approve_comment(
            self.request(user=self.reader), created["id"],
        ))
        self.assertNotIn("email", repeated)
        self.assertNotIn("ip_address", repeated)
        self.assertNotIn("user_agent", repeated)
        self.assertNotIn("location_detail", repeated)
        self.assertTrue((await Comment.get(id=created["id"])).is_approved)

    async def test_admin_article_moderation_includes_guest_private_fields(self):
        created = self.data(await self.submit({
            "nickname": "访客", "email": "guest@example.com", "content": "Text",
        }, headers={"user-agent": "PrivateBrowser/1.0"}))
        pending = self.data(await comments.list_pending_comments(
            self.request(user=self.admin), self.article.id,
        ))
        first_approval = self.data(await comments.approve_comment(
            self.request(user=self.admin), created["id"],
        ))
        repeated_approval = self.data(await comments.approve_comment(
            self.request(user=self.admin), created["id"],
        ))
        for item in (pending[0], first_approval, repeated_approval):
            self.assertEqual(item["email"], "guest@example.com")
            self.assertEqual(item["ip_address"], "203.0.113.42")
            self.assertEqual(item.get("user_agent"), "PrivateBrowser/1.0")

    async def test_reject_retains_comment_and_allows_approval_and_rejection_again(self):
        created = self.data(await self.submit({
            "nickname": "访客", "email": "guest@example.com", "content": "Text",
        }))
        for action, status, approved, rejected in (
            (comments.reject_comment, "rejected", False, True),
            (comments.reject_comment, "rejected", False, True),
            (comments.approve_comment, "approved", True, False),
            (comments.approve_comment, "approved", True, False),
            (comments.reject_comment, "rejected", False, True),
        ):
            response = await action(self.request(user=self.admin), created["id"])
            record = await Comment.get_or_none(id=created["id"])
            self.assertIsNotNone(record, "Rejection must retain the comment for review")
            self.assertEqual((record.is_approved, record.is_rejected), (approved, rejected))
            item = self.data(response)
            self.assertEqual((item["status"], item["is_approved"]), (status, approved))
            self.assertEqual(item["email"], "guest@example.com")
            self.assertEqual(item["ip_address"], "203.0.113.42")
            self.assertEqual(item.get("user_agent"), "")
            public = self.data(await comments.list_comments(self.request(), self.article.id))
            self.assertEqual(public["total"], int(approved))

    async def test_article_pending_list_excludes_rejected_comments(self):
        pending = self.data(await self.submit())
        rejected = self.data(await self.submit())
        await comments.reject_comment(self.request(user=self.admin), rejected["id"])
        self.assertTrue(await Comment.exists(id=rejected["id"]))
        result = self.data(await comments.list_pending_comments(
            self.request(user=self.admin), self.article.id,
        ))
        self.assertEqual([item["id"] for item in result], [pending["id"]])
        self.assertEqual(result[0]["status"], "pending")

    async def test_article_author_rejection_keeps_guest_private_fields_hidden(self):
        self.article.author = self.reader
        await self.article.save(update_fields=["author_id"])
        created = self.data(await self.submit({
            "nickname": "访客", "email": "guest@example.com", "content": "Text",
        }))
        rejected = self.data(await comments.reject_comment(
            self.request(user=self.reader), created["id"],
        ))
        self.assertIsNotNone(rejected, "Rejection should return the resulting moderation state")
        self.assertEqual(rejected["status"], "rejected")
        self.assertNotIn("email", rejected)
        self.assertNotIn("ip_address", rejected)
        self.assertNotIn("user_agent", rejected)

    async def test_guest_cannot_moderate_or_delete_and_other_users_cannot_review(self):
        created = self.data(await self.submit())
        for handler in (comments.approve_comment, comments.reject_comment, comments.delete_comment):
            with self.subTest(handler=handler.__name__), self.assertRaises(UnauthorizedError):
                await handler(self.request(), created["id"])
            with self.subTest(handler=handler.__name__), self.assertRaises(ForbiddenError):
                await handler(self.request(user=self.reader), created["id"])
        with self.assertRaises(ForbiddenError):
            await admin_comments.list_comments(self.request(user=self.reader, args={"status": "pending"}))
        self.assertTrue(await Comment.exists(id=created["id"]))

    async def test_deleting_legacy_comment_author_retains_comment(self):
        comment = await Comment.create(article=self.article, author=self.reader, content="Retained", is_approved=True)
        await self.reader.delete()
        retained = await Comment.get_or_none(id=comment.id)
        self.assertIsNotNone(retained)
        self.assertIsNone(retained.author_id)

    async def test_admin_pagination_validation_is_consistent(self):
        for args in ({"page": "abc"}, {"page": "0"}, {"size": "0"}, {"size": "101"}):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                await admin_comments.list_comments(self.request(user=self.admin, args={**args, "status": "pending"}))


if __name__ == "__main__":
    unittest.main()
