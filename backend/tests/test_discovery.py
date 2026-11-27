"""Public discovery contracts, visibility, ranking and input safety."""
import unittest
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "discovery-tests-only-32-byte-secret")

from app.api import about, article
from app.core.exceptions import NotFoundError, ValidationError
from app.models.about import AboutPage
from app.models.article import Article
from app.models.category import Category
from app.models.tag import Tag
from tests import test_site_content as fixtures

class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SiteContentTests.asyncSetUp
    asyncTearDown = fixtures.SiteContentTests.asyncTearDown
    request = fixtures.SiteContentTests.request
    data = fixtures.SiteContentTests.data
    about_handler = fixtures.SiteContentTests.about_handler

    async def make_article(self, title, **fields):
        return await Article.create(title=title, slug=title, content="private body", author=self.admin,
                                    **{"is_published": True, **fields})

    async def test_defaults_and_featured_visibility_order_save_and_clear(self):
        self.assertEqual(self.data(await about.get_about_sidebar(self.request())), {"featured_articles": [], "current_projects": []})
        first = await self.make_article("first")
        second = await self.make_article("second")
        draft = await self.make_article("draft", is_published=False)
        deleted = await self.make_article("deleted", deleted_at=datetime.now(timezone.utc))
        save = self.about_handler("update_about_admin", admin=True)
        payload = {"title": "Author", "content": "Bio", "featured_article_ids": [second.id, draft.id, first.id, deleted.id],
                   "current_projects": [{"name": "  Project  ", "description": "  Progress  ", "url": " https://example.com/path "}]}
        saved = self.data(await save(self.request(self.admin, payload)))
        self.assertEqual(saved["current_projects"], [{"name": "Project", "description": "Progress", "url": "https://example.com/path"}])
        result = self.data(await about.get_about_sidebar(self.request()))
        self.assertEqual([a["id"] for a in result["featured_articles"]], [second.id, first.id])
        self.assertEqual(set(result["featured_articles"][0]), {"id", "title", "summary", "category"})
        await save(self.request(self.admin, {"title": "Other", "content": "New"}))
        self.assertEqual(self.data(await about.get_about_sidebar(self.request())), result)
        await save(self.request(self.admin, {"title": "Other", "content": "New", "featured_article_ids": [], "current_projects": []}))
        self.assertEqual(self.data(await about.get_about_sidebar(self.request())), {"featured_articles": [], "current_projects": []})

    async def test_reject_invalid_configuration(self):
        invalid = [{"featured_article_ids": ids} for ids in ([1, 1], [True], [0], ["1"], list(range(1, 7)))]
        invalid += [{"current_projects": projects} for projects in ([{"name": " "}], [{"name": "x" * 61}], [{"name": "ok", "description": "x" * 161}], [{"name": "ok"}] * 4)]
        for url in ("javascript:alert(1)", "//example.com", "https://u:p@example.com", "https://@example.com", "https://example.com/a\\b", "https://example.com/a\nb", "https://example.com:65536", "https://example.com/" + "a" * 512):
            invalid.append({"current_projects": [{"name": "ok", "url": url}]})
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                await self.about_handler("update_about_admin", admin=True)(self.request(self.admin, {"title": "Author", "content": "Bio", **fields}))
        self.assertFalse(await AboutPage.exists(id=1))

    async def test_raw_discovery_configuration_is_only_visible_to_admin(self):
        draft = await self.make_article("private-draft", is_published=False)
        deleted = await self.make_article("deleted", deleted_at=datetime.now(timezone.utc))
        settings = {"featured_article_ids": [draft.id, deleted.id],
                    "current_projects": [{"name": "Project", "description": "", "url": "https://example.com"}]}
        saved = self.data(await self.about_handler("update_about_admin", admin=True)(self.request(
            self.admin, {"title": "Author", "content": "Biography", **settings})))
        admin = self.data(await self.about_handler("get_about_admin", admin=True)(self.request(self.admin)))
        for key, value in settings.items():
            self.assertEqual(saved[key], value)
            self.assertEqual(admin[key], value)
        public = self.data(await about.get_about(self.request()))
        self.assertEqual(public["content"], "Biography")
        for key in settings:
            self.assertNotIn(key, public)
        sidebar = self.data(await about.get_about_sidebar(self.request()))
        self.assertEqual(sidebar["featured_articles"], [])
        self.assertNotIn("featured_article_ids", sidebar)
        self.assertEqual(sidebar["current_projects"], settings["current_projects"])

    async def test_related_ranks_category_then_shared_tags_without_views(self):
        cat = await Category.create(name="Code", slug="code")
        tags = [await Tag.create(name=n, slug=n) for n in ("one", "two")]
        current = await self.make_article("current", category=cat)
        await current.tags.add(*tags)
        outside = await self.make_article("outside")
        await outside.tags.add(*tags)
        same = []
        for count in range(3):
            item = await self.make_article(f"same-{count}", category=cat)
            if count:
                await item.tags.add(*tags[:count])
            same.append(item)
        for title, fields in (("draft", {"is_published": False}), ("deleted", {"deleted_at": datetime.now(timezone.utc)})):
            hidden = await self.make_article(title, category=cat, **fields)
            await hidden.tags.add(*tags)
        await self.make_article("unrelated")
        with patch.object(article, "record_article_view", new=AsyncMock()) as record:
            result = self.data(await article.get_related_articles(self.request(), current.id))
        record.assert_not_awaited()
        self.assertEqual([a["id"] for a in result], [a.id for a in reversed(same)])
        self.assertEqual(result[0]["category"], {"id": cat.id, "name": "Code", "slug": "code"})
        self.assertEqual(set(result[0]), {"id", "title", "summary", "category"})
        await Article.filter(id__in=[a.id for a in same]).update(is_published=False)
        self.assertEqual([a["id"] for a in self.data(await article.get_related_articles(self.request(), current.id))], [outside.id])

    async def test_related_stable_ties_null_category_and_hidden_source(self):
        current = await self.make_article("current")
        self.assertEqual(self.data(await article.get_related_articles(self.request(), current.id)), [])
        tag = await Tag.create(name="tag", slug="tag")
        await current.tags.add(tag)
        first, second = await self.make_article("first"), await self.make_article("second")
        for item in (first, second):
            await item.tags.add(tag)
        same_time = datetime.now(timezone.utc)
        await Article.filter(id__in=[first.id, second.id]).update(published_at=same_time, created_at=same_time)
        for _ in range(2):
            self.assertEqual([a["id"] for a in self.data(await article.get_related_articles(self.request(), current.id))], [second.id, first.id])
        for hidden in (await self.make_article("draft", is_published=False), await self.make_article("deleted", deleted_at=same_time)):
            with self.assertRaises(NotFoundError):
                await article.get_related_articles(self.request(), hidden.id)
        with self.assertRaises(NotFoundError):
            await article.get_related_articles(self.request(), 999999)

    async def test_category_without_tags_and_persisted_unsafe_project_links(self):
        cat = await Category.create(name="Code", slug="code")
        source = await self.make_article("source", category=cat)
        other = await self.make_article("other", category=cat)
        self.assertEqual([a["id"] for a in self.data(await article.get_related_articles(self.request(), source.id))], [other.id])
        await AboutPage.create(id=1, current_projects=[{"name": "Unsafe", "url": "https://user:pass@example.com"}, {"name": "Safe"}])
        self.assertEqual(self.data(await about.get_about_sidebar(self.request()))["current_projects"], [{"name": "Safe", "description": "", "url": ""}])
