"""Login overload, privacy and dependency failures."""
import asyncio
import json
import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from app.api import auth
from app.core.exceptions import UnauthorizedError

class LoginProtectionTests(unittest.IsolatedAsyncioTestCase):
    def request(self):
        return SimpleNamespace(json={'username': 'Admin', 'password': 'private-password'}, ip='203.0.113.4', headers={})

    async def test_blocked_login_returns_cooldown_without_database_access(self):
        from app.core import login_rate_limit as limiter
        with patch.object(limiter, 'get_redis', return_value=SimpleNamespace(eval=AsyncMock(return_value=42))), patch.object(auth.User, 'get_or_none', new=AsyncMock()) as query:
            response = await auth.login(self.request())
        self.assertEqual(response.status, 429)
        self.assertEqual(response.headers['Retry-After'], '42')
        self.assertNotEqual(json.loads(response.body)['code'], 0)
        query.assert_not_awaited()

    async def test_redis_unavailable_fails_closed_without_secrets(self):
        from app.core import login_rate_limit as limiter
        with patch.object(limiter, 'get_redis', side_effect=RuntimeError('redis://private-secret')), patch.object(auth.User, 'get_or_none', new=AsyncMock()) as query:
            response = await auth.login(self.request())
        self.assertEqual(response.status, 503)
        self.assertNotIn('private', response.body.decode())
        query.assert_not_awaited()

    async def test_failures_keep_reservation_and_inactive_account_is_generic(self):
        from app.core import login_rate_limit as limiter
        redis = SimpleNamespace(eval=AsyncMock(return_value=0), delete=AsyncMock())
        for user in (None, SimpleNamespace(password_hash='hash', is_active=False)):
            with patch.object(limiter, 'get_redis', return_value=redis), patch.object(auth.User, 'get_or_none', new=AsyncMock(return_value=user)), patch.object(auth, 'verify_password', return_value=True):
                with self.assertRaises(UnauthorizedError) as caught:
                    await auth.login(self.request())
                self.assertEqual(str(caught.exception), 'invalid username or password')
        redis.delete.assert_not_awaited()

    async def test_success_clears_only_account_and_hashes_identifiers(self):
        from app.core import login_rate_limit as limiter
        redis = SimpleNamespace(eval=AsyncMock(return_value=0), delete=AsyncMock())
        user = SimpleNamespace(id=1, username='Admin', password_hash='hash', is_active=True, is_admin=True, email='admin@example.com', nickname='', avatar='', bio='', created_at=datetime(2026, 1, 1))
        with patch.object(limiter, 'get_redis', return_value=redis), patch.object(auth.User, 'get_or_none', new=AsyncMock(return_value=user)), patch.object(auth, 'verify_password', return_value=True), patch.object(auth, 'create_access_token', return_value='test-token'):
            response = await auth.login(self.request())
        self.assertEqual(response.status, 200)
        args = redis.eval.call_args.args
        self.assertEqual(args[1], 2)
        for key in args[2:4]:
            self.assertNotIn('Admin', key)
            self.assertNotIn('203.0.113.4', key)
        redis.delete.assert_awaited_once_with(args[2])

    async def test_trusted_proxy_and_case_variants_share_limit(self):
        from app.core import login_rate_limit as limiter
        from app.core.config import settings
        import hashlib
        redis = SimpleNamespace(eval=AsyncMock(return_value=0))
        request = self.request()
        request.ip = '127.0.0.1'
        request.headers = {'X-Forwarded-For': '203.0.113.8'}
        with patch.object(limiter, 'get_redis', return_value=redis), patch.object(settings, 'TRUSTED_PROXY_CIDRS', '127.0.0.0/8'):
            await limiter.reserve_login('Ádmin', request)
            first = redis.eval.call_args.args
            await limiter.reserve_login('admin', request)
            second = redis.eval.call_args.args
        self.assertEqual(first[2], second[2])
        self.assertTrue(first[3].endswith(hashlib.sha256(b'203.0.113.8').hexdigest()))

@unittest.skipUnless(os.getenv('REDIS_LOGIN_TEST_URL'), 'set isolated REDIS_LOGIN_TEST_URL for real Lua concurrency checks')
class LoginLuaIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from redis.asyncio import from_url
        from uuid import uuid4
        self.redis = from_url(os.environ['REDIS_LOGIN_TEST_URL'], decode_responses=True)
        self.keys = ['test:login:' + uuid4().hex + ':' + kind for kind in ('account', 'ip')]

    async def asyncTearDown(self):
        await self.redis.delete(*self.keys)
        await self.redis.aclose()

    async def reserve(self, maximum=5, window=900):
        from app.core.login_rate_limit import RESERVE_SCRIPT
        return await self.redis.eval(RESERVE_SCRIPT, 2, *self.keys, window, maximum, 30)

    async def test_concurrent_failures_allow_only_five(self):
        results = await asyncio.gather(*(self.reserve() for _ in range(20)))
        self.assertEqual(results.count(0), 5)
        self.assertTrue(all(value > 0 for value in results if value != 0))
        self.assertLessEqual(await self.redis.ttl(self.keys[0]), 900)

    async def test_success_reset_preserves_ip_budget(self):
        for _ in range(30):
            self.assertEqual(await self.reserve(), 0)
            await self.redis.delete(self.keys[0])
        self.assertGreater(await self.reserve(), 0)

    async def test_expiry_allows_login_again(self):
        self.assertEqual(await self.reserve(maximum=1, window=1), 0)
        self.assertGreater(await self.reserve(maximum=1, window=1), 0)
        await asyncio.sleep(1.1)
        self.assertEqual(await self.reserve(maximum=1, window=1), 0)

class LoginDependencyFailures(unittest.IsolatedAsyncioTestCase):
    async def test_redis_timeout_does_not_allow_login(self):
        from app.core import login_rate_limit as limiter
        async def stalled(*args):
            await asyncio.sleep(10)
        redis = SimpleNamespace(eval=stalled)
        with patch.object(limiter, 'get_redis', return_value=redis), patch.object(limiter, 'REDIS_TIMEOUT_SECONDS', 0.001):
            with self.assertRaises(limiter.LoginProtectionUnavailable):
                await limiter.reserve_login('admin', SimpleNamespace(ip='203.0.113.4', headers={}))

    async def test_clear_failure_does_not_issue_token(self):
        from app.core import login_rate_limit as limiter
        redis = SimpleNamespace(eval=AsyncMock(return_value=0), delete=AsyncMock(side_effect=ConnectionError('sensitive redis URI')))
        user = SimpleNamespace(id=1, password_hash='hash', is_active=True, is_admin=True)
        request = SimpleNamespace(json={'username': 'admin', 'password': 'password'}, ip='203.0.113.4', headers={})
        with patch.object(limiter, 'get_redis', return_value=redis), patch.object(auth.User, 'get_or_none', new=AsyncMock(return_value=user)), patch.object(auth, 'verify_password', return_value=True), patch.object(auth, 'create_access_token') as token:
            response = await auth.login(request)
        self.assertEqual(response.status, 503)
        self.assertNotIn('sensitive', response.body.decode())
        token.assert_not_called()
