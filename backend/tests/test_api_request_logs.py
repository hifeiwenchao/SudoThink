"""API recording and admin queries against SQLite and in-process Sanic ASGI."""
import importlib
import importlib.util
import json
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "request-log-tests-only-32-byte-secret")

from sanic import Sanic
from sanic.response import json as json_response
from tortoise import Tortoise
from app.api import register_blueprints
from app.core.exceptions import register_exception_handlers
from app.core.security import create_access_token
from app.models.user import User


class ApiRequestLogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.admin = await User.create(username="admin", email="admin@example.com",
                                       password_hash="unused", is_admin=True)
        self.reader = await User.create(username="reader", email="reader@example.com", password_hash="unused")
        self.app = None

    async def asyncTearDown(self):
        await Tortoise.close_connections()
        if self.app is not None:
            Sanic.unregister_app(self.app)

    def module(self, name):
        self.assertIsNotNone(importlib.util.find_spec(name), f"Missing request-log feature: {name}")
        return importlib.import_module(name)

    def model(self):
        return self.module("app.models.api_request_log").ApiRequestLog

    async def application(self):
        middleware = self.module("app.middlewares.request_log")
        app = self.app = Sanic(f"request_logs_{id(self)}", configure_logging=False)
        app.config.AUTO_EXTEND = False
        # Touchup rewrites Sanic class methods once for a production process;
        # this suite deliberately creates several independent apps in one process.
        app.config.TOUCHUP = False
        register_blueprints(app)
        register_exception_handlers(app)
        middleware.register_request_logging(app)

        @app.route("/api/echo/<aid:int>", methods=["GET", "POST"])
        async def echo(request, aid):
            return json_response({"aid": aid})

        @app.post("/api/parse-json")
        async def parse_json(request):
            return json_response(request.json)

        @app.get("/api/failure")
        async def failure(_):
            raise RuntimeError("test failure")

        @app.get("/static-check")
        async def static_check(_):
            return json_response({"ok": True})

        app.asgi = True
        await app._startup()

    async def request(self, target, *, method="GET", payload=None, body=None, headers=None, user=None):
        if self.app is None:
            await self.application()
        parts = urlsplit(target)
        request_headers = {"host": "blog.example.com", **(headers or {})}
        if user is not None:
            request_headers["authorization"] = "Bearer " + create_access_token(user.id)
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            request_headers.setdefault("content-type", "application/json")
        body = body or b""
        request_headers["content-length"] = str(len(body))
        events = []

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(event):
            events.append(event)

        await self.app({
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": method, "scheme": "https", "path": parts.path,
            "raw_path": parts.path.encode(), "query_string": parts.query.encode(),
            "headers": [(key.encode(), value.encode()) for key, value in request_headers.items()],
            "client": ("127.0.0.1", 12345), "server": ("blog.example.com", 443),
        }, receive, send)
        status = next(event["status"] for event in events if event["type"] == "http.response.start")
        raw = b"".join(event.get("body", b"") for event in events if event["type"] == "http.response.body")
        return SimpleNamespace(status=status, body=raw)

    def data(self, response):
        self.assertEqual(response.status, 200)
        result = json.loads(response.body)
        self.assertEqual(result["code"], 0)
        return result["data"]

    async def test_api_records_keep_matched_params_status_timing_and_safe_defaults(self):
        self.assertEqual((await self.request("/api/echo/7?search=python&tag=one&tag=two")).status, 200)
        record = await self.model().get()
        self.assertEqual((record.method, record.path, record.status_code), ("GET", "/api/echo/7", 200))
        self.assertEqual(record.path_params, {"aid": 7})
        self.assertEqual(record.query_params, {"search": "python", "tag": ["one", "two"]})
        self.assertEqual(record.url, "/api/echo/7?search=python&tag=one&tag=two")
        self.assertGreaterEqual(record.duration_ms, 0)
        self.assertIsNotNone(record.created_at)
        self.assertIsNone(record.body_params)
        await self.request("/static-check")
        self.assertEqual(await self.model().all().count(), 1)

    async def test_nested_credentials_encoded_query_secrets_and_headers_never_leak(self):
        await self.request(
            "/api/echo/7?pass%77ord=url-password&access_key_id=access-id&api-key=api-value&ok=visible",
            method="POST", payload={
                "username": "author", "password": "body-password",
                "settings": [{"refreshToken": "refresh-value", "secret_key": "secret-value"}],
                "credentials": {"username": "private-user", "value": "credential-value"},
                "accessKeySecret": "access-secret", "new_password": "new-password-value",
            }, headers={"authorization": "Bearer header-only", "cookie": "session=cookie-only"},
        )
        record = await self.model().get()
        saved = json.dumps([record.url, record.query_params, record.body_params, record.path_params])
        for secret in (
            "url-password", "access-id", "api-value", "body-password", "refresh-value",
            "secret-value", "private-user", "credential-value", "access-secret",
            "new-password-value", "header-only", "cookie-only",
        ):
            self.assertNotIn(secret, saved)
        self.assertEqual(record.query_params["ok"], "visible")
        self.assertEqual(record.body_params["username"], "author")
        self.assertEqual(record.body_params["settings"][0]["refreshToken"], "[REDACTED]")

    async def test_failed_and_unmatched_api_requests_are_recorded(self):
        for target, kwargs, expected in (
            ("/api/not-a-route?token=missing-secret", {}, 404),
            ("/api/failure", {}, 500),
            ("/api/parse-json", {"method": "POST", "body": b'{"password":"broken-secret"',
             "headers": {"content-type": "application/json"}}, 400),
        ):
            with self.subTest(target=target):
                self.assertEqual((await self.request(target, **kwargs)).status, expected)
                record = await self.model().all().order_by("-id").first()
                self.assertEqual(record.status_code, expected)
                self.assertNotIn("secret", json.dumps([record.url, record.body_params]))
        self.assertEqual(await self.model().all().count(), 3)

    async def test_large_binary_multipart_and_malformed_bodies_only_store_metadata(self):
        for content_type, body in (
            ("application/json", b'{"value":"' + b"large-private-value" * 10000 + b'"}'),
            ("application/octet-stream", b"binary-private-value"),
            ("multipart/form-data; boundary=abc", b"file-private-value"),
            ("application/json", b'{"password":"invalid-private-value"'),
        ):
            with self.subTest(content_type=content_type, length=len(body)):
                response = await self.request("/api/echo/2", method="POST", body=body,
                                              headers={"content-type": content_type})
                self.assertEqual(response.status, 200)
                record = await self.model().all().order_by("-id").first()
                serialized = json.dumps(record.body_params)
                self.assertNotIn("private-value", serialized)
                self.assertLess(len(serialized), 200)

    async def test_bounds_limit_depth_fields_strings_and_combined_size(self):
        nested = {"leaf": "deep-private-value"}
        for _ in range(30):
            nested = {"nested": nested}
        await self.request("/api/echo/9", method="POST",
                           payload={"safe": "visible", "deep": nested})
        record = await self.model().get()
        self.assertEqual(record.body_params["safe"], "visible")
        self.assertNotIn("deep-private-value", json.dumps(record.body_params))
        await self.request("/api/echo/9", method="POST",
                           payload={f"field{i}": "字" * 10000 for i in range(300)})
        record = await self.model().all().order_by("-id").first()
        self.assertLess(len(json.dumps(record.body_params).encode()), 200)
        await self.request("/api/echo/9?" + "&".join(f"field{i}=" + "x" * 400 for i in range(120)))
        record = await self.model().all().order_by("-id").first()
        self.assertLessEqual(len(record.url), 2048)
        self.assertLessEqual(len(json.dumps([record.query_params, record.path_params, record.body_params],
                                            ensure_ascii=False).encode()), 16384)
        self.assertLessEqual(len(record.query_params), 101)

    async def test_urlencoded_forms_sanitize_fields_and_preserve_repeated_values(self):
        response = await self.request("/api/echo/3", method="POST",
                                      body=b"username=author&password=form-private&token=form-token&tag=a&tag=b",
                                      headers={"content-type": "application/x-www-form-urlencoded"})
        self.assertEqual(response.status, 200)
        record = await self.model().get()
        self.assertEqual(record.body_params["username"], "author")
        self.assertEqual(record.body_params["tag"], ["a", "b"])
        self.assertNotIn("form-private", json.dumps(record.body_params))
        self.assertNotIn("form-token", json.dumps(record.body_params))

    async def test_log_failure_preserves_response_and_uses_non_sensitive_diagnostic(self):
        model = self.model()
        with patch.object(model, "create", side_effect=RuntimeError("database-password-must-not-leak")):
            with self.assertLogs("app.request_log", level="WARNING") as messages:
                response = await self.request("/api/echo/4?token=query-private")
        self.assertEqual(response.status, 200)
        self.assertNotIn("database-password", " ".join(messages.output))
        self.assertNotIn("query-private", " ".join(messages.output))
        self.assertEqual(await model.all().count(), 0)

    async def seed(self):
        records = []
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for method, path, status in (
            ("GET", "/api/articles/8", 200),
            ("GET", "/api/articles/9", 200),
            ("POST", "/api/auth/login", 401),
            ("GET", "/api/articles/10", 404),
        ):
            records.append(await self.model().create(
                method=method, path=path, url="/archived" + path,
                status_code=status, duration_ms=5,
            ))
        await self.model().all().update(created_at=timestamp)
        return records

    async def test_admin_query_returns_contract_fields_with_stable_pagination(self):
        records = await self.seed()
        result = self.data(await self.request("/api/admin/operations/requests?size=2", user=self.admin))
        self.assertEqual((result["total"], result["page"], result["size"]), (4, 1, 2))
        self.assertEqual([item["id"] for item in result["items"]], [records[3].id, records[2].id])
        self.assertEqual(set(result["items"][0]), {
            "id", "method", "url", "path", "query_params", "path_params", "body_params",
            "status_code", "duration_ms", "created_at",
        })
        self.assertIsInstance(result["items"][0]["created_at"], str)
        second = self.data(await self.request(
            "/api/admin/operations/requests?url=/archived&page=2&size=2", user=self.admin,
        ))
        self.assertEqual([item["id"] for item in second["items"]], [records[1].id, records[0].id])

    async def test_url_method_and_status_filters_combine_with_accurate_totals(self):
        records = await self.seed()
        for query, expected in (
            ("url=/archived/api/articles", [records[3].id, records[1].id, records[0].id]),
            ("method=GET&status_code=200&url=/archived/api/articles", [records[1].id, records[0].id]),
            ("method=POST&status_code=401&url=/archived/api/auth", [records[2].id]),
            ("method=GET&status_code=404&url=/archived/api/articles", [records[3].id]),
            ("method=POST&status_code=200&url=/archived/api/articles", []),
        ):
            with self.subTest(query=query):
                result = self.data(await self.request(
                    "/api/admin/operations/requests?" + query, user=self.admin,
                ))
                self.assertEqual([item["id"] for item in result["items"]], expected)
                self.assertEqual(result["total"], len(expected))
        defaults = self.data(await self.request("/api/admin/operations/requests?url=/archived", user=self.admin))
        self.assertEqual((defaults["page"], defaults["size"]), (1, 20))

    async def test_query_requires_active_admin_and_strict_filter_values(self):
        for user, expected in ((None, 401), (self.reader, 403)):
            self.assertEqual((await self.request("/api/admin/operations/requests", user=user)).status, expected)
        self.admin.is_active = False
        await self.admin.save()
        self.assertEqual((await self.request("/api/admin/operations/requests", user=self.admin)).status, 401)
        self.admin.is_active = True
        await self.admin.save()
        for query in (
            "page=0", "page=-1", "page=1.0", "page=%201", "page=99999999999", "size=0", "size=101",
            "method=get", "method=INVALID", "method=", "status_code=99", "status_code=600",
            "status_code=200.0", "status_code=", "url=" + "x" * 2049,
            "page=1&page=2",
        ):
            with self.subTest(query=query):
                self.assertEqual((await self.request(
                    "/api/admin/operations/requests?" + query, user=self.admin,
                )).status, 422)


if __name__ == "__main__":
    unittest.main()
