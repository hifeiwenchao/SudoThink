"""微信网页分享签名接口测试。"""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from sanic import Sanic

from app.api import register_blueprints
from app.api.wechat import get_signature
from app.core.exceptions import APIError, ValidationError
from app.core import wechat


class FakeRedis:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.set_calls = []

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value
        self.set_calls.append((key, value, ex))
        return True


class WeChatSharingTests(unittest.IsolatedAsyncioTestCase):
    def request(self, url):
        return SimpleNamespace(args={"url": url})

    def data(self, response):
        body = json.loads(response.body)
        self.assertEqual(body["code"], 0)
        return body["data"]

    async def test_signature_uses_cached_ticket_without_network(self):
        redis = FakeRedis({"wechat:jsapi_ticket": "cached-ticket"})
        with patch.object(wechat, "get_redis", return_value=redis), patch.object(
            wechat, "_request_json", new=AsyncMock(side_effect=AssertionError("network call"))
        ), patch.object(wechat.settings, "WECHAT_APP_ID", "wx-test"), patch.object(
            wechat.settings, "WECHAT_APP_SECRET", "secret-test"
        ):
            result = self.data(await get_signature(self.request("https://www.example.com/articles/1")))
        self.assertEqual(result["app_id"], "wx-test")
        self.assertEqual(result["nonce_str"] and len(result["nonce_str"]) > 0, True)
        self.assertEqual(len(result["signature"]), 40)
        self.assertIsInstance(result["timestamp"], int)

    async def test_signature_fetches_and_caches_access_token_and_ticket(self):
        redis = FakeRedis()
        responses = [
            {"access_token": "access-token", "expires_in": 7200},
            {"errcode": 0, "ticket": "jsapi-ticket", "expires_in": 7200},
        ]
        with patch.object(wechat, "get_redis", return_value=redis), patch.object(
            wechat, "_request_json", new=AsyncMock(side_effect=responses)
        ) as fetch, patch.object(wechat.settings, "WECHAT_APP_ID", "wx-test"), patch.object(
            wechat.settings, "WECHAT_APP_SECRET", "secret-test"
        ):
            result = self.data(await get_signature(self.request("https://www.example.com/articles/2")))
        self.assertEqual(result["app_id"], "wx-test")
        self.assertEqual(redis.values["wechat:access_token"], "access-token")
        self.assertEqual(redis.values["wechat:jsapi_ticket"], "jsapi-ticket")
        self.assertEqual(fetch.await_count, 2)
        self.assertTrue(all(call[2] >= 60 for call in redis.set_calls))

    async def test_invalid_urls_are_rejected(self):
        for url in ("", "relative/path", "javascript:alert(1)", "https://example.com/#fragment"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                await get_signature(self.request(url))

    async def test_missing_wechat_credentials_return_a_safe_error(self):
        redis = FakeRedis()
        with patch.object(wechat, "get_redis", return_value=redis), patch.object(
            wechat.settings, "WECHAT_APP_ID", ""
        ), patch.object(wechat.settings, "WECHAT_APP_SECRET", ""):
            with self.assertRaises(APIError) as context:
                await get_signature(self.request("https://www.example.com/articles/1"))
        self.assertNotIn("secret", str(context.exception).lower())

    def test_route_is_registered(self):
        app = Sanic("wechat_routes", configure_logging=False)
        register_blueprints(app)
        app.router.finalize()
        routes = {(route.path, method) for route in app.router.routes for method in route.methods}
        self.assertIn(("api/wechat/signature", "GET"), routes)


if __name__ == "__main__":
    unittest.main()
