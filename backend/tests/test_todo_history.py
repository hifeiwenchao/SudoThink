"""Reminder history follows successful state changes and stays owner-private."""
import importlib
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "todo-history-only-long-testing-secret")

from tortoise import Tortoise
from app.core.exceptions import NotFoundError
from app.core.security import create_access_token
from app.models.todo import Todo
from app.models.user import User

NOW = datetime(2026, 11, 24, 4, tzinfo=timezone.utc)


class TodoHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]},
                            use_tz=False, timezone="Asia/Shanghai")
        await Tortoise.generate_schemas()
        self.owner = await User.create(username="history", email="history@example.com", password_hash="unused", is_admin=True)
        self.other = await User.create(username="other", email="other@example.com", password_hash="unused", is_admin=True)
        self.api = importlib.import_module("app.api.admin.todos")
        self.reminders = importlib.import_module("app.core.todo_reminders")
        self.todo = await Todo.create(owner=self.owner, title="检查", due_at=None, reminder_enabled=True,
                                     reminder_email="owner@example.com", reminder_repeat="cron", reminder_cron="0 12 * * *",
                                     reminder_next_run_at=NOW, reminder_next_attempt_at=NOW, reminder_status="pending")
        self.config = SimpleNamespace(SMTP_HOST="smtp.example.com", SMTP_PORT=465, SMTP_SECURITY="ssl", SMTP_USERNAME="sender@example.com",
                                      SMTP_PASSWORD="unused", SMTP_FROM_EMAIL="", SMTP_FROM_NAME="Blog", SMTP_TIMEOUT_SECONDS=15)

    async def asyncTearDown(self):
        await Tortoise.close_connections()

    def request(self, owner=None, body=None, args=None):
        return SimpleNamespace(headers={"Authorization": "Bearer " + create_access_token((owner or self.owner).id),
                                        "Content-Type": "application/json"}, ctx=SimpleNamespace(), json=body,
                               get_args=lambda **kw: args or {})

    async def history(self, owner=None):
        handler = getattr(self.api, "list_todo_history", None)
        self.assertIsNotNone(handler, "Todo history endpoint missing")
        result = await handler(self.request(owner), self.todo.id)
        return json.loads(result.body)["data"]

    async def test_delivery_attempts_record_results_without_private_message_fields(self):
        from app.core.mail import MailDeliveryError
        with patch.object(self.reminders, "send_mail", side_effect=MailDeliveryError("邮件发送失败")):
            await self.reminders.process_due_reminders(now=NOW, config=self.config)
        with patch.object(self.reminders, "send_mail"):
            await self.reminders.process_due_reminders(now=NOW + timedelta(minutes=1), config=self.config)
        page = await self.history()
        self.assertEqual(page["total"], 2)
        self.assertEqual([row["event"] for row in page["items"]], ["sent", "failed"])
        self.assertEqual(page["items"][0]["error"], "")
        self.assertEqual(datetime.fromisoformat(page["items"][0]["scheduled_at"]), NOW)
        self.assertNotIn("owner@example.com", json.dumps(page))
        self.assertNotIn("claim", json.dumps(page))
        with self.assertRaises(NotFoundError):
            await self.history(self.other)

    async def test_skip_history_and_stale_worker_do_not_create_false_delivery(self):
        revision, token = await self.reminders.claim_reminder(self.todo.id, now=NOW)
        with patch.object(self.api, "datetime") as clock:
            clock.now.return_value = NOW
            await self.api.skip_todo_period(self.request(body={"period": "month"}), self.todo.id)
        with patch.object(self.reminders, "send_mail") as transport:
            result = await self.reminders.deliver_reminder(self.todo.id, revision, token, now=NOW, config=self.config)
        self.assertEqual(result, "skipped")
        transport.assert_not_called()
        page = await self.history()
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["event"], "skipped")
        self.assertEqual(page["items"][0]["period"], "month")
        self.assertEqual(datetime.fromisoformat(page["items"][0]["next_run_at"]), datetime(2026, 12, 1, 4, tzinfo=timezone.utc))
        model = importlib.import_module("app.models.todo_history").TodoReminderHistory
        await self.todo.delete()
        self.assertEqual(await model.all().count(), 0)

    async def test_history_insert_failure_rolls_back_outcome_and_skip(self):
        model = importlib.import_module("app.models.todo_history").TodoReminderHistory
        revision, token = await self.reminders.claim_reminder(self.todo.id, now=NOW)
        with patch.object(model, "create", side_effect=RuntimeError("database write failed")), patch.object(self.reminders, "send_mail"):
            with self.assertRaises(RuntimeError):
                await self.reminders.deliver_reminder(self.todo.id, revision, token, now=NOW, config=self.config)
        await self.todo.refresh_from_db()
        self.assertEqual(self.todo.reminder_status, "sending")
        with patch.object(model, "create", side_effect=RuntimeError("database write failed")):
            with self.assertRaises(RuntimeError):
                await self.api.skip_todo_period(self.request(body={"period": "month"}), self.todo.id)
        await self.todo.refresh_from_db()
        self.assertEqual(self.todo.reminder_revision, revision)

    async def test_stale_smtp_result_does_not_record_a_success(self):
        revision, token = await self.reminders.claim_reminder(self.todo.id, now=NOW)
        async def edit_during_send(*args, **kwargs):
            await Todo.filter(id=self.todo.id).update(reminder_revision=revision + 1,
                                                      reminder_status="pending", reminder_claim_token="")
        with patch.object(self.reminders.asyncio, "to_thread", side_effect=edit_during_send):
            result = await self.reminders.deliver_reminder(self.todo.id, revision, token, now=NOW, config=self.config)
        self.assertEqual(result, "skipped")
        self.assertEqual((await self.history())["total"], 0)
