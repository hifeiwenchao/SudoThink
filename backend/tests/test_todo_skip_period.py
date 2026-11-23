"""Skipping a calendar period keeps recurring rules and invalidates old delivery work."""
import importlib
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "todo-tests-only-32-byte-secret-value")

from sanic import Sanic
from tortoise import Tortoise

from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from app.core.mail import MailDeliveryError
from app.core.security import create_access_token
from app.models.todo import Todo
from app.models.user import User


NOW = datetime.fromisoformat("2026-11-01T00:00:00Z")
NEXT_MONTH = datetime.fromisoformat("2026-12-01T01:00:00Z")


class TodoSkipPeriodTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.api = importlib.import_module("app.api.admin.todos")
        self.reminders = importlib.import_module("app.core.todo_reminders")
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
        self.config = SimpleNamespace(
            SMTP_HOST="smtp.example.com", SMTP_PORT=465, SMTP_SECURITY="ssl",
            SMTP_USERNAME="sender@example.com", SMTP_PASSWORD="test-only-password",
            SMTP_FROM_EMAIL="", SMTP_FROM_NAME="SudoThink", SMTP_TIMEOUT_SECONDS=15,
        )
        self.messages = []
        self.transport = patch.object(
            self.reminders, "send_mail", side_effect=lambda *args, **kwargs: self.messages.append(args),
        )
        self.transport.start()

    async def asyncTearDown(self):
        self.transport.stop()
        await Tortoise.close_connections()

    async def create(self, **overrides):
        return await Todo.create(**(dict(
            owner=self.admin, title="月初检查", content="检查账单", due_at=None,
            reminder_enabled=True, reminder_email="reminder@example.com", reminder_repeat="cron",
            reminder_cron="0 9 1,2,3 * *", reminder_timezone="Asia/Shanghai",
            reminder_next_run_at=NOW + timedelta(hours=1),
            reminder_next_attempt_at=NOW + timedelta(hours=1), reminder_status="pending",
        ) | overrides))

    def request(self, user, payload=None, content_type="application/json"):
        headers = {"Content-Type": content_type}
        if user is not None:
            headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
        return SimpleNamespace(headers=headers, ctx=SimpleNamespace(), json=payload)

    def handler(self, preview=False):
        name = "preview_todo_skip_period" if preview else "skip_todo_period"
        handler = getattr(self.api, name, None)
        self.assertIsNotNone(handler, f"Missing skip-period handler: {name}")
        return handler

    async def skip(self, todo, period="month", *, now=NOW, preview=False):
        with patch.object(self.api, "datetime") as clock:
            clock.now.return_value = now
            response = await self.handler(preview)(self.request(self.admin, {"period": period}), todo.id)
        body = json.loads(response.body)
        self.assertEqual(body["code"], 0)
        return body["data"]

    async def test_month_preview_uses_real_current_period_and_does_not_write(self):
        todo = await self.create(reminder_sent_at=NOW - timedelta(days=1))
        before = await Todo.filter(id=todo.id).values()
        result = await self.skip(todo, preview=True)
        self.assertEqual(result, {
            "period": "month", "timezone": "Asia/Shanghai",
            "period_ends_at": "2026-12-01T00:00:00+08:00",
            "next_run_at": "2026-12-01T09:00:00+08:00",
            "reminder_revision": todo.reminder_revision,
        })
        self.assertEqual(await Todo.filter(id=todo.id).values(), before)

    async def test_skip_month_avoids_second_and_third_then_resumes_original_cron_next_month(self):
        todo = await self.create()
        result = await self.skip(todo)
        self.assertEqual(datetime.fromisoformat(result["reminder_next_run_at"]), NEXT_MONTH)
        self.assertTrue(result["reminder_enabled"])
        self.assertFalse(result["is_completed"])
        self.assertEqual(result["reminder_cron"], "0 9 1,2,3 * *")
        for when in ("2026-11-01T01:00:00Z", "2026-11-02T01:00:00Z", "2026-11-03T01:00:00Z"):
            await self.reminders.process_due_reminders(now=datetime.fromisoformat(when), config=self.config)
        self.assertEqual(self.messages, [])
        await self.reminders.process_due_reminders(now=NEXT_MONTH, config=self.config)
        await todo.refresh_from_db()
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(todo.reminder_next_run_at, datetime.fromisoformat("2026-12-02T01:00:00Z"))
        await self.reminders.process_due_reminders(
            now=datetime.fromisoformat("2026-12-02T01:00:00Z"), config=self.config,
        )
        await todo.refresh_from_db()
        self.assertEqual(len(self.messages), 2)
        self.assertEqual(todo.reminder_next_run_at, datetime.fromisoformat("2026-12-03T01:00:00Z"))

    async def test_period_boundaries_are_inclusive_in_saved_timezone(self):
        cases = (
            ("day", "2026-11-01T23:30:00Z", "Asia/Shanghai", "2026-11-03T00:00:00+08:00"),
            ("week", "2026-12-31T12:00:00Z", "Asia/Shanghai", "2027-01-04T00:00:00+08:00"),
            ("week", "2027-01-04T00:00:00+08:00", "Asia/Shanghai", "2027-01-11T00:00:00+08:00"),
            ("month", "2026-12-31T22:00:00Z", "America/New_York", "2027-01-01T00:00:00-05:00"),
            ("year", "2026-12-31T12:00:00Z", "Asia/Shanghai", "2027-01-01T00:00:00+08:00"),
            ("day", "2026-03-08T06:30:00Z", "America/New_York", "2026-03-09T00:00:00-04:00"),
            ("day", "2026-11-01T05:30:00Z", "America/New_York", "2026-11-02T00:00:00-05:00"),
        )
        for period, now, zone, expected in cases:
            with self.subTest(period=period, now=now, zone=zone):
                todo = await self.create(
                    reminder_cron="0 0 * * *", reminder_timezone=zone,
                    reminder_next_run_at=datetime.fromisoformat(now),
                )
                preview = await self.skip(todo, period, now=datetime.fromisoformat(now), preview=True)
                self.assertEqual(preview["period_ends_at"], expected)
                self.assertEqual(preview["next_run_at"], expected)

    async def test_dst_skipped_midnight_boundary_uses_first_valid_local_instant(self):
        todo = await self.create(
            reminder_cron="0 * * * *", reminder_timezone="America/Santiago",
            reminder_next_run_at=datetime.fromisoformat("2026-09-05T12:00:00-04:00"),
        )
        preview = await self.skip(todo, "day", now=datetime.fromisoformat("2026-09-05T12:00:00-04:00"), preview=True)
        self.assertEqual(preview["period_ends_at"], "2026-09-06T01:00:00-03:00")
        self.assertEqual(preview["next_run_at"], "2026-09-06T01:00:00-03:00")

    async def test_legacy_recurrences_keep_anchor_and_include_boundary(self):
        cases = (
            ("daily", "2026-10-30T00:00:00+08:00", "day", "2026-11-02T00:00:00+08:00"),
            ("monthly", "2026-01-31T09:00:00+08:00", "month", "2026-12-31T09:00:00+08:00"),
            ("yearly", "2024-02-29T09:00:00+08:00", "year", "2027-02-28T09:00:00+08:00"),
        )
        for repeat, anchor, period, expected in cases:
            with self.subTest(repeat=repeat):
                todo = await self.create(
                    due_at=datetime.fromisoformat(anchor), reminder_repeat=repeat, reminder_cron="",
                )
                result = await self.skip(todo, period)
                self.assertEqual(datetime.fromisoformat(result["reminder_next_run_at"]), datetime.fromisoformat(expected))
                await todo.refresh_from_db()
                self.assertEqual(todo.due_at, datetime.fromisoformat(anchor))

    async def test_repeated_clicks_and_shorter_period_never_move_next_run_backwards(self):
        todo = await self.create(reminder_cron="0 9 * * *")
        for period in ("year", "year", "month", "week", "day"):
            result = await self.skip(todo, period)
            self.assertEqual(datetime.fromisoformat(result["reminder_next_run_at"]), datetime.fromisoformat("2027-01-01T09:00:00+08:00"))
            preview = await self.skip(todo, period, preview=True)
            self.assertEqual(datetime.fromisoformat(preview["next_run_at"]), datetime.fromisoformat("2027-01-01T09:00:00+08:00"))

    async def test_submit_recomputes_current_period_instead_of_trusting_old_preview(self):
        todo = await self.create()
        await self.skip(todo, preview=True)
        result = await self.skip(todo, now=datetime.fromisoformat("2026-12-01T00:00:00Z"))
        self.assertEqual(datetime.fromisoformat(result["reminder_next_run_at"]), datetime.fromisoformat("2027-01-01T09:00:00+08:00"))

    async def test_matching_expected_boundary_accepts_equivalent_utc_instant(self):
        todo = await self.create()
        preview = await self.skip(todo, preview=True)
        expected = datetime.fromisoformat(preview["period_ends_at"]).astimezone(timezone.utc).isoformat()
        with patch.object(self.api, "datetime") as clock:
            clock.now.return_value = NOW
            response = await self.handler()(self.request(self.admin, {
                "period": "month", "expected_period_ends_at": expected,
            }), todo.id)
        self.assertEqual(json.loads(response.body)["code"], 0)
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_next_run_at, NEXT_MONTH)

    async def test_expired_expected_boundary_rejects_without_changing_plan(self):
        todo = await self.create()
        preview = await self.skip(todo, preview=True)
        before = await Todo.filter(id=todo.id).values()
        with patch.object(self.api, "datetime") as clock:
            clock.now.return_value = datetime.fromisoformat("2026-12-01T00:00:00Z")
            with self.assertRaisesRegex(ValidationError, "预览已过期，请重新确认"):
                await self.handler()(self.request(self.admin, {
                    "period": "month", "expected_period_ends_at": preview["period_ends_at"],
                }), todo.id)
        self.assertEqual(await Todo.filter(id=todo.id).values(), before)

    async def test_matching_revision_and_next_run_allow_confirmed_schedule(self):
        todo = await self.create()
        preview = await self.skip(todo, preview=True)
        with patch.object(self.api, "datetime") as clock:
            clock.now.return_value = NOW
            try:
                response = await self.handler()(self.request(self.admin, {
                    "period": "month", "expected_period_ends_at": preview["period_ends_at"],
                    "expected_reminder_revision": todo.reminder_revision,
                    "expected_next_run_at": "2026-12-01T01:00:00Z",
                }), todo.id)
            except ValidationError as exc:
                self.fail(f"The unchanged preview should be accepted: {exc}")
        self.assertEqual(json.loads(response.body)["code"], 0)
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_next_run_at, NEXT_MONTH)

    async def test_changed_cron_in_same_period_rejects_old_revision_without_writes(self):
        todo = await self.create()
        preview = await self.skip(todo, preview=True)
        with patch.object(self.api, "datetime") as clock:
            clock.now.return_value = NOW
            await self.api.update_todo(self.request(self.admin, dict(
                title=todo.title, content=todo.content, due_at=None, reminder_enabled=True,
                reminder_email=todo.reminder_email, reminder_repeat="cron",
                reminder_cron="0 10 1,2,3 * *", reminder_timezone=todo.reminder_timezone,
            )), todo.id)
            before = await Todo.filter(id=todo.id).values()
            with self.assertRaisesRegex(ValidationError, "预览已过期，请重新确认"):
                await self.handler()(self.request(self.admin, {
                    "period": "month", "expected_period_ends_at": preview["period_ends_at"],
                    "expected_reminder_revision": todo.reminder_revision,
                }), todo.id)
        self.assertEqual(await Todo.filter(id=todo.id).values(), before)

    async def test_advanced_next_run_without_new_revision_rejects_old_preview(self):
        todo = await self.create()
        preview = await self.skip(todo, preview=True)
        await Todo.filter(id=todo.id).update(
            reminder_next_run_at=NEXT_MONTH + timedelta(days=1),
            reminder_next_attempt_at=NEXT_MONTH + timedelta(days=1),
        )
        before = await Todo.filter(id=todo.id).values()
        self.assertEqual(before[0]["reminder_revision"], todo.reminder_revision)
        with patch.object(self.api, "datetime") as clock:
            clock.now.return_value = NOW
            with self.assertRaisesRegex(ValidationError, "预览已过期，请重新确认"):
                await self.handler()(self.request(self.admin, {
                    "period": "month", "expected_period_ends_at": preview["period_ends_at"],
                    "expected_next_run_at": preview["next_run_at"],
                }), todo.id)
        self.assertEqual(await Todo.filter(id=todo.id).values(), before)

    async def test_expected_revision_requires_positive_strict_integer(self):
        todo = await self.create()
        before = await Todo.filter(id=todo.id).values()
        for revision in (0, -1, "1", 1.0, True):
            with self.subTest(revision=revision), self.assertRaises(ValidationError):
                await self.handler()(self.request(self.admin, {
                    "period": "month", "expected_reminder_revision": revision,
                }), todo.id)
        self.assertEqual(await Todo.filter(id=todo.id).values(), before)

    async def test_skip_cancels_failed_retry_budget_and_keeps_delivery_history(self):
        todo = await self.create(
            reminder_status="failed", reminder_attempts=3, reminder_error="邮箱认证失败",
            reminder_sent_at=NOW - timedelta(days=1), reminder_next_attempt_at=None,
        )
        revision = todo.reminder_revision
        await self.skip(todo)
        await todo.refresh_from_db()
        self.assertEqual((todo.reminder_status, todo.reminder_attempts, todo.reminder_error), ("pending", 0, ""))
        self.assertEqual(todo.reminder_sent_at, NOW - timedelta(days=1))
        self.assertEqual(todo.reminder_next_attempt_at, NEXT_MONTH)
        self.assertGreater(todo.reminder_revision, revision)
        await self.reminders.process_due_reminders(now=NOW + timedelta(minutes=5), config=self.config)
        self.assertEqual(self.messages, [])

    async def test_skip_during_pending_retry_cancels_old_attempt(self):
        todo = await self.create(
            reminder_next_run_at=NOW, reminder_next_attempt_at=NOW + timedelta(minutes=1),
            reminder_attempts=1, reminder_error="邮件发送失败",
        )
        await self.skip(todo)
        await self.reminders.process_due_reminders(now=NOW + timedelta(minutes=1), config=self.config)
        await todo.refresh_from_db()
        self.assertEqual((todo.reminder_attempts, todo.reminder_error), (0, ""))
        self.assertEqual(todo.reminder_next_attempt_at, NEXT_MONTH)
        self.assertEqual(self.messages, [])

    async def test_skip_invalidates_claim_before_old_worker_can_send(self):
        todo = await self.create(reminder_next_run_at=NOW, reminder_next_attempt_at=NOW)
        revision, token = await self.reminders.claim_reminder(todo.id, now=NOW)
        await self.skip(todo)
        result = await self.reminders.deliver_reminder(todo.id, revision, token, now=NOW, config=self.config)
        self.assertEqual(result, "skipped")
        self.assertEqual(self.messages, [])
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_claim_token, "")
        self.assertIsNone(todo.reminder_claim_until)
        self.assertEqual(todo.reminder_next_run_at, NEXT_MONTH)

    async def test_old_smtp_success_and_failure_cannot_overwrite_skipped_plan(self):
        for failed in (False, True):
            with self.subTest(failed=failed):
                todo = await self.create(reminder_next_run_at=NOW, reminder_next_attempt_at=NOW)
                revision, token = await self.reminders.claim_reminder(todo.id, now=NOW)

                async def skip_during_smtp(*args, **kwargs):
                    await self.skip(todo)
                    if failed:
                        raise MailDeliveryError("邮箱认证失败")

                with patch.object(self.reminders.asyncio, "to_thread", side_effect=skip_during_smtp):
                    result = await self.reminders.deliver_reminder(todo.id, revision, token, now=NOW, config=self.config)
                self.assertEqual(result, "skipped")
                await todo.refresh_from_db()
                self.assertEqual(todo.reminder_next_run_at, NEXT_MONTH)
                self.assertEqual(todo.reminder_next_attempt_at, NEXT_MONTH)
                self.assertEqual((todo.reminder_status, todo.reminder_attempts, todo.reminder_error), ("pending", 0, ""))
                self.assertIsNone(todo.reminder_sent_at)

    async def test_content_and_recipient_edits_preserve_skipped_schedule(self):
        todo = await self.create()
        await self.skip(todo)
        payload = dict(
            title=todo.title, content=todo.content, due_at=None, reminder_enabled=True,
            reminder_email=todo.reminder_email, reminder_repeat="cron",
            reminder_cron=todo.reminder_cron, reminder_timezone=todo.reminder_timezone,
        )
        for changes in ({"title": "新的标题"}, {"content": "更新详情"}, {"reminder_email": "new@example.com"}):
            await self.api.update_todo(self.request(self.admin, payload | changes), todo.id)
            await todo.refresh_from_db()
            self.assertEqual(todo.reminder_next_run_at, NEXT_MONTH)
            self.assertEqual(todo.reminder_next_attempt_at, NEXT_MONTH)

    async def test_skip_rejects_once_disabled_completed_and_invalid_payloads_without_writes(self):
        for changes in ({"reminder_repeat": "once"}, {"reminder_enabled": False}, {"is_completed": True}):
            todo = await self.create(**changes)
            before = await Todo.filter(id=todo.id).values()
            for preview in (False, True):
                with self.subTest(changes=changes, preview=preview), self.assertRaises(ValidationError):
                    await self.handler(preview)(self.request(self.admin, {"period": "month"}), todo.id)
            self.assertEqual(await Todo.filter(id=todo.id).values(), before)
        todo = await self.create()
        for payload in ({}, {"period": "quarter"}, {"period": None}, {"period": 1},
                        {"period": "month", "now": "2026-01-01T00:00:00Z"}, [], None):
            for preview in (False, True):
                with self.subTest(payload=payload, preview=preview), self.assertRaises(ValidationError):
                    await self.handler(preview)(self.request(self.admin, payload), todo.id)
        for preview in (False, True):
            with self.assertRaises(ValidationError):
                await self.handler(preview)(self.request(self.admin, {"period": "month"}, "text/plain"), todo.id)

    async def test_skip_requires_active_admin_and_owns_private_todo(self):
        todo = await self.create()
        for preview in (False, True):
            handler = self.handler(preview)
            for user, error in ((None, UnauthorizedError), (self.reader, ForbiddenError)):
                with self.subTest(user=user, preview=preview), self.assertRaises(error):
                    await handler(self.request(user, {"period": "month"}), todo.id)
            for todo_id in (todo.id, 99999):
                with self.assertRaises(NotFoundError):
                    await handler(self.request(self.other, {"period": "month"}), todo_id)
        self.admin.is_active = False
        await self.admin.save()
        for preview in (False, True):
            with self.assertRaises(UnauthorizedError):
                await self.handler(preview)(self.request(self.admin, {"period": "month"}), todo.id)

    async def test_skip_routes_are_registered_only_under_admin(self):
        from app.api import register_blueprints
        app = Sanic("todo_skip_routes", configure_logging=False)
        register_blueprints(app)
        app.router.finalize()
        routes = {(route.path, method) for route in app.router.routes for method in route.methods}
        for suffix in ("skip-period", "skip-period/preview"):
            self.assertIn((f"api/admin/todos/<todo_id:int>/{suffix}", "POST"), routes)
        self.assertFalse(any(path.startswith("api/todos") for path, _ in routes))


if __name__ == "__main__":
    unittest.main()
