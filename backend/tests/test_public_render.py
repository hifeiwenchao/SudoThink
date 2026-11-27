"""Initial HTML preserves the SPA and protects unpublished content."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from tests import test_article_visibility as fixtures

TEMPLATE = '<!doctype html><html><head><title>Old</title><meta name="robots" content="index"><link rel="canonical" href="old"></head><body><div id="app"></div><script type="module" src="/assets/app.js"></script></body></html>'

class PublicRenderTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.ArticleVisibilityTests.asyncSetUp
    asyncTearDown = fixtures.ArticleVisibilityTests.asyncTearDown

    async def render(self, path):
        from app.api import public_render as render
        request = SimpleNamespace(headers={"X-Public-Path": path}, args={"path": "/evil"})
        with patch.object(render, "load_template", AsyncMock(return_value=TEMPLATE)), patch.object(render.settings, "PUBLIC_SITE_URL", "https://public.test"):
            return await render.public_page(request)

    async def test_safe_article_and_no_view_increment(self):
        initial_views = self.published.view_count
        self.published.title = 'Title </title><script>alert(1)</script>'
        self.published.summary = 'Summary " onload="bad'
        self.published.content = '<p>Visible &amp; readable</p><script>secret()</script><style>hide</style><img alt="Diagram"><p>&lt;/noscript&gt;&lt;script&gt;attack()&lt;/script&gt;</p>'
        await self.published.save()
        response = await self.render(f'/articles/{self.published.id}')
        body = response.body.decode()
        self.assertEqual(response.status, 200)
        self.assertIn(f'href="https://public.test/articles/{self.published.id}"', body)
        self.assertIn('Title &lt;/title&gt;&lt;script&gt;', body)
        self.assertIn('Visible &amp; readable', body)
        self.assertIn('Diagram', body)
        self.assertNotIn('secret()', body)
        self.assertNotIn('attack()</script>', body)
        self.assertNotIn('hide', body)
        self.assertIn('src="/assets/app.js"', body)
        await self.published.refresh_from_db()
        self.assertEqual(self.published.view_count, initial_views)

    async def test_draft_trash_unknown_real_404(self):
        from datetime import datetime, timezone
        missing = await self.render('/articles/999999')
        draft = await self.render(f'/articles/{self.draft.id}')
        self.published.deleted_at = datetime.now(timezone.utc)
        await self.published.save()
        for response in (missing, draft, await self.render(f'/articles/{self.published.id}'), await self.render('/unknown')):
            self.assertEqual(response.status, 404)
            self.assertEqual(response.headers['X-Robots-Tag'], 'noindex, nofollow')
            self.assertIn('页面不存在', response.body.decode())
            self.assertIn('/assets/app.js', response.body.decode())
        self.assertNotIn(self.draft.title, draft.body.decode())

    async def test_public_routes_and_ignore_query_path(self):
        for path in ('/', '/about', '/tools'):
            response = await self.render(path)
            self.assertEqual(response.status, 200)
            self.assertIn(f'href="https://public.test{path}"', response.body.decode())
            self.assertNotIn('/evil', response.body.decode())

    async def test_trailing_slashes_match_vue_and_canonicalize(self):
        for path in ('/about', '/tools', f'/articles/{self.published.id}'):
            response = await self.render(path + '/')
            self.assertEqual(response.status, 200)
            self.assertIn(f'href="https://public.test{path}"', response.body.decode())
            self.assertNotIn(f'href="https://public.test{path}/"', response.body.decode())

    async def test_cover_image_is_absolute_safe_and_escaped(self):
        for cover, expected in (
            ('/images/cover.jpg?x=1&y=2', 'https://public.test/images/cover.jpg?x=1&amp;y=2'),
            ('images/relative.jpg', 'https://public.test/images/relative.jpg'),
            ('https://cdn.test/cover.jpg', 'https://cdn.test/cover.jpg'),
            ('javascript:alert(1)', 'https://public.test/favicon.svg'),
            ('data:image/svg+xml,bad', 'https://public.test/favicon.svg'),
            ('', 'https://public.test/favicon.svg'),
        ):
            self.published.cover = cover
            await self.published.save()
            body = (await self.render(f'/articles/{self.published.id}')).body.decode()
            self.assertIn(f'<meta property="og:image" content="{expected}">', body)

    async def test_template_failure_returns_503(self):
        from app.api import public_render as render
        with patch.object(render, 'load_template', AsyncMock(side_effect=TimeoutError)):
            response = await render.public_page(SimpleNamespace(headers={'X-Public-Path': '/'}))
        self.assertEqual(response.status, 503)
        self.assertIn('noindex', response.headers['X-Robots-Tag'])

class TemplateFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_caps_bytes_and_rejects_invalid_template(self):
        from app.api import public_render as render
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        with patch.object(render, 'build_opener', return_value=opener):
            response.read.return_value = b'x' * (render.MAX_TEMPLATE_BYTES + 1)
            with self.assertRaises(ValueError):
                render._fetch_template()
            response.read.assert_called_with(render.MAX_TEMPLATE_BYTES + 1)
            response.read.return_value = b'<html><head></head><body>no executable entry</body></html>'
            with self.assertRaises(ValueError):
                render._fetch_template()
            response.read.return_value = TEMPLATE.encode()
            self.assertEqual(render._fetch_template(), TEMPLATE)
            opener.open.assert_called_with(render.settings.SPA_TEMPLATE_URL, timeout=3)

    async def test_text_extraction_supports_legacy_text_and_safe_alt(self):
        from app.api.public_render import plain_content
        self.assertEqual(plain_content('Plain text\nNext line'), 'Plain text\nNext line')
        self.assertEqual(plain_content('Literal <example> & escaped &lt;example&gt;\nNext'), 'Literal <example> & escaped &lt;example&gt;\nNext')
        self.assertEqual(plain_content('<img alt><p>Safe</p><script>hidden</script>'), 'Safe')

    async def test_cache_and_no_redirect(self):
        from app.api import public_render as render
        from urllib.request import Request
        self.assertIsNone(render.NoRedirect().redirect_request(Request('http://localhost/a'), None, 302, '', {}, 'http://elsewhere/'))
        with patch.object(render, '_fetch_template', return_value=TEMPLATE) as fetch:
            render._template_cache = None
            await render.load_template()
            await render.load_template()
        self.assertEqual(fetch.call_count, 1)
