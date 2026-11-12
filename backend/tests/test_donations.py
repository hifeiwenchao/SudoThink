"""Donation settings endpoints, using an isolated SQLite database and real JWTs."""
import importlib
import importlib.util
import json
import os
import unittest
from types import SimpleNamespace

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "donations-tests-only-32-byte-secret")

from sanic import Sanic
from tortoise import Tortoise, connections

from app.core.exceptions import ForbiddenError, UnauthorizedError, ValidationError
from app.core.security import create_access_token
from app.models.category import Category
from app.models.user import User


class DonationSettingsTests(unittest.IsolatedAsyncioTestCase):
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

    def handler(self, name, admin=False):
        path = "app.api.admin.donations" if admin else "app.api.donations"
        self.assertIsNotNone(importlib.util.find_spec(path), "Donation endpoint is missing")
        return getattr(importlib.import_module(path), name)

    def model(self):
        path = "app.models.donations"
        self.assertIsNotNone(importlib.util.find_spec(path), "Donation model is missing")
        return importlib.import_module(path).DonationSettings

    def request(self, user=None, payload=None):
        headers = {}
        if user is not None:
            headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
        return SimpleNamespace(headers=headers, ctx=SimpleNamespace(), json=payload)

    def data(self, response):
        body = json.loads(response.body)
        self.assertEqual(body["code"], 0)
        return body["data"]

    async def save(self, enabled=False, wechat="", alipay=""):
        return self.data(await self.handler("update_donations_admin", admin=True)(
            self.request(self.admin, {
                "enabled": enabled, "wechat_qr_url": wechat, "alipay_qr_url": alipay,
            })
        ))

    async def public(self):
        return self.data(await self.handler("get_donations")(self.request()))

    async def administrative(self):
        return self.data(await self.handler("get_donations_admin", admin=True)(
            self.request(self.admin)
        ))

    async def test_initial_public_and_admin_defaults_do_not_create_a_record(self):
        self.assertEqual(await self.public(), {
            "enabled": False, "wechat_qr_url": "", "alipay_qr_url": "",
        })
        self.assertEqual(await self.administrative(), {
            "enabled": False, "wechat_qr_url": "", "alipay_qr_url": "", "updated_at": None,
        })
        self.assertEqual(await self.model().all().count(), 0)

    async def test_admin_endpoints_require_an_active_administrator(self):
        for name in ("get_donations_admin", "update_donations_admin"):
            handler = self.handler(name, admin=True)
            for user, error in ((None, UnauthorizedError), (self.reader, ForbiddenError)):
                with self.subTest(handler=name, user=user), self.assertRaises(error):
                    await handler(self.request(user, {
                        "enabled": False, "wechat_qr_url": "", "alipay_qr_url": "",
                    }))
        self.admin.is_active = False
        await self.admin.save()
        for name in ("get_donations_admin", "update_donations_admin"):
            with self.subTest(handler=name), self.assertRaises(UnauthorizedError):
                await self.handler(name, admin=True)(self.request(self.admin))
        self.assertEqual(await self.model().all().count(), 0)

    async def test_invalid_and_deleted_user_tokens_cannot_update_settings(self):
        handler = self.handler("update_donations_admin", admin=True)
        request = self.request(self.admin, {})
        request.headers["Authorization"] = "Bearer not-a-jwt"
        with self.assertRaises(UnauthorizedError):
            await handler(request)
        request = self.request(self.admin, {})
        await self.admin.delete()
        with self.assertRaises(UnauthorizedError):
            await handler(request)

    async def test_each_single_code_and_both_codes_are_available_when_enabled(self):
        for wechat, alipay in (
            ("https://cdn.example.com/wechat.png", ""),
            ("", "http://cdn.example.com/alipay.png"),
            ("https://cdn.example.com/wechat.png", "https://cdn.example.com/alipay.png"),
        ):
            with self.subTest(wechat=wechat, alipay=alipay):
                saved = await self.save(True, wechat, alipay)
                self.assertIsInstance(saved["updated_at"], str)
                self.assertEqual(await self.public(), {
                    "enabled": True, "wechat_qr_url": wechat, "alipay_qr_url": alipay,
                })
                self.assertEqual(await self.administrative(), saved)
        self.assertEqual(await self.model().all().count(), 1)
        self.assertEqual((await self.model().get()).id, 1)

    async def test_disabling_hides_public_urls_while_preserving_admin_settings(self):
        await self.save(True, "https://cdn.example.com/wechat.png", "")
        saved = await self.save(False, "https://cdn.example.com/wechat.png", "")
        self.assertEqual(saved["wechat_qr_url"], "https://cdn.example.com/wechat.png")
        self.assertEqual(await self.public(), {
            "enabled": False, "wechat_qr_url": "", "alipay_qr_url": "",
        })
        self.assertEqual(await self.administrative(), saved)

    async def test_admin_can_clear_a_code_or_clear_all_codes_when_disabled(self):
        await self.save(True, "https://cdn.example.com/wechat.png", "https://cdn.example.com/a.png")
        await self.save(True, "", "https://cdn.example.com/a.png")
        self.assertEqual((await self.public())["wechat_qr_url"], "")
        saved = await self.save(False)
        self.assertEqual(saved["wechat_qr_url"], "")
        self.assertEqual(saved["alipay_qr_url"], "")
        persisted = await self.model().get(id=1)
        self.assertEqual((persisted.enabled, persisted.wechat_qr_url, persisted.alipay_qr_url),
                         (False, "", ""))

    async def test_urls_are_trimmed_and_queries_and_exact_maximum_length_are_preserved(self):
        query_url = "https://cdn.example.com/wechat.png?version=2&width=480"
        saved = await self.save(True, "  " + query_url + "  ", "   ")
        self.assertEqual(saved["wechat_qr_url"], query_url)
        self.assertEqual(saved["alipay_qr_url"], "")
        max_url = "https://cdn.example.com/" + "a" * (2048 - len("https://cdn.example.com/"))
        saved = await self.save(True, max_url)
        self.assertEqual(saved["wechat_qr_url"], max_url)

    async def test_invalid_forms_do_not_overwrite_saved_settings_or_update_timestamp(self):
        original = await self.save(True, "https://cdn.example.com/retained.png", "")
        complete = {"enabled": False, "wechat_qr_url": "", "alipay_qr_url": ""}
        invalid = [None, [], "invalid", 7, {},
                   {"enabled": False, "wechat_qr_url": ""},
                   {"enabled": False, "alipay_qr_url": ""},
                   {"wechat_qr_url": "", "alipay_qr_url": ""},
                   {**complete, "unexpected": "field"},
                   {**complete, "enabled": True}]
        invalid.extend({**complete, "enabled": value} for value in ("false", "true", 0, 1, None))
        for field in ("wechat_qr_url", "alipay_qr_url"):
            invalid.extend({**complete, field: value} for value in (None, 7, False, []))
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                await self.handler("update_donations_admin", admin=True)(
                    self.request(self.admin, payload)
                )
            self.assertEqual(await self.administrative(), original)
        self.assertEqual(await self.model().all().count(), 1)

    async def test_unsafe_or_incomplete_urls_are_rejected_without_changes(self):
        original = await self.save(False, "https://cdn.example.com/retained.png", "")
        invalid_urls = (
            "/qr.png", "//cdn.example.com/qr.png", "cdn.example.com/qr.png",
            "https:", "https:///qr.png", "https://", "javascript:alert(1)",
            "data:image/png;base64,abc", "file:///tmp/qr.png", "ftp://cdn.example.com/qr.png",
            "https://user:password@cdn.example.com/qr.png", "https://user@cdn.example.com/qr.png",
            "https://@cdn.example.com/qr.png", "https://cdn.example.com/a b.png",
            "https://cdn.example.com/a\nb.png", "https://cdn.example.com/a\rb.png",
            "https://cdn.example.com/a\tb.png", "https://cdn.example.com/a\x00b.png",
            "https://cdn.example.com/a\x7fb.png", "https://cdn.example.com/a\u0085b.png",
            "https://cdn.example.com/a\\b.png", "https://cdn.example.com/qr.png#part",
            "https://cdn.example.com/qr.png#", "https://cdn.example.com:bad/qr.png",
            "https://cdn.example.com:65536/qr.png", "https://%00cdn.example.com/qr.png",
            "https://cdn.example.com/" + "a" * 2048,
        )
        for field in ("wechat_qr_url", "alipay_qr_url"):
            for url in invalid_urls:
                payload = {"enabled": False, "wechat_qr_url": "", "alipay_qr_url": "", field: url}
                with self.subTest(field=field, url=url), self.assertRaises(ValidationError):
                    await self.handler("update_donations_admin", admin=True)(
                        self.request(self.admin, payload)
                    )
                self.assertEqual(await self.administrative(), original)

    async def test_safe_schema_generation_creates_missing_table_and_preserves_records_on_rerun(self):
        self.model()
        category = await Category.create(name="Retained", slug="retained", weight=7)
        await connections.get("default").execute_script("DROP TABLE donation_settings")
        await Tortoise.generate_schemas(safe=True)
        saved = await self.save(True, "https://cdn.example.com/retained.png", "")
        await Tortoise.generate_schemas(safe=True)
        await Tortoise.generate_schemas(safe=True)
        self.assertEqual(await self.administrative(), saved)
        self.assertEqual(await self.model().all().count(), 1)
        self.assertEqual((await Category.get(id=category.id)).weight, 7)

    async def test_public_and_admin_routes_are_registered_with_expected_methods(self):
        from app.api import register_blueprints
        app = Sanic("donation_routes", configure_logging=False)
        register_blueprints(app)
        app.router.finalize()
        routes = {(route.path, method) for route in app.router.routes for method in route.methods}
        self.assertIn(("api/donations", "GET"), routes)
        self.assertIn(("api/admin/donations", "GET"), routes)
        self.assertIn(("api/admin/donations", "PUT"), routes)


if __name__ == "__main__":
    unittest.main()
