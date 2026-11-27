"""Health probes never contact real services in the unit suite."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.api import health


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_does_not_probe_dependencies(self):
        with patch.object(health, "get_redis", side_effect=AssertionError("must not connect")):
            response = await health.live(None)
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.body)["data"]["status"], "ok")

    async def test_ready_reports_all_dependencies_and_legacy_fields(self):
        with patch.object(health, "_check_mysql", new=AsyncMock()), patch.object(
            health, "_check_redis", new=AsyncMock()
        ), patch.object(health, "_check_rabbitmq", new=AsyncMock()):
            for endpoint in (health.ready, health.health):
                response = await endpoint(None)
                body = json.loads(response.body)
                self.assertEqual(response.status, 200)
                self.assertEqual(body["code"], 0)
                self.assertEqual(body["data"], {"status": "ok", "redis": True, "checks": {
                    "mysql": True, "redis": True, "rabbitmq": True,
                }})

    async def test_each_dependency_failure_is_degraded_without_secret_leak(self):
        for failed in ("mysql", "redis", "rabbitmq"):
            with self.subTest(failed=failed), patch.object(
                health, "_check_mysql", new=AsyncMock(side_effect=RuntimeError("secret DSN") if failed == "mysql" else None)
            ), patch.object(
                health, "_check_redis", new=AsyncMock(side_effect=RuntimeError("secret DSN") if failed == "redis" else None)
            ), patch.object(
                health, "_check_rabbitmq", new=AsyncMock(side_effect=RuntimeError("secret DSN") if failed == "rabbitmq" else None)
            ):
                response = await health.ready(None)
                body = json.loads(response.body)
                self.assertEqual(response.status, 503)
                self.assertNotEqual(body["code"], 0)
                self.assertEqual(body["data"]["status"], "degraded")
                self.assertFalse(body["data"]["checks"][failed])
                self.assertNotIn("secret", response.body.decode())
                self.assertEqual(body["data"]["redis"], failed != "redis")

    async def test_timeout_is_bounded_and_checks_start_concurrently(self):
        started = set()
        gate = asyncio.Event()
        async def hanging(name):
            started.add(name)
            if len(started) == 3:
                gate.set()
            await asyncio.Future()
        with patch.object(health, "CHECK_TIMEOUT_SECONDS", 0.05), patch.object(
            health, "_check_mysql", new=lambda: hanging("mysql")
        ), patch.object(health, "_check_redis", new=lambda: hanging("redis")), patch.object(
            health, "_check_rabbitmq", new=lambda: hanging("rabbitmq")
        ):
            response = await asyncio.wait_for(health.ready(None), timeout=0.3)
        self.assertTrue(gate.is_set())
        self.assertEqual(response.status, 503)
        self.assertEqual(json.loads(response.body)["data"]["checks"], dict.fromkeys(started, False))

    async def test_dependency_can_recover_on_next_request(self):
        with patch.object(health, "_check_mysql", new=AsyncMock(side_effect=[RuntimeError(), None])), patch.object(
            health, "_check_redis", new=AsyncMock()
        ), patch.object(health, "_check_rabbitmq", new=AsyncMock()):
            self.assertEqual((await health.ready(None)).status, 503)
            self.assertEqual((await health.ready(None)).status, 200)

    async def test_mysql_executes_read_only_query(self):
        connection = MagicMock(execute_query=AsyncMock())
        with patch.object(health, "connections", MagicMock(get=MagicMock(return_value=connection))):
            await health._check_mysql()
        connection.execute_query.assert_awaited_once_with("SELECT 1")

    async def test_redis_requires_successful_ping(self):
        with patch.object(health, "get_redis", return_value=MagicMock(ping=AsyncMock(return_value=False))):
            with self.assertRaises(RuntimeError):
                await health._check_redis()

    async def test_rabbitmq_connects_and_releases_without_queues_or_messages(self):
        connection = MagicMock()
        with patch.object(health, "Connection", return_value=connection):
            await health._check_rabbitmq()
        connection.ensure_connection.assert_called_once_with(max_retries=0)
        connection.release.assert_called_once_with()
        self.assertFalse(connection.channel.called)
        self.assertFalse(connection.Producer.called)

    async def test_rabbitmq_releases_failed_connection(self):
        connection = MagicMock()
        connection.ensure_connection.side_effect = OSError("broker secret")
        with patch.object(health, "Connection", return_value=connection):
            with self.assertRaises(OSError):
                await health._check_rabbitmq()
        connection.release.assert_called_once_with()

    async def test_legacy_health_does_not_claim_healthy_on_redis_failure(self):
        with patch.object(health, "_check_mysql", new=AsyncMock()), patch.object(health, "_check_rabbitmq", new=AsyncMock()), patch.object(health, "get_redis", return_value=MagicMock(ping=AsyncMock(side_effect=OSError("offline")))):
            response = await health.health(None)
        self.assertEqual(response.status, 503)
