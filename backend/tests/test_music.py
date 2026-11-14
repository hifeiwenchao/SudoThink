"""Music settings with real JWT auth and an isolated, in-memory database."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "music-tests-only-32-byte-secret-value")

from sanic import Sanic
from sanic.exceptions import BadRequest
from tortoise import Tortoise, connections

from app.api import music
from app.api.admin import music as admin_music
from app.core.exceptions import ForbiddenError, UnauthorizedError, ValidationError
from app.core.security import create_access_token
from app.models.category import Category
from app.models.music import MusicSettings
from app.models.user import User


CDN = "https://cdn.example.com/blog"


def track(number=1, **overrides):
    values = {
        "title": f"曲目 {number}", "artist": "演奏者",
        "url": f"{CDN}/media/audios/2026/11/{number:032x}.mp3",
    }
    values.update(overrides)
    return values


class MusicSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await Tortoise.init(db_url="sqlite://:memory:", modules={"models": ["app.models"]})
        await Tortoise.generate_schemas()
        self.admin = await User.create(
            username="admin", email="admin@example.com", password_hash="unused", is_admin=True,
        )
        self.reader = await User.create(
            username="reader", email="reader@example.com", password_hash="unused",
        )
        self.config = SimpleNamespace(CDN_BASE_URL=CDN + "/", OSS_MEDIA_PREFIX="media")
        self.config_patch = patch.object(admin_music, "settings", self.config)
        self.config_patch.start()

    async def asyncTearDown(self):
        self.config_patch.stop()
        await Tortoise.close_connections()

    def request(self, user=None, payload=None, content_type="application/json"):
        headers = {"Content-Type": content_type}
        if user is not None:
            headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
        return SimpleNamespace(headers=headers, ctx=SimpleNamespace(), json=payload)

    def data(self, response):
        body = json.loads(response.body)
        self.assertEqual(body["code"], 0)
        return body["data"]

    async def save(self, enabled=True, tracks=None):
        return self.data(await admin_music.update_music_admin(self.request(
            self.admin, {"enabled": enabled, "tracks": tracks if tracks is not None else [track()]},
        )))

    async def public(self):
        return self.data(await music.get_music(self.request()))

    async def administrative(self):
        return self.data(await admin_music.get_music_admin(self.request(self.admin)))

    async def test_initial_defaults_are_hidden_and_do_not_create_a_record(self):
        self.assertEqual(await self.public(), {"enabled": False, "tracks": []})
        self.assertEqual(await self.administrative(), {
            "enabled": False, "tracks": [], "updated_at": None,
        })
        self.assertEqual(await MusicSettings.all().count(), 0)

    async def test_admin_get_and_put_require_an_active_administrator(self):
        for handler in (admin_music.get_music_admin, admin_music.update_music_admin):
            for user, error in ((None, UnauthorizedError), (self.reader, ForbiddenError)):
                with self.subTest(handler=handler.__name__, user=user), self.assertRaises(error):
                    await handler(self.request(user, {"enabled": True, "tracks": [track()]}))
        self.admin.is_active = False
        await self.admin.save()
        for handler in (admin_music.get_music_admin, admin_music.update_music_admin):
            with self.assertRaises(UnauthorizedError):
                await handler(self.request(self.admin))
        self.assertEqual(await MusicSettings.all().count(), 0)

    async def test_invalid_and_deleted_user_tokens_cannot_update_settings(self):
        request = self.request(self.admin, {"enabled": False, "tracks": []})
        request.headers["Authorization"] = "Bearer invalid-token"
        with self.assertRaises(UnauthorizedError):
            await admin_music.update_music_admin(request)
        request = self.request(self.admin, {"enabled": False, "tracks": []})
        await self.admin.delete()
        with self.assertRaises(UnauthorizedError):
            await admin_music.update_music_admin(request)

    async def test_saving_reordering_editing_and_removing_tracks_preserves_exact_order(self):
        tracks = [track(1), track(2), track(3)]
        saved = await self.save(tracks=tracks)
        self.assertEqual(saved["tracks"], tracks)
        self.assertIsInstance(saved["updated_at"], str)
        self.assertEqual(await self.public(), {"enabled": True, "tracks": tracks})
        reordered = [track(3, title=" 修改后的曲名 ", artist="  "), track(1)]
        saved = await self.save(tracks=reordered)
        expected = [track(3, title="修改后的曲名", artist=""), track(1)]
        self.assertEqual(saved["tracks"], expected)
        self.assertEqual(await self.public(), {"enabled": True, "tracks": expected})
        self.assertEqual((await MusicSettings.get(id=1)).tracks, expected)
        self.assertEqual(await MusicSettings.all().count(), 1)

    async def test_disabling_preserves_admin_playlist_and_hides_public_tracks(self):
        await self.save()
        saved = await self.save(False, [track(), track(2)])
        self.assertFalse(saved["enabled"])
        self.assertEqual(saved["tracks"], [track(), track(2)])
        self.assertEqual(await self.public(), {"enabled": False, "tracks": []})
        self.assertEqual(await self.administrative(), saved)

    async def test_removing_all_tracks_hides_player_even_when_enabled(self):
        await self.save()
        saved = await self.save(True, [])
        self.assertTrue(saved["enabled"])
        self.assertEqual(saved["tracks"], [])
        self.assertEqual(await self.public(), {"enabled": False, "tracks": []})
        self.assertEqual((await MusicSettings.get(id=1)).tracks, [])

    async def test_maximum_playlist_and_unicode_names_are_supported(self):
        tracks = [track(number) for number in range(100)]
        saved = await self.save(tracks=tracks)
        self.assertEqual(len(saved["tracks"]), 100)
        saved = await self.save(tracks=[track(title="曲" * 120, artist="歌" * 120)])
        self.assertEqual(saved["tracks"][0]["title"], "曲" * 120)

    async def test_invalid_input_never_overwrites_the_saved_playlist(self):
        original = await self.save()
        complete = {"enabled": False, "tracks": []}
        invalid = [None, [], 7, "invalid", {}, {"enabled": False}, {"tracks": []},
                   {**complete, "extra": "field"}, {**complete, "tracks": "invalid"},
                   {**complete, "tracks": [track(), track()]},
                   {**complete, "tracks": [track(number) for number in range(101)]}]
        invalid.extend({**complete, "enabled": value} for value in (None, 0, 1, "true", "false"))
        invalid.extend({**complete, "tracks": value} for value in (None, False, 0, {}))
        invalid.extend({**complete, "tracks": [item]} for item in (
            {}, [], None, track(title=""), track(title="   "), track(title="a" * 121),
            track(artist="a" * 121), track(title=1), track(artist=False), track(url=None),
            track(title="line\nbreak"), track(artist="hidden\u200btext"),
            {**track(), "extra": "field"},
        ))
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                await admin_music.update_music_admin(self.request(self.admin, payload))
            self.assertEqual(await self.administrative(), original)
        self.assertEqual(await MusicSettings.all().count(), 1)

    async def test_only_uploaded_audio_urls_are_accepted(self):
        original = await self.save()
        original_url = track()["url"]
        invalid = (
            "javascript:alert(1)", "data:audio/mpeg;base64,eA==", "/media/audios/track.mp3",
            original_url.replace("https://", "http://"),
            original_url.replace("cdn.example.com", "evil.example.com"),
            original_url.replace("cdn.example.com", "cdn.example.com.evil.test"),
            original_url.replace("cdn.example.com", "user:pass@cdn.example.com"),
            original_url.replace("/blog/", "/"),
            original_url.replace("/audios/", "/images/"),
            original_url.replace(".mp3", ".html"),
            original_url.replace("2026/11/", "2026/13/"),
            original_url.replace("2026/11/", "../11/"),
            original_url.replace("2026/11/", "%2e%2e/11/"),
            original_url + "?query=1", original_url + "#fragment", original_url + "#",
            original_url + "\x00", original_url.replace("audios", "audios\\..\\audios"),
            original_url.replace("/media/", "/media2/"), original_url.replace("11/", "11//"),
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                await self.save(tracks=[track(url=url)])
            self.assertEqual(await self.administrative(), original)
        for suffix in ("mp3", "m4a", "wav", "ogg"):
            saved = await self.save(tracks=[track(url=original_url[:-3] + suffix)])
            self.assertTrue(saved["tracks"][0]["url"].endswith("." + suffix))

    async def test_json_content_type_and_parse_errors_are_rejected(self):
        with self.assertRaises(ValidationError):
            await admin_music.update_music_admin(self.request(
                self.admin, {"enabled": False, "tracks": []}, "text/plain",
            ))
        request = self.request(self.admin)

        class InvalidJSONRequest:
            headers = request.headers
            ctx = request.ctx

            @property
            def json(self):
                raise BadRequest("invalid JSON")

        with self.assertRaises(ValidationError):
            await admin_music.update_music_admin(InvalidJSONRequest())
        saved = self.data(await admin_music.update_music_admin(self.request(
            self.admin, {"enabled": False, "tracks": []}, "application/json; charset=UTF-8",
        )))
        self.assertEqual(saved["tracks"], [])

    async def test_disabling_or_clearing_does_not_require_upload_credentials(self):
        await self.save()
        # Saved CDN URLs can be retained while closing the player even if access keys rotate.
        self.assertEqual((await self.save(False))["tracks"], [track()])
        self.config.CDN_BASE_URL = ""
        saved = await self.save(False, [])
        self.assertEqual(saved["tracks"], [])

    async def test_safe_schema_generation_creates_table_and_preserves_saved_and_other_data(self):
        category = await Category.create(name="retained", slug="retained", weight=7)
        await connections.get("default").execute_script("DROP TABLE music_settings")
        await Tortoise.generate_schemas(safe=True)
        saved = await self.save()
        await Tortoise.generate_schemas(safe=True)
        self.assertEqual(await self.administrative(), saved)
        self.assertEqual(await MusicSettings.all().count(), 1)
        self.assertEqual((await Category.get(id=category.id)).weight, 7)

    async def test_public_and_admin_routes_are_registered(self):
        from app.api import register_blueprints
        app = Sanic("music_routes", configure_logging=False)
        register_blueprints(app)
        app.router.finalize()
        routes = {(route.path, method) for route in app.router.routes for method in route.methods}
        self.assertIn(("api/music", "GET"), routes)
        self.assertIn(("api/admin/music", "GET"), routes)
        self.assertIn(("api/admin/music", "PUT"), routes)


if __name__ == "__main__":
    unittest.main()
