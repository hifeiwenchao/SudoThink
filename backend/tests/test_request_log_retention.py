"""Seven-day retention and aware time filters against a real database."""
import importlib
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "request-log-tests-only-32-byte-secret")

from tortoise import Tortoise
from app.core.exceptions import ValidationError
from app.core.security import create_access_token
from app.models.api_request_log import ApiRequestLog
from app.models.user import User


class RetentionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]},
                            use_tz=False, timezone="Asia/Shanghai")
        await Tortoise.generate_schemas()
        self.admin = await User.create(username="log-admin", email="log@example.com", password_hash="unused", is_admin=True)

    async def asyncTearDown(self):
        await Tortoise.close_connections()

    async def record(self, when):
        row = await ApiRequestLog.create(method="GET", url="/api/articles", path="/api/articles",
                                         status_code=200, duration_ms=1)
        # Emulate the application's existing naive Shanghai database timestamps.
        from zoneinfo import ZoneInfo
        wall = when.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
        await ApiRequestLog.filter(id=row.id).update(created_at=wall)
        return row

    async def test_seven_day_cutoff_is_strict_batched_and_repeatable(self):
        module = importlib.import_module("app.core.request_log_retention")
        now = datetime(2026, 11, 24, 4, tzinfo=timezone.utc)
        cutoff = now - timedelta(days=7)
        old = [await self.record(cutoff - timedelta(seconds=n)) for n in (1, 2, 3)]
        boundary = await self.record(cutoff)
        recent = await self.record(cutoff + timedelta(seconds=1))
        result = await module.cleanup_request_logs(now=now, batch_size=2)
        self.assertEqual(result["deleted"], 3)
        self.assertFalse(await ApiRequestLog.filter(id__in=[row.id for row in old]).exists())
        self.assertEqual(set(await ApiRequestLog.all().values_list("id", flat=True)), {boundary.id, recent.id})
        self.assertEqual((await module.cleanup_request_logs(now=now))["deleted"], 0)

    async def test_aware_inclusive_range_uses_database_timezone(self):
        api = importlib.import_module("app.api.admin.request_logs")
        for hour in (3, 4, 5):
            await self.record(datetime(2026, 11, 24, hour, tzinfo=timezone.utc))
        args = {"created_from": "2026-11-24T12:00:00+08:00", "created_to": "2026-11-24T05:00:00Z"}
        req = SimpleNamespace(headers={"Authorization": "Bearer " + create_access_token(self.admin.id)},
                              ctx=SimpleNamespace(), get_args=lambda **kw: args)
        response = await api.list_request_logs(req)
        self.assertEqual(json.loads(response.body)["data"]["total"], 2)
        for invalid in ({"created_from": "invalid"}, {"created_to": "2026-11-24"},
                        {"created_from": "2026-11-24T06:00:00Z", "created_to": "2026-11-24T05:00:00Z"}):
            req.get_args = lambda **kw: invalid
            with self.assertRaises(ValidationError):
                await api.list_request_logs(req)

    def test_cleanup_task_is_discovered_and_scheduled_hourly(self):
        from app.celery_app import celery_app
        celery_app.loader.import_default_modules()
        matches = [entry for entry in celery_app.conf.beat_schedule.values()
                   if entry["task"] == "app.tasks.request_logs.cleanup_request_logs"]
        self.assertEqual(len(matches), 1)
        self.assertLessEqual(matches[0]["schedule"], 3600)
        self.assertIn(matches[0]["task"], celery_app.tasks)
