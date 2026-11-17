"""Due reminders against a real database; only external SMTP is replaced."""
import asyncio
import importlib
import importlib.util
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from tortoise import Tortoise

from app.core.mail import MailDeliveryError
from app.models.user import User


NOW = datetime(2026, 11, 17, 4, 0, tzinfo=timezone.utc)


def mail_config(**overrides):
    return SimpleNamespace(**(dict(
        SMTP_HOST="smtp.exmail.qq.com", SMTP_PORT=465, SMTP_SECURITY="ssl",
        SMTP_USERNAME="sender@example.com", SMTP_PASSWORD="test-only-password",
        SMTP_FROM_EMAIL="", SMTP_FROM_NAME="SudoThink",
        SMTP_TIMEOUT_SECONDS=15, CELERY_TIMEZONE="Asia/Shanghai",
    ) | overrides))


class TodoReminderTests(unittest.IsolatedAsyncioTestCase):
    use_tz = True
    db_timezone = "UTC"

    async def asyncSetUp(self):
        self.assertIsNotNone(importlib.util.find_spec("app.core.todo_reminders"), "Reminder processor is missing")
        self.reminders = importlib.import_module("app.core.todo_reminders")
        self.Todo = importlib.import_module("app.models.todo").Todo
        await Tortoise.init(
            db_url="sqlite://:memory:", modules={"models": ["app.models"]},
            use_tz=self.use_tz, timezone=self.db_timezone,
        )
        await Tortoise.generate_schemas()
        self.owner = await User.create(
            username="admin", email="admin@example.com", password_hash="unused", is_admin=True,
        )
        self.config = mail_config()
        self.messages = []

        def record(subject, body, recipient, **kwargs):
            self.messages.append((subject, body, recipient))

        self.transport = patch.object(self.reminders, "send_mail", side_effect=record)
        self.transport.start()

    async def asyncTearDown(self):
        if hasattr(self, "transport"):
            self.transport.stop()
            await Tortoise.close_connections()

    async def create(self, **overrides):
        values = dict(
            owner=self.owner, title="续费提醒", content="给域名续费。",
            reminder_email="reminder@example.com",
            due_at=NOW, reminder_enabled=True, reminder_status="pending",
            reminder_next_attempt_at=NOW,
        ) | overrides
        values.setdefault("reminder_next_run_at", values["due_at"])
        return await self.Todo.create(**values)

    async def scan(self, now=NOW):
        return await self.reminders.process_due_reminders(now=now, config=self.config)

    async def test_due_mail_sent_once_with_title_content_and_local_due_time(self):
        todo = await self.create()
        await self.scan()
        await self.scan(NOW + timedelta(minutes=10))
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_status, "sent")
        self.assertEqual(todo.reminder_attempts, 1)
        self.assertIsNotNone(todo.reminder_sent_at)
        self.assertEqual(len(self.messages), 1)
        subject, body, recipient = self.messages[0]
        self.assertIn("续费提醒", subject)
        self.assertIn("给域名续费。", body)
        self.assertIn("2026-11-17 12:00", body)
        self.assertEqual(recipient, "reminder@example.com")

    async def test_future_completed_disabled_or_inactive_owner_are_not_sent(self):
        await self.create(due_at=NOW + timedelta(hours=1), reminder_next_attempt_at=NOW + timedelta(hours=1))
        await self.create(is_completed=True)
        await self.create(reminder_enabled=False)
        inactive = await User.create(
            username="inactive", email="inactive@example.com", password_hash="unused", is_admin=True, is_active=False,
        )
        await self.create(owner=inactive)
        ordinary = await User.create(username="reader", email="reader@example.com", password_hash="unused")
        await self.create(owner=ordinary)
        await self.scan()
        self.assertEqual(self.messages, [])

    async def test_unconfigured_mail_keeps_due_reminder_without_consuming_attempt(self):
        todo = await self.create()
        self.config.SMTP_PASSWORD = ""
        await self.scan()
        await todo.refresh_from_db()
        self.assertEqual((todo.reminder_status, todo.reminder_attempts), ("pending", 0))
        self.assertEqual(self.messages, [])

    async def test_mail_failure_has_bounded_retries_and_safe_error(self):
        todo = await self.create()
        with patch.object(self.reminders, "send_mail", side_effect=MailDeliveryError("邮箱认证失败")):
            await self.scan()
            await todo.refresh_from_db()
            self.assertEqual((todo.reminder_status, todo.reminder_attempts), ("pending", 1))
            self.assertEqual(todo.reminder_next_attempt_at, NOW + timedelta(minutes=1))
            await self.scan(NOW + timedelta(seconds=59))
            await todo.refresh_from_db()
            self.assertEqual(todo.reminder_attempts, 1)
            await self.scan(NOW + timedelta(minutes=1))
            await todo.refresh_from_db()
            self.assertEqual(todo.reminder_attempts, 2)
            self.assertEqual(todo.reminder_next_attempt_at, NOW + timedelta(minutes=6))
            await self.scan(NOW + timedelta(minutes=6))
            await todo.refresh_from_db()
            self.assertEqual((todo.reminder_status, todo.reminder_attempts), ("failed", 3))
            self.assertEqual(todo.reminder_error, "邮箱认证失败")
            self.assertIsNone(todo.reminder_next_attempt_at)
            await self.scan(NOW + timedelta(days=1))
            await todo.refresh_from_db()
            self.assertEqual(todo.reminder_attempts, 3)

    async def test_expired_lease_is_recovered_but_active_lease_is_not(self):
        expired = await self.create(
            reminder_status="sending", reminder_claim_token="old", reminder_attempts=1,
            reminder_claim_until=NOW - timedelta(seconds=1),
        )
        active = await self.create(
            reminder_status="sending", reminder_claim_token="active", reminder_attempts=1,
            reminder_claim_until=NOW + timedelta(minutes=2),
        )
        await self.scan()
        await expired.refresh_from_db()
        await active.refresh_from_db()
        self.assertEqual((expired.reminder_status, expired.reminder_attempts), ("sent", 2))
        self.assertEqual((active.reminder_status, active.reminder_attempts), ("sending", 1))
        self.assertEqual(len(self.messages), 1)

    async def test_competing_claims_send_only_one_message(self):
        todo = await self.create()
        claims = await asyncio.gather(*[
            self.reminders.claim_reminder(todo.id, now=NOW) for _ in range(5)
        ])
        claims = [claim for claim in claims if claim]
        self.assertEqual(len(claims), 1)
        revision, token = claims[0]
        await self.reminders.deliver_reminder(todo.id, revision, token, now=NOW, config=self.config)
        await self.reminders.deliver_reminder(todo.id, revision, token, now=NOW, config=self.config)
        self.assertEqual(len(self.messages), 1)

    async def test_changed_completed_deleted_or_rescheduled_claim_cannot_send(self):
        for action in ("completed", "rescheduled", "disabled", "deleted"):
            with self.subTest(action=action):
                todo = await self.create()
                revision, token = await self.reminders.claim_reminder(todo.id, now=NOW)
                if action == "deleted":
                    await todo.delete()
                else:
                    updates = dict(reminder_revision=revision + 1, reminder_claim_token="")
                    if action == "completed":
                        updates["is_completed"] = True
                    elif action == "rescheduled":
                        updates["due_at"] = NOW + timedelta(days=1)
                    else:
                        updates["reminder_enabled"] = False
                    await self.Todo.filter(id=todo.id).update(**updates)
                result = await self.reminders.deliver_reminder(todo.id, revision, token, now=NOW, config=self.config)
                self.assertEqual(result, "skipped")
        self.assertEqual(self.messages, [])

    async def test_stale_smtp_result_does_not_overwrite_edited_reminder(self):
        todo = await self.create()
        revision, token = await self.reminders.claim_reminder(todo.id, now=NOW)
        next_due = NOW + timedelta(days=1)

        async def edit_during_send(*args, **kwargs):
            await self.Todo.filter(id=todo.id).update(
                due_at=next_due, reminder_next_attempt_at=next_due, reminder_revision=revision + 1,
                reminder_claim_token="", reminder_status="pending", reminder_attempts=0,
            )

        with patch.object(self.reminders.asyncio, "to_thread", side_effect=edit_during_send):
            await self.reminders.deliver_reminder(todo.id, revision, token, now=NOW, config=self.config)
        await todo.refresh_from_db()
        self.assertEqual((todo.reminder_status, todo.reminder_attempts), ("pending", 0))
        self.assertEqual(todo.due_at, next_due)
        self.assertIsNone(todo.reminder_sent_at)

    async def test_invalid_recipient_fails_one_item_without_preventing_other_reminders(self):
        bad = await self.create(reminder_email="bad-address")
        good = await self.create()
        await self.scan()
        await bad.refresh_from_db()
        await good.refresh_from_db()
        self.assertEqual(bad.reminder_status, "pending")
        self.assertIn("邮箱", bad.reminder_error)
        self.assertEqual(good.reminder_status, "sent")

    async def test_saved_recipient_is_used_instead_of_owner_email(self):
        self.owner.email = "owner@example.com"
        await self.owner.save()
        await self.create(reminder_email="chosen@example.com")
        await self.scan()
        self.assertEqual([message[2] for message in self.messages], ["chosen@example.com"])

    async def test_legacy_todo_without_recipient_waits_without_using_attempts(self):
        todo = await self.create(reminder_email="")
        await self.scan()
        await todo.refresh_from_db()
        self.assertEqual((todo.reminder_status, todo.reminder_attempts), ("pending", 0))
        self.assertEqual(self.messages, [])

    async def test_final_interrupted_attempt_stops_recovery_without_another_email(self):
        todo = await self.create(
            reminder_status="sending", reminder_claim_token="old", reminder_attempts=3,
            reminder_claim_until=NOW - timedelta(seconds=1),
        )
        await self.scan()
        await todo.refresh_from_db()
        self.assertEqual((todo.reminder_status, todo.reminder_attempts), ("failed", 3))
        self.assertIsNone(todo.reminder_claim_until)
        self.assertEqual(self.messages, [])

    async def test_recurring_success_rearms_next_day_and_resets_attempt_budget(self):
        todo = await self.create(reminder_repeat="daily", reminder_timezone="Asia/Shanghai")
        await self.scan()
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_status, "pending")
        self.assertEqual(todo.reminder_attempts, 0)
        self.assertEqual(todo.reminder_sent_at, NOW)
        self.assertEqual(todo.reminder_next_run_at, NOW + timedelta(days=1))
        self.assertEqual(todo.reminder_next_attempt_at, NOW + timedelta(days=1))
        self.assertEqual(todo.due_at, NOW)
        await self.scan(NOW + timedelta(hours=23))
        self.assertEqual(len(self.messages), 1)
        await self.scan(NOW + timedelta(days=1))
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_next_run_at, NOW + timedelta(days=2))
        self.assertEqual(len(self.messages), 2)
        self.assertIn("2026-11-18 12:00", self.messages[1][1])

    async def test_restart_catches_up_once_instead_of_sending_all_missed_occurrences(self):
        todo = await self.create(reminder_repeat="daily")
        later = NOW + timedelta(days=6, minutes=5)
        await self.scan(later)
        await self.scan(later + timedelta(minutes=1))
        await todo.refresh_from_db()
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(todo.reminder_next_run_at, NOW + timedelta(days=7))

    async def test_retry_does_not_advance_the_scheduled_occurrence_until_success(self):
        anchor = datetime.fromisoformat("2026-01-31T09:15:00+08:00")
        todo = await self.create(
            due_at=anchor, reminder_repeat="monthly", reminder_next_attempt_at=anchor,
        )
        with patch.object(self.reminders, "send_mail", side_effect=MailDeliveryError("发送失败")):
            await self.scan(anchor)
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_next_run_at, anchor)
        self.assertEqual(todo.reminder_attempts, 1)
        await self.scan(anchor + timedelta(minutes=1))
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_next_run_at, datetime.fromisoformat("2026-02-28T09:15:00+08:00"))
        self.assertEqual(todo.reminder_attempts, 0)
        await self.scan(datetime.fromisoformat("2026-02-28T09:15:00+08:00"))
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_next_run_at, datetime.fromisoformat("2026-03-31T09:15:00+08:00"))

    async def test_recurring_stale_delivery_cannot_advance_an_edited_schedule(self):
        todo = await self.create(reminder_repeat="daily")
        revision, token = await self.reminders.claim_reminder(todo.id, now=NOW)
        new_run = NOW + timedelta(hours=2)

        async def edit_during_send(*args, **kwargs):
            await self.Todo.filter(id=todo.id).update(
                reminder_next_run_at=new_run, reminder_next_attempt_at=new_run,
                reminder_revision=revision + 1, reminder_claim_token="", reminder_status="pending",
            )

        with patch.object(self.reminders.asyncio, "to_thread", side_effect=edit_during_send):
            await self.reminders.deliver_reminder(todo.id, revision, token, now=NOW, config=self.config)
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_next_run_at, new_run)
        self.assertIsNone(todo.reminder_sent_at)

    async def test_future_occurrence_is_not_sent_when_original_anchor_is_past(self):
        todo = await self.create(
            due_at=NOW - timedelta(days=1), reminder_repeat="daily",
            reminder_next_run_at=NOW + timedelta(days=1), reminder_next_attempt_at=NOW,
        )
        await self.scan()
        self.assertEqual(self.messages, [])
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_attempts, 0)

    async def test_next_occurrence_uses_delivery_finish_time_when_smtp_crosses_a_period(self):
        todo = await self.create(reminder_repeat="daily")
        revision, token = await self.reminders.claim_reminder(todo.id, now=NOW)
        finished = NOW + timedelta(days=1, minutes=1)
        with patch.object(self.reminders, "datetime") as clock:
            clock.now.side_effect = [NOW, finished]
            await self.reminders.deliver_reminder(todo.id, revision, token, config=self.config)
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_sent_at, finished)
        self.assertEqual(todo.reminder_next_run_at, NOW + timedelta(days=2))

    async def test_cron_without_legacy_date_rearms_at_next_matching_weekday(self):
        todo = await self.create(
            due_at=None, reminder_repeat="cron", reminder_cron="0 9 * * MON-FRI",
            reminder_next_run_at=NOW, reminder_next_attempt_at=NOW,
        )
        await self.scan()
        await todo.refresh_from_db()
        expected = datetime.fromisoformat("2026-11-18T09:00:00+08:00")
        self.assertEqual(todo.reminder_next_run_at, expected)
        self.assertEqual(todo.reminder_next_attempt_at, expected)
        self.assertEqual(todo.reminder_status, "pending")
        self.assertEqual(todo.reminder_attempts, 0)
        self.assertIsNone(todo.due_at)
        await self.scan()
        self.assertEqual(len(self.messages), 1)
        await self.scan(expected)
        self.assertEqual(len(self.messages), 2)
        self.assertIn("2026-11-18 09:00", self.messages[1][1])

    async def test_cron_downtime_only_catches_up_once_before_next_future_match(self):
        todo = await self.create(
            due_at=None, reminder_repeat="cron", reminder_cron="*/15 * * * *",
            reminder_next_run_at=NOW - timedelta(days=2), reminder_next_attempt_at=NOW - timedelta(days=2),
        )
        await self.scan()
        await self.scan(NOW + timedelta(minutes=1))
        await todo.refresh_from_db()
        self.assertEqual(len(self.messages), 1)
        self.assertEqual(todo.reminder_next_run_at, NOW + timedelta(minutes=15))

    async def test_cron_delivery_retry_preserves_the_occurrence_until_success(self):
        todo = await self.create(
            due_at=None, reminder_repeat="cron", reminder_cron="0 9 * * *",
            reminder_next_run_at=NOW, reminder_next_attempt_at=NOW,
        )
        with patch.object(self.reminders, "send_mail", side_effect=MailDeliveryError("发送失败")):
            await self.scan()
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_next_run_at, NOW)
        self.assertEqual(todo.reminder_attempts, 1)
        await self.scan(NOW + timedelta(minutes=1))
        await todo.refresh_from_db()
        self.assertEqual(todo.reminder_next_run_at, datetime.fromisoformat("2026-11-18T09:00:00+08:00"))
        self.assertEqual(todo.reminder_attempts, 0)


class ShanghaiNaiveStorageReminderTests(TodoReminderTests):
    """Production uses local naive DB timestamps, unlike Tortoise's default tests."""
    use_tz = False
    db_timezone = "Asia/Shanghai"


if __name__ == "__main__":
    unittest.main()
