"""OSS upload credentials, using real JWT auth and an isolated SQLite database."""
import base64
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "uploads-tests-only-32-byte-secret-value")

from sanic import Sanic
from sanic.exceptions import BadRequest
from tortoise import Tortoise

from app.core.exceptions import APIError, ForbiddenError, UnauthorizedError, ValidationError
from app.core.security import create_access_token
from app.models.user import User


def configured(**overrides):
    values = {
        "ACCESS_KEY_ID": "test-access-key-id",
        "ACCESS_KEY_SECRET": "test-access-key-secret",
        "OSS_SECURITY_TOKEN": "",
        "OSS_REGION": "cn-hangzhou",
        "OSS_BUCKET": "sudothink-test",
        "OSS_ENDPOINT": "https://oss-cn-hangzhou.aliyuncs.com",
        "CDN_BASE_URL": "https://cdn.example.com/blog/",
        "OSS_MEDIA_PREFIX": "media",
        "OSS_STATIC_PREFIX": "static",
        "OSS_IMAGE_MAX_BYTES": 10485760,
        "OSS_VIDEO_MAX_BYTES": 209715200,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class CredentialEnvironmentTests(unittest.TestCase):
    def test_shared_access_keys_enable_uploads_from_environment(self):
        environment = {key: str(value) for key, value in vars(configured()).items()}
        environment["PYTHON_DOTENV_DISABLED"] = "1"
        result = subprocess.run(
            [sys.executable, "-c", (
                "import json; from app.core.oss import get_upload_configuration; "
                "print(json.dumps(get_upload_configuration()))"
            )],
            cwd=Path(__file__).resolve().parents[1], env=environment,
            capture_output=True, text=True, check=True,
        )
        self.assertTrue(json.loads(result.stdout)["enabled"])


class InvalidJSONRequest:
    def __init__(self, request):
        self.headers = request.headers
        self.ctx = request.ctx

    @property
    def json(self):
        raise BadRequest("Failed when parsing body as json")


class UploadTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.admin = await User.create(
            username="admin", email="admin@example.com", password_hash="unused", is_admin=True
        )
        self.reader = await User.create(
            username="reader", email="reader@example.com", password_hash="unused"
        )

    async def asyncTearDown(self):
        await Tortoise.close_connections()

    def module(self, name):
        self.assertIsNotNone(importlib.util.find_spec(name), f"Missing upload module: {name}")
        return importlib.import_module(name)

    def request(self, user=None, payload=None, content_type="application/json"):
        headers = {"Content-Type": content_type}
        if user is not None:
            headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
        return SimpleNamespace(headers=headers, ctx=SimpleNamespace(), json=payload)

    def data(self, response):
        body = json.loads(response.body)
        self.assertEqual(body["code"], 0)
        return body["data"]

    async def test_config_and_policy_require_an_active_administrator(self):
        uploads = self.module("app.api.admin.uploads")
        for handler in (uploads.get_upload_config, uploads.create_upload_policy):
            for user, error in ((None, UnauthorizedError), (self.reader, ForbiddenError)):
                with self.subTest(handler=handler.__name__, user=user), self.assertRaises(error):
                    await handler(self.request(user, {}))
        self.admin.is_active = False
        await self.admin.save()
        with self.assertRaises(UnauthorizedError):
            await uploads.get_upload_config(self.request(self.admin))

    async def test_disabled_config_is_safe_and_policy_reports_service_unavailable(self):
        uploads = self.module("app.api.admin.uploads")
        config = configured(ACCESS_KEY_SECRET="")
        with patch.object(uploads, "settings", config):
            data = self.data(await uploads.get_upload_config(self.request(self.admin)))
            self.assertFalse(data["enabled"])
            self.assertEqual(data["image_max_bytes"], 10485760)
            self.assertEqual(data["video_max_bytes"], 209715200)
            self.assertEqual(data["image_types"]["image/jpeg"], [".jpg", ".jpeg"])
            self.assertEqual(data["video_types"], {"video/mp4": [".mp4"], "video/webm": [".webm"]})
            with self.assertRaises(APIError) as unavailable:
                await uploads.create_upload_policy(self.request(self.admin, {
                    "filename": "photo.jpg", "size": 2048, "content_type": "image/jpeg",
                }))
            self.assertEqual(unavailable.exception.status, 503)
            self.assertNotIn("test-access-key-id", str(unavailable.exception))
            self.assertNotIn("ACCESS_KEY", str(unavailable.exception))
        self.assertNotIn("test-access-key", json.dumps(data))

    async def test_admin_upload_routes_are_registered_under_api(self):
        from app.api import register_blueprints
        app = Sanic("upload_routes", configure_logging=False)
        register_blueprints(app)
        app.router.finalize()
        paths = {route.path for route in app.router.routes}
        self.assertIn("api/admin/uploads/config", paths)
        self.assertIn("api/admin/uploads/policy", paths)

    async def test_policy_uses_random_server_keys_and_cdn_prefix_for_images_and_videos(self):
        uploads = self.module("app.api.admin.uploads")
        with patch.object(uploads, "settings", configured()):
            for filename, mime, kind, suffix in (
                ("../../my private image.JPEG", "image/jpeg", "images", "jpeg"),
                ("movie.mp4", "video/mp4", "videos", "mp4"),
                ("graphic.avif", "image/avif", "images", "avif"),
            ):
                with self.subTest(mime=mime):
                    payload = {"filename": filename, "size": 1234, "content_type": mime}
                    first = self.data(await uploads.create_upload_policy(
                        self.request(self.admin, payload),
                    ))
                    second = self.data(await uploads.create_upload_policy(
                        self.request(self.admin, payload),
                    ))
                    self.assertRegex(
                        first["key"], rf"^media/{kind}/\d{{4}}/\d{{2}}/[0-9a-f]{{32}}\.{suffix}$",
                    )
                    self.assertNotEqual(first["key"], second["key"])
                    self.assertEqual(
                        first["public_url"], f"https://cdn.example.com/blog/{first['key']}",
                    )
                    self.assertEqual(first["fields"]["Content-Type"], mime)

    async def test_policy_rejects_invalid_file_metadata_with_422(self):
        uploads = self.module("app.api.admin.uploads")
        valid = {"filename": "image.png", "size": 100, "content_type": "image/png"}
        invalid = (
            {}, [], None, "not an object",
            {**valid, "size": True}, {**valid, "size": 0}, {**valid, "size": -1},
            {**valid, "size": "100"}, {**valid, "size": 1.5},
            {**valid, "size": 10485761},
            {**valid, "filename": "video.mp4", "content_type": "video/mp4", "size": 209715201},
            {**valid, "filename": 123}, {**valid, "filename": ""},
            {**valid, "filename": "x" * 256 + ".png"},
            {**valid, "filename": "image.png\x00"},
            {**valid, "filename": "image.svg", "content_type": "image/svg+xml"},
            {**valid, "filename": "image.jpg", "content_type": "image/png"},
            {**valid, "filename": "image.png.exe"},
            {**valid, "filename": "image.png", "content_type": "text/html"},
            {**valid, "content_type": "image/png\r\nX-Header: bad"},
            {**valid, "filename": "image.png", "content_type": None},
            {**valid, "unexpected": "field"},
        )
        with patch.object(uploads, "settings", configured()):
            for payload in invalid:
                with self.subTest(payload=payload), self.assertRaises(ValidationError) as error:
                    await uploads.create_upload_policy(self.request(self.admin, payload))
                self.assertEqual(error.exception.status, 422)
            with self.assertRaises(ValidationError):
                await uploads.create_upload_policy(InvalidJSONRequest(self.request(self.admin)))
            with self.assertRaises(ValidationError):
                await uploads.create_upload_policy(self.request(self.admin, valid, "text/plain"))

    async def test_file_limits_are_inclusive(self):
        uploads = self.module("app.api.admin.uploads")
        with patch.object(uploads, "settings", configured()):
            for filename, mime, limit in (
                ("image.png", "image/png", 10485760),
                ("video.webm", "video/webm", 209715200),
            ):
                result = self.data(await uploads.create_upload_policy(self.request(self.admin, {
                    "filename": filename, "content_type": mime, "size": limit,
                })))
                policy = json.loads(base64.b64decode(result["fields"]["policy"]))
                self.assertIn(["content-length-range", limit, limit], policy["conditions"])

    async def test_invalid_configuration_disables_signing_without_exposing_secrets(self):
        uploads = self.module("app.api.admin.uploads")
        invalid = (
            {"OSS_BUCKET": "Wrong_Bucket"}, {"OSS_BUCKET": "ab"},
            {"OSS_REGION": "cn-hangzhou/evil"},
            {"OSS_ENDPOINT": "http://oss-cn-hangzhou.aliyuncs.com"},
            {"OSS_ENDPOINT": "https://oss-cn-beijing.aliyuncs.com"},
            {"OSS_ENDPOINT": "https://oss-cn-hangzhou.aliyuncs.com.evil.test"},
            {"OSS_ENDPOINT": "https://user:secret@oss-cn-hangzhou.aliyuncs.com"},
            {"OSS_ENDPOINT": "https://oss-cn-hangzhou.aliyuncs.com/path"},
            {"CDN_BASE_URL": "http://cdn.example.com"},
            {"CDN_BASE_URL": "https://user:secret@cdn.example.com"},
            {"CDN_BASE_URL": "https://cdn.example.com/?token=private"},
            {"CDN_BASE_URL": "https://cdn.example.com/#fragment"},
            {"CDN_BASE_URL": "https://cdn.example.com/%2e%2e"},
            {"CDN_BASE_URL": "https://cdn.example.com:invalid"},
            {"CDN_BASE_URL": "https://cdn.example.com\\evil"},
            {"OSS_MEDIA_PREFIX": "../media"}, {"OSS_MEDIA_PREFIX": "media/../other"},
            {"OSS_MEDIA_PREFIX": "media//nested"}, {"OSS_MEDIA_PREFIX": "media/%2e%2e"},
            {"OSS_IMAGE_MAX_BYTES": 0}, {"OSS_VIDEO_MAX_BYTES": -1},
            {"ACCESS_KEY_ID": "id\r\nInjected: header"},
            {"ACCESS_KEY_SECRET": "secret\ninvalid"},
        )
        for override in invalid:
            with (
                self.subTest(override=override),
                patch.object(uploads, "settings", configured(**override)),
            ):
                response = self.data(await uploads.get_upload_config(self.request(self.admin)))
                self.assertFalse(response["enabled"])
                self.assertNotIn("test-access-key-secret", json.dumps(response))
                with self.assertRaises(APIError) as error:
                    await uploads.create_upload_policy(self.request(self.admin, {
                        "filename": "photo.png", "size": 100, "content_type": "image/png",
                    }))
                self.assertEqual(error.exception.status, 503)
                self.assertNotIn("test-access-key-secret", str(error.exception))

    def test_signature_matches_a_fixed_v4_reference_vector(self):
        oss = self.module("app.core.oss")
        # Synthetic credential vector independently calculated from the documented HMAC stages.
        encoded = (
            "eyJleHBpcmF0aW9uIjoiMjAyNi0xMS0xMlQwODowNTowMC4wMDBaIiwiY29uZGl0aW9u"
            "cyI6W3siYnVja2V0Ijoic3Vkb3RoaW5rLXRlc3QifV19"
        )
        signature = oss.sign_v4_policy(encoded, "test-access-key-secret", "20261112", "cn-hangzhou")
        self.assertEqual(
            signature, "9a5a07cda84680e46bbbffa1f352e30055cfa8f5493ce59759cd34a559495fee",
        )

    def test_signing_has_five_minute_expiry_and_exact_object_type_size_and_fields(self):
        oss = self.module("app.core.oss")
        result = oss.sign_post_policy(
            key="media/images/2026/11/fixed.png", size=1234, content_type="image/png",
            config=configured(OSS_SECURITY_TOKEN="temporary-security-token"),
            now=datetime(2026, 11, 12, 8, 0, 0, tzinfo=timezone.utc),
        )
        fields = result["fields"]
        self.assertEqual(
            result["upload_url"], "https://sudothink-test.oss-cn-hangzhou.aliyuncs.com",
        )
        self.assertEqual(
            result["public_url"], "https://cdn.example.com/blog/media/images/2026/11/fixed.png",
        )
        self.assertEqual(result["expires_at"], "2026-11-12T08:05:00Z")
        self.assertEqual(fields["x-oss-date"], "20261112T080000Z")
        self.assertEqual(fields["x-oss-signature-version"], "OSS4-HMAC-SHA256")
        self.assertEqual(
            fields["x-oss-credential"],
            "test-access-key-id/20261112/cn-hangzhou/oss/aliyun_v4_request",
        )
        self.assertEqual(fields["success_action_status"], "201")
        self.assertEqual(fields["x-oss-security-token"], "temporary-security-token")
        self.assertNotIn("file", fields)
        policy = json.loads(base64.b64decode(fields["policy"]))
        self.assertEqual(policy["expiration"], "2026-11-12T08:05:00.000Z")
        self.assertIn(["eq", "$bucket", "sudothink-test"], policy["conditions"])
        self.assertIn(["content-length-range", 1234, 1234], policy["conditions"])
        for name, value in fields.items():
            if name not in {"policy", "x-oss-signature"}:
                self.assertIn(["eq", "$" + name.lower(), value], policy["conditions"])
        self.assertNotIn("test-access-key-secret", json.dumps(result))
        self.assertRegex(fields["x-oss-signature"], r"^[a-f0-9]{64}$")

    def test_static_signing_accepts_javascript_but_rejects_unsafe_object_keys(self):
        oss = self.module("app.core.oss")
        result = oss.sign_post_policy(
            key="static/assets/app.hash.js", size=123, content_type="text/javascript",
            config=configured(),
        )
        self.assertEqual(result["fields"]["Content-Type"], "text/javascript")
        for key in (
            "/static/a.js", "static/../a.js", "static//a.js", "static/a.js?x=y", "static/a\\b.js",
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                oss.sign_post_policy(
                    key=key, size=1, content_type="text/javascript", config=configured(),
                )

    def test_static_cache_control_is_pinned_in_policy_and_cannot_inject_headers(self):
        oss = self.module("app.core.oss")
        result = oss.sign_post_policy(
            key="static/assets/app.hash.js", size=123, content_type="text/javascript",
            config=configured(), cache_control="public, max-age=31536000, immutable",
        )
        fields = result["fields"]
        self.assertEqual(fields.get("Cache-Control"), "public, max-age=31536000, immutable")
        policy = json.loads(base64.b64decode(fields["policy"]))
        self.assertIn(
            ["eq", "$cache-control", "public, max-age=31536000, immutable"], policy["conditions"],
        )
        for value in ("", "public\r\nInjected: header", "x" * 257, 123):
            with self.subTest(value=value), self.assertRaises(ValueError):
                oss.sign_post_policy(
                    key="static/assets/app.hash.js", size=123, content_type="text/javascript",
                    config=configured(), cache_control=value,
                )


if __name__ == "__main__":
    unittest.main()
