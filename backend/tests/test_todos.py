"""Private admin todos, validation and reminder invalidation with a real database."""
import importlib
import importlib.util
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "todo-tests-only-32-byte-secret-value")

from sanic import Sanic
from sanic.exceptions import BadRequest
from tortoise import Tortoise, connections

from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from app.core.mail import MailDeliveryError
from app.core.security import create_access_token
from app.models.user import User


class TodoAvailabilityTests(unittest.TestCase):
    def test_feature_modules_exist(self):
        self.assertIsNotNone(importlib.util.find_spec("app.models.todo"), "Todo model is missing")
        self.assertIsNotNone(importlib.util.find_spec("app.schemas.todo"), "Todo schema is missing")
        self.assertIsNotNone(importlib.util.find_spec("app.api.admin.todos"), "Todo API is missing")


class TodoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.api = importlib.import_module("app.api.admin.todos")
        self.Todo = importlib.import_module("app.models.todo").Todo
        await Tortoise.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]},
            use_tz=False, timezone="Asia/Shanghai",
        )
        await Tortoise.generate_schemas()
        self.admin = await User.create(
            username="admin", email="admin@example.com", password_hash="unused", is_admin=True,
        )
        self.other = await User.create(
            username="other", email="other@example.com", password_hash="unused", is_admin=True,
        )
        self.reader = await User.create(
            username="reader", email="reader@example.com", password_hash="unused",
        )
        self.patches = [patch.object(self.api, "smtp_ready", return_value=True)]
        for current in self.patches:
            current.start()
        self.due = datetime.now(timezone.utc) + timedelta(hours=3)

    async def asyncTearDown(self):
        for current in self.patches:
            current.stop()
        await Tortoise.close_connections()

    def request(self, user=None, payload=None, args=None, content_type="application/json"):
        headers = {"Content-Type": content_type}
        if user is not None:
            headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
        arguments = args or {}
        return SimpleNamespace(
            headers=headers, ctx=SimpleNamespace(), json=payload, args=arguments,
            get_args=lambda **kwargs: arguments,
        )

    def data(self, response):
        body = json.loads(response.body)
        self.assertEqual(body["code"], 0)
        return body["data"]

    def payload(self, **values):
        return {"title": "待办事项", "content": "详情", "due_at": self.due.isoformat(),
                "reminder_enabled": True, "reminder_email": "reminder@example.com", **values}

    async def create(self, user=None, **values):
        return self.data(await self.api.create_todo(self.request(
            user or self.admin, self.payload(**values),
        )))

    async def list(self, user=None, **args):
        return self.data(await self.api.list_todos(self.request(user or self.admin, args=args)))

    async def test_create_edit_delete_and_defaults(self):
        saved = await self.create(title="  给服务续费  ", content="  账单确认  ")
        self.assertEqual(saved["title"], "给服务续费")
        self.assertEqual(saved["content"], "账单确认")
        self.assertEqual(saved["reminder_status"], "pending")
        self.assertEqual(saved["reminder_email"], "reminder@example.com")
        self.assertFalse(saved["is_completed"])
        self.assertEqual(saved["reminder_attempts"], 0)
        self.assertNotIn("owner_id", saved)
        self.assertNotIn("reminder_claim_token", saved)
        self.assertNotIn("reminder_revision", saved)
        self.assertEqual(datetime.fromisoformat(saved["due_at"]), self.due)
        edited = self.data(await self.api.update_todo(self.request(
            self.admin, self.payload(title="新标题", content="", due_at=None, reminder_enabled=False),
        ), saved["id"]))
        self.assertEqual(edited["title"], "新标题")
        self.assertIsNone(edited["due_at"])
        self.assertEqual(edited["reminder_status"], "disabled")
        await self.api.delete_todo(self.request(self.admin), saved["id"])
        self.assertFalse(await self.Todo.exists(id=saved["id"]))

    async def test_todos_are_private_between_admins_and_missing_ids_are_not_found(self):
        saved = await self.create()
        await self.create(self.other, title="另一个管理员的待办")
        listing = await self.list()
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["items"][0]["id"], saved["id"])
        actions = [
            (self.api.update_todo, self.payload()),
            (self.api.set_todo_completion, {"is_completed": True}),
            (self.api.delete_todo, None),
            (self.api.retry_todo_reminder, None),
        ]
        for handler, payload in actions:
            for todo_id in (saved["id"], 9999):
                with self.subTest(handler=handler.__name__, id=todo_id), self.assertRaises(NotFoundError):
                    await handler(self.request(self.other, payload), todo_id)
        self.assertTrue(await self.Todo.exists(id=saved["id"]))

    async def test_all_routes_require_an_active_administrator(self):
        saved = await self.create()
        actions = [
            (self.api.list_todos, None, ()),
            (self.api.create_todo, self.payload(), ()),
            (self.api.update_todo, self.payload(), (saved["id"],)),
            (self.api.set_todo_completion, {"is_completed": True}, (saved["id"],)),
            (self.api.delete_todo, None, (saved["id"],)),
            (self.api.retry_todo_reminder, None, (saved["id"],)),
        ]
        for handler, payload, arguments in actions:
            for user, error in ((None, UnauthorizedError), (self.reader, ForbiddenError)):
                with self.subTest(handler=handler.__name__, user=user), self.assertRaises(error):
                    await handler(self.request(user, payload), *arguments)
        self.admin.is_active = False
        await self.admin.save()
        for handler, payload, arguments in actions:
            with self.assertRaises(UnauthorizedError):
                await handler(self.request(self.admin, payload), *arguments)

    async def test_title_content_boolean_and_timezone_validation(self):
        invalid = [
            None, [], 4, {}, self.payload(title=""), self.payload(title="  "),
            self.payload(title="x" * 201), self.payload(content="x" * 10001),
            self.payload(title=4), self.payload(content=False), self.payload(extra="field"),
            self.payload(reminder_enabled="true"), self.payload(reminder_enabled=1),
            self.payload(reminder_enabled=None), self.payload(due_at="2026-11-17T10:00:00"),
            self.payload(due_at=123), self.payload(due_at="1234567890"), self.payload(due_at="invalid"),
            self.payload(due_at=None), self.payload(title="bad\nheader"),
            self.payload(reminder_email=""), self.payload(reminder_email=None),
            self.payload(reminder_email=4), self.payload(reminder_email="bad"),
            self.payload(reminder_email="A Person <a@example.com>"),
            self.payload(reminder_email="a@example.com,b@example.com"),
            self.payload(reminder_email="a\r\nb@example.com"),
        ]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                await self.api.create_todo(self.request(self.admin, payload))
        self.assertEqual(await self.Todo.all().count(), 0)
        # Explicit UTC offsets refer to an instant regardless of the server timezone.
        due = "2026-12-01T08:15:00+08:00"
        saved = await self.create(due_at=due)
        self.assertEqual(datetime.fromisoformat(saved["due_at"]), datetime.fromisoformat(due))
        await self.create(due_at=None, reminder_enabled=False)
        await self.create(due_at="2020-01-01T00:00:00Z")

    async def test_bad_json_content_type_and_partial_edits_do_not_modify_todo(self):
        saved = await self.create()
        with self.assertRaises(ValidationError):
            await self.api.update_todo(self.request(self.admin, {"title": "partial"}), saved["id"])
        with self.assertRaises(ValidationError):
            await self.api.create_todo(self.request(self.admin, self.payload(), content_type="text/plain"))
        request = self.request(self.admin)

        class InvalidJSONRequest:
            headers = request.headers
            ctx = request.ctx

            @property
            def json(self):
                raise BadRequest("invalid JSON")

        with self.assertRaises(ValidationError):
            await self.api.create_todo(InvalidJSONRequest())
        self.assertEqual((await self.Todo.get(id=saved["id"])).title, saved["title"])

    async def test_completion_disables_pending_reminder_and_reopen_does_not_resend(self):
        saved = await self.create()
        await self.Todo.filter(id=saved["id"]).update(
            reminder_status="sending", reminder_claim_token="a" * 32,
            reminder_claim_until=self.due, reminder_attempts=1,
        )
        completed = self.data(await self.api.set_todo_completion(self.request(
            self.admin, {"is_completed": True},
        ), saved["id"]))
        self.assertTrue(completed["is_completed"])
        self.assertFalse(completed["reminder_enabled"])
        self.assertEqual(completed["reminder_status"], "disabled")
        row = await self.Todo.get(id=saved["id"])
        self.assertEqual(row.reminder_claim_token, "")
        self.assertIsNone(row.reminder_claim_until)
        self.assertIsNone(row.reminder_next_attempt_at)
        self.assertGreater(row.reminder_revision, 1)
        reopened = self.data(await self.api.set_todo_completion(self.request(
            self.admin, {"is_completed": False},
        ), saved["id"]))
        self.assertFalse(reopened["is_completed"])
        self.assertFalse(reopened["reminder_enabled"])
        for payload in ({}, {"is_completed": "true"}, {"is_completed": 1},
                        {"is_completed": True, "extra": 1}):
            with self.assertRaises(ValidationError):
                await self.api.set_todo_completion(self.request(self.admin, payload), saved["id"])

    async def test_redundant_incomplete_update_keeps_an_existing_reminder(self):
        saved = await self.create()
        unchanged = self.data(await self.api.set_todo_completion(self.request(
            self.admin, {"is_completed": False},
        ), saved["id"]))
        self.assertTrue(unchanged["reminder_enabled"])
        self.assertEqual(unchanged["reminder_status"], "pending")

    async def test_editing_invalidates_inflight_claim_and_old_revision_updates(self):
        saved = await self.create()
        await self.Todo.filter(id=saved["id"]).update(
            reminder_status="sending", reminder_claim_token="b" * 32,
            reminder_claim_until=self.due, reminder_attempts=2,
        )
        before = await self.Todo.get(id=saved["id"])
        changed = self.data(await self.api.update_todo(self.request(
            self.admin, self.payload(title="提醒内容已修改"),
        ), saved["id"]))
        self.assertEqual(changed["reminder_status"], "pending")
        row = await self.Todo.get(id=saved["id"])
        self.assertGreater(row.reminder_revision, before.reminder_revision)
        self.assertEqual(row.reminder_attempts, 0)
        self.assertEqual(row.reminder_claim_token, "")
        self.assertEqual(row.reminder_next_attempt_at, row.due_at)
        updated = await self.Todo.filter(id=row.id, reminder_revision=before.reminder_revision).update(
            reminder_status="sent",
        )
        self.assertEqual(updated, 0)

    async def test_sent_reminder_is_preserved_until_rescheduled(self):
        saved = await self.create()
        sent_at = datetime.now(timezone.utc)
        await self.Todo.filter(id=saved["id"]).update(
            reminder_status="sent", reminder_sent_at=sent_at, reminder_attempts=1,
            reminder_next_attempt_at=None,
        )
        changed = self.data(await self.api.update_todo(self.request(
            self.admin, self.payload(title="只修改内容"),
        ), saved["id"]))
        self.assertEqual(changed["reminder_status"], "sent")
        self.assertEqual(datetime.fromisoformat(changed["reminder_sent_at"]), sent_at)
        self.assertEqual(changed["reminder_attempts"], 1)
        new_due = self.due + timedelta(hours=1)
        changed = self.data(await self.api.update_todo(self.request(
            self.admin, self.payload(due_at=new_due.isoformat()),
        ), saved["id"]))
        self.assertEqual(changed["reminder_status"], "pending")
        self.assertIsNone(changed["reminder_sent_at"])
        self.assertEqual(changed["reminder_attempts"], 0)

    async def test_failed_reminders_require_retry_or_a_changed_schedule(self):
        saved = await self.create()
        await self.Todo.filter(id=saved["id"]).update(
            reminder_status="failed", reminder_attempts=3, reminder_error="SMTP 登录失败",
            reminder_next_attempt_at=None,
        )
        changed = self.data(await self.api.update_todo(self.request(
            self.admin, self.payload(title="改一下标题"),
        ), saved["id"]))
        self.assertEqual(changed["reminder_status"], "failed")
        retried = self.data(await self.api.retry_todo_reminder(self.request(self.admin), saved["id"]))
        self.assertEqual(retried["reminder_status"], "pending")
        self.assertEqual(retried["reminder_attempts"], 0)
        self.assertEqual(retried["reminder_error"], "")
        with self.assertRaises(ValidationError):
            await self.api.retry_todo_reminder(self.request(self.admin), saved["id"])

    async def test_completed_todo_cannot_enable_a_reminder_until_reopened(self):
        saved = await self.create()
        await self.api.set_todo_completion(self.request(self.admin, {"is_completed": True}), saved["id"])
        with self.assertRaises(ValidationError):
            await self.api.update_todo(self.request(self.admin, self.payload()), saved["id"])
        changed = self.data(await self.api.update_todo(self.request(
            self.admin, self.payload(reminder_enabled=False),
        ), saved["id"]))
        self.assertTrue(changed["is_completed"])

    async def test_list_filters_search_pagination_and_mail_metadata(self):
        future = await self.create(title="未来账单")
        past = await self.create(title="过期账单", due_at="2020-01-01T00:00:00Z")
        done = await self.create(title="完成事项", due_at=None, reminder_enabled=False)
        await self.api.set_todo_completion(self.request(self.admin, {"is_completed": True}), done["id"])
        await self.create(self.other, title="过期账单", due_at="2020-01-01T00:00:00Z")
        self.assertEqual((await self.list(status="pending"))["total"], 2)
        self.assertEqual((await self.list(status="completed"))["items"][0]["id"], done["id"])
        self.assertEqual((await self.list(status="overdue"))["items"][0]["id"], past["id"])
        self.assertEqual((await self.list(q="账单"))["total"], 2)
        self.assertEqual((await self.list(q="未来"))["items"][0]["id"], future["id"])
        listing = await self.list(page="2", size="1")
        self.assertEqual(listing["page"], 2)
        self.assertEqual(listing["size"], 1)
        self.assertEqual(len(listing["items"]), 1)
        self.assertEqual(listing["total"], 3)
        self.assertTrue(listing["email_configured"])
        self.assertNotIn("reminder_email", listing)
        with patch.object(self.api, "smtp_ready", return_value=False):
            self.assertFalse((await self.list())["email_configured"])
        for args in ({"status": "invalid"}, {"q": "x" * 201}, {"page": "0"},
                     {"page": "x"}, {"page": "1.2"}, {"size": "101"}, {"size": "0"},
                     {"page": "-1"}, {"size": ""}, {"q": 2}):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                await self.list(**args)

    async def test_reminder_email_changes_rearm_sent_delivery_and_normalize(self):
        saved = await self.create(reminder_email="  NewRecipient@Example.COM  ")
        self.assertEqual(saved["reminder_email"], "NewRecipient@example.com")
        sent_at = datetime.now(timezone.utc)
        await self.Todo.filter(id=saved["id"]).update(
            reminder_status="sent", reminder_sent_at=sent_at, reminder_attempts=1,
            reminder_claim_token="c" * 32, reminder_claim_until=self.due,
        )
        changed = self.data(await self.api.update_todo(self.request(
            self.admin, self.payload(reminder_email="new@example.com"),
        ), saved["id"]))
        self.assertEqual(changed["reminder_email"], "new@example.com")
        self.assertEqual(changed["reminder_status"], "pending")
        self.assertEqual(changed["reminder_attempts"], 0)
        self.assertIsNone(changed["reminder_sent_at"])
        row = await self.Todo.get(id=saved["id"])
        self.assertEqual(row.reminder_claim_token, "")
        self.assertIsNone(row.reminder_claim_until)

    async def test_safe_schema_generation_adds_todos_and_is_idempotent(self):
        await connections.get("default").execute_script("DROP TABLE todos")
        await Tortoise.generate_schemas(safe=True)
        saved = await self.create()
        await Tortoise.generate_schemas(safe=True)
        self.assertEqual((await self.Todo.get(id=saved["id"])).title, saved["title"])
        self.assertTrue(await User.exists(id=self.admin.id))

    async def test_production_naive_storage_preserves_instants_and_query_cutoffs(self):
        saved = await self.create(due_at="2026-12-01T08:15:00+08:00")
        expected = datetime.fromisoformat("2026-12-01T00:15:00Z")
        row = await self.Todo.get(id=saved["id"])
        self.assertEqual(row.due_at, expected)
        self.assertEqual(row.reminder_next_attempt_at, expected)
        self.assertIsNotNone(row.created_at.utcoffset())
        self.assertIsNotNone(row.updated_at.utcoffset())
        self.assertFalse(await self.Todo.filter(
            id=row.id, due_at__lte=expected - timedelta(microseconds=1),
        ).exists())
        self.assertTrue(await self.Todo.filter(id=row.id, due_at__lte=expected).exists())
        self.assertTrue(await self.Todo.filter(
            id=row.id, reminder_next_attempt_at__lte=expected,
        ).exists())
        await self.Todo.filter(id=row.id).update(
            reminder_status="sent", reminder_sent_at=expected,
            reminder_claim_until=expected + timedelta(minutes=5),
        )
        changed = self.data(await self.api.update_todo(self.request(
            self.admin, self.payload(due_at=expected.isoformat()),
        ), row.id))
        self.assertEqual(changed["reminder_status"], "sent")
        self.assertEqual(datetime.fromisoformat(changed["reminder_sent_at"]), expected)
        self.assertTrue(await self.Todo.filter(id=row.id, reminder_sent_at=expected).exists())

    async def test_routes_are_admin_only(self):
        from app.api import register_blueprints
        app = Sanic("todo_routes", configure_logging=False)
        register_blueprints(app)
        app.router.finalize()
        routes = {(route.path, method) for route in app.router.routes for method in route.methods}
        for method in ("GET", "POST"):
            self.assertIn(("api/admin/todos", method), routes)
        for method in ("PUT", "DELETE"):
            self.assertIn(("api/admin/todos/<todo_id:int>", method), routes)
        self.assertIn(("api/admin/todos/<todo_id:int>/completion", "PATCH"), routes)
        self.assertIn(("api/admin/todos/<todo_id:int>/retry", "POST"), routes)
        self.assertFalse(any(path.startswith("api/todos") for path, _ in routes))


if __name__ == "__main__":
    unittest.main()
