"""CDN request signing, limits, safe errors, and administrator route access."""
import io
import json
import os
import threading
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "cdn-tests-only-32-byte-secret-value")

from tortoise import Tortoise

from app.api.admin import operations
from app.core import cdn
from app.core.exceptions import APIError, ForbiddenError, UnauthorizedError, ValidationError
from app.core.security import create_access_token
from app.models.user import User


def configured(**overrides):
    values = {
        "ACCESS_KEY_ID": "test-access-key-id",
        "ACCESS_KEY_SECRET": "test-access-key-secret",
        "OSS_SECURITY_TOKEN": "",
        "CDN_BASE_URL": "https://cdn.example.com",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CDNClientTests(unittest.IsolatedAsyncioTestCase):
    def test_rpc_post_signature_covers_special_characters_and_sts_token(self):
        request = cdn._signed_request(
            "RefreshObjectCaches", {
                "ObjectPath": "https://cdn.example.com/a%20b.js?x=1&y=~\nhttps://other.example.com/file.js",
                "ObjectType": "File",
            }, configured(OSS_SECURITY_TOKEN="test-token+/=~"),
            now=datetime(2026, 11, 13, tzinfo=timezone.utc), nonce="fixed-nonce",
        )
        fields = parse_qs(request.data.decode("ascii"))
        self.assertEqual(request.full_url, "https://cdn.aliyuncs.com/")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(fields["Signature"], ["8KDnRJrRj10A3MfMwr1Riq0GVJU="])
        self.assertEqual(fields["Version"], ["2018-05-10"])
        self.assertEqual(fields["SecurityToken"], ["test-token+/=~"])
        self.assertNotIn(b"test-access-key-secret", request.data)

    def test_config_never_returns_credentials_and_accepts_other_account_domains(self):
        result = cdn.get_cdn_configuration(configured(OSS_SECURITY_TOKEN="private-token"))
        self.assertTrue(result["enabled"])
        self.assertEqual(result["limits"]["refresh_regex"], 1)
        self.assertEqual(result["cdn_base_url"], "https://cdn.example.com")
        self.assertNotIn("private-token", json.dumps(result))
        self.assertNotIn("test-access-key", json.dumps(result))
        self.assertFalse(cdn.get_cdn_configuration(configured(ACCESS_KEY_SECRET=""))["enabled"])
        self.assertEqual(cdn.validate_cdn_urls(["https://other-account-domain.example.com/x"]), [
            "https://other-account-domain.example.com/x",
        ])

    def test_url_scope_type_and_batch_limits_fail_before_any_rpc(self):
        invalid = (
            [], "https://cdn.example.com/x", [None], ["https://cdn.example.com/a\nb"],
            ["file:///tmp/x"], ["https://user:password@cdn.example.com/x"],
            ["https://cdn.example.com/x#fragment"], ["https://cdn.example.com:443/x"],
            ["https://127.0.0.1/x"], ["https://cdn.*.com/x"],
            ["https://cdn.example.com/x", "https://cdn.example.com/x"],
            ["https://cdn.example.com/" + "x" * 1024],
            [f"https://cdn{i}.example.com/x" for i in range(11)],
            [f"https://cdn.example.com/x{i}" for i in range(1001)],
        )
        for urls in invalid:
            with self.subTest(urls=repr(urls)[:120]), self.assertRaises(ValueError):
                cdn.validate_cdn_urls(urls)
        for urls, object_type in (
            (["https://cdn.example.com/assets"], "Directory"),
            (["https://cdn.example.com/assets/?x=1"], "Directory"),
            (["https://cdn.example.com/a.*", "https://cdn.example.com/b.*"], "Regex"),
            (["https://cdn.example.com/assets/\\d+"], "Regex"),
            (["https://cdn.example.com/assets/(a|b)"], "Regex"),
            (["https://cdn.example.com/a"], []),
            (["https://cdn.example.com/a"], {}),
        ):
            with self.subTest(object_type=object_type), self.assertRaises(ValueError):
                cdn.validate_cdn_urls(urls, object_type=object_type)
        for url in ("https://cdn.example.com/", "https://cdn.example.com/assets/", "https://cdn.example.com/assets/.*.js"):
            with self.subTest(preload=url), self.assertRaises(ValueError):
                cdn.validate_cdn_urls([url], preload=True)
        self.assertEqual(cdn.validate_cdn_urls([
            "https://cdn.example.com/static/[0-9][a-z]/[^/]*.*.jpg",
        ], object_type="Regex"), ["https://cdn.example.com/static/[0-9][a-z]/[^/]*.*.jpg"])

    async def test_refresh_and_preload_map_only_supported_actions_off_event_loop(self):
        loop_thread = threading.get_ident()
        calls = []

        def rpc(action, arguments, config):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            calls.append((action, arguments))
            return {"RefreshTaskId": "123,124", "PushTaskId": "456", "RequestId": "request-1"}

        with patch.object(cdn, "_rpc", side_effect=rpc):
            result = await cdn.refresh_cdn_cache(["https://cdn.example.com/assets/"], object_type="Directory")
            self.assertEqual(result, {"task_id": "123,124", "request_id": "request-1"})
            await cdn.refresh_cdn_cache(["https://cdn.example.com/assets/.*.js"], object_type="Regex")
            preload = await cdn.preload_cdn_cache(["https://cdn.example.com/a.js", "https://cdn.example.com/b.js"])
            self.assertEqual(preload["task_id"], "456")
        self.assertEqual(calls, [
            ("RefreshObjectCaches", {"ObjectPath": "https://cdn.example.com/assets/", "ObjectType": "Directory"}),
            ("RefreshObjectCaches", {"ObjectPath": "https://cdn.example.com/assets/.*.js", "ObjectType": "Regex"}),
            ("PushObjectCache", {"ObjectPath": "https://cdn.example.com/a.js\nhttps://cdn.example.com/b.js"}),
        ])

    async def test_task_results_normalize_pagination_without_returning_unknown_fields(self):
        response = {"Tasks": {"CDNTask": [{
            "TaskId": "123", "ObjectPath": "https://cdn.example.com/a.js", "ObjectType": "file",
            "Status": "Complete", "Process": "100%", "CreationTime": "2026-11-13T00:00:00Z",
            "Description": "刷新成功",
            "Unexpected": "do not return",
        }]}, "TotalCount": "1", "RequestId": "request-2"}
        with patch.object(cdn, "_rpc", return_value=response) as rpc:
            result = await cdn.list_cdn_tasks(task_id="123", page=2, size=10)
        self.assertEqual(rpc.call_args.args[:2], ("DescribeRefreshTasks", {"TaskId": "123", "PageNumber": 2, "PageSize": 10}))
        self.assertEqual((result["total"], result["page"], result["size"]), (1, 2, 10))
        self.assertEqual(result["items"][0]["status"], "Complete")
        self.assertEqual(result["items"][0]["description"], "刷新成功")
        self.assertNotIn("Unexpected", result["items"][0])
        for task_id in ("123,124", "x\ny", ["123"]):
            with self.subTest(task_id=task_id), self.assertRaises(ValueError):
                await cdn.list_cdn_tasks(task_id=task_id)

    def test_upstream_errors_and_network_errors_never_echo_sensitive_content(self):
        for error in (
            HTTPError(cdn.CDN_ENDPOINT, 403, "upstream secret", {}, io.BytesIO(json.dumps({
                "Code": "InvalidAccessKeyId.NotFound", "Message": "test-access-key-secret private-token",
            }).encode())),
            URLError("test-access-key-secret private-token"),
        ):
            with self.subTest(error=type(error).__name__), patch.object(cdn, "build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(cdn.CDNError) as caught:
                    cdn._rpc("DescribeRefreshTasks", {}, configured())
                self.assertNotIn("test-access-key-secret", str(caught.exception))
                self.assertNotIn("private-token", str(caught.exception))
        self.assertEqual(cdn._upstream_error({"Code": "Throttling"}).status, 429)
        self.assertIsNone(cdn._NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example.com"))


class CDNRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.admin = await User.create(username="admin", email="admin@example.com", password_hash="unused", is_admin=True)
        self.reader = await User.create(username="reader", email="reader@example.com", password_hash="unused")
        self.inactive = await User.create(username="inactive", email="inactive@example.com", password_hash="unused", is_admin=True, is_active=False)
        patcher = patch.object(operations, "settings", configured())
        patcher.start()
        self.addCleanup(patcher.stop)

    async def asyncTearDown(self):
        await Tortoise.close_connections()

    def request(self, user=None, payload=None, args=None):
        headers = {"Content-Type": "application/json"}
        if user is not None:
            headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
        return SimpleNamespace(headers=headers, ctx=SimpleNamespace(), json=payload, args=args or {})

    def data(self, response):
        self.assertEqual(response.status, 200)
        return json.loads(response.body)["data"]

    async def test_all_endpoints_require_an_active_administrator_before_any_network_call(self):
        with patch.object(cdn, "_rpc", side_effect=AssertionError("unexpected CDN request")):
            for handler in (operations.get_config, operations.refresh, operations.preload, operations.tasks):
                for user, error in ((None, UnauthorizedError), (self.reader, ForbiddenError), (self.inactive, UnauthorizedError)):
                    with self.subTest(handler=handler.__name__, user=user), self.assertRaises(error):
                        await handler(self.request(user))

    async def test_refresh_preload_and_tasks_use_fixed_backend_operations(self):
        with patch.object(operations, "refresh_cdn_cache", new=AsyncMock(return_value={"task_id": "123", "request_id": "r1"})) as refresh:
            result = self.data(await operations.refresh(self.request(self.admin, {"urls": ["https://cdn.example.com/"], "object_type": "Directory"})))
            self.assertEqual(result["task_id"], "123")
            refresh.assert_awaited_once_with(urls=["https://cdn.example.com/"], object_type="Directory", config=operations.settings)
        with patch.object(operations, "preload_cdn_cache", new=AsyncMock(return_value={"task_id": "456", "request_id": "r2"})):
            self.assertEqual(self.data(await operations.preload(self.request(self.admin, {"urls": ["https://cdn.example.com/a.js"]})))["task_id"], "456")
        with patch.object(operations, "list_cdn_tasks", new=AsyncMock(return_value={"items": [], "total": 0})) as tasks:
            await operations.tasks(self.request(self.admin, args={"task_id": "123", "page": "2", "size": "10"}))
            tasks.assert_awaited_once_with(task_id="123", page=2, size=10, config=operations.settings)

    async def test_extra_fields_bad_json_pagination_and_unconfigured_service_are_rejected(self):
        for payload in (None, [], {}, {"urls": ["https://cdn.example.com/x"], "object_type": "File", "Action": "DeleteCdnDomain"}):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                await operations.refresh(self.request(self.admin, payload))
        for args in ({"page": "0"}, {"size": "51"}, {"page": "１"}, {"page": "1" * 100}):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                await operations.tasks(self.request(self.admin, args=args))
        with patch.object(operations, "settings", configured(ACCESS_KEY_SECRET="")):
            self.assertFalse(self.data(await operations.get_config(self.request(self.admin)))["enabled"])
            with self.assertRaises(APIError) as caught:
                await operations.preload(self.request(self.admin, {"urls": ["https://cdn.example.com/x"]}))
            self.assertEqual(caught.exception.status, 503)


if __name__ == "__main__":
    unittest.main()
