"""Comment limiter Redis boundary: privacy, throttling and failure behavior."""
import importlib
import importlib.util
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
from redis.exceptions import ConnectionError as RedisConnectionError
from app.core.exceptions import APIError


class CommentRateLimitTests(unittest.IsolatedAsyncioTestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec("app.core.comment_rate_limit"), "Anonymous comment limiter is missing")
        return importlib.import_module("app.core.comment_rate_limit")

    async def test_allowed_submission_uses_single_atomic_call_with_hashed_ip(self):
        module = self.module()
        redis = SimpleNamespace(eval=AsyncMock(return_value=0))
        with patch.object(module, "get_redis", return_value=redis):
            await module.enforce_comment_rate_limit("203.0.113.42")
        args = redis.eval.await_args.args
        self.assertEqual(args[1], 1)
        self.assertNotIn("203.0.113.42", args[2])
        self.assertTrue(args[2].startswith("comment:rate:"))
        self.assertEqual(args[4:7], (30000, 600000, 5))

    async def test_exhausted_budget_returns_429(self):
        module = self.module()
        with patch.object(module, "get_redis", return_value=SimpleNamespace(eval=AsyncMock(return_value=30))):
            with self.assertRaises(APIError) as error:
                await module.enforce_comment_rate_limit("203.0.113.42")
        self.assertEqual(error.exception.status, 429)

    async def test_redis_connection_failure_and_uninitialized_redis_do_not_block_comment(self):
        module = self.module()
        with patch.object(module, "get_redis", return_value=SimpleNamespace(eval=AsyncMock(side_effect=RedisConnectionError("offline")))):
            await module.enforce_comment_rate_limit("203.0.113.42")
        with patch.object(module, "get_redis", side_effect=RuntimeError("Redis 尚未初始化")):
            await module.enforce_comment_rate_limit("203.0.113.42")

    async def test_programming_error_is_not_swallowed_as_redis_outage(self):
        module = self.module()
        with patch.object(module, "get_redis", return_value=SimpleNamespace(eval=AsyncMock(side_effect=ValueError("bad script input")))):
            with self.assertRaisesRegex(ValueError, "bad script input"):
                await module.enforce_comment_rate_limit("203.0.113.42")
