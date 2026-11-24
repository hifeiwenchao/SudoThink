"""Real SQLite regressions for retained article trash and public SEO."""
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from tests import test_article_visibility as fixtures
from app.api import article as public
from app.api.admin import articles as admin
from app.api import comment
from app.core.exceptions import NotFoundError, ValidationError
from app.models.article import Article
from app.models.comment import Comment

class ArticleTrashTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.ArticleVisibilityTests.asyncSetUp
    asyncTearDown = fixtures.ArticleVisibilityTests.asyncTearDown
    def request(self, user=None, **args):
        request = fixtures.ArticleVisibilityTests.request(self, user)
        request.args = args
        return request

    def data(self, response):
        return json.loads(response.body)["data"]

    async def test_delete_retains_content_relations_and_restore_state(self):
        published_at = datetime(2025, 1, 2, tzinfo=timezone.utc)
        self.draft.is_published = True
        self.draft.published_at = published_at
        await self.draft.save()
        record = await Comment.create(article=self.draft, content="Retain", nickname="Guest")
        await admin.delete_article_admin(self.request(self.admin), self.draft.id)
        retained = await Article.get(id=self.draft.id)
        self.assertIsNotNone(retained.deleted_at)
        self.assertEqual(await retained.tags.all().count(), 1)
        self.assertTrue(await Comment.exists(id=record.id))
        for handler in (public.get_article, admin.get_article_admin):
            with self.assertRaises(NotFoundError):
                await handler(self.request(self.admin), retained.id)
        for handler in (comment.list_comments, comment.create_comment):
            with self.assertRaises(NotFoundError):
                await handler(self.request(), retained.id)
        data = self.data(await admin.restore_article_admin(self.request(self.admin), retained.id))
        self.assertIsNone(data["deleted_at"])
        self.assertTrue(data["is_published"])
        self.assertEqual(data["published_at"], published_at.isoformat())
        self.assertEqual(len(data["tags"]), 1)

    async def test_status_lists_and_public_projection(self):
        await admin.delete_article_admin(self.request(self.admin), self.published.id)
        for status, ids in (("all", [self.draft.id]), ("draft", [self.draft.id]), ("published", []), ("trash", [self.published.id])):
            data = self.data(await admin.list_all_articles(self.request(self.admin, status=status)))
            self.assertEqual([item["id"] for item in data["items"]], ids)
            for item in data["items"]:
                self.assertIn("deleted_at", item)
                self.assertNotIn("content", item)
        self.draft.is_published = True
        await self.draft.save()
        with patch.object(Article, "fetch_related", side_effect=AssertionError("list refetched relations")):
            items = self.data(await public.list_articles(self.request()))["items"]
        self.assertEqual([item["id"] for item in items], [self.draft.id])
        self.assertNotIn("content", items[0])

    async def test_bad_pagination_filters_are_validation_errors(self):
        for handler, user in ((public.list_articles, None), (admin.list_all_articles, self.admin)):
            for args in ({"page":"x"}, {"size":"0"}, {"page":"-1"}, {"size":"101"}):
                with self.assertRaises(ValidationError):
                    await handler(self.request(user, **args))
        for args in ({"category_id":"x"}, {"tag_id":"-1"}):
            with self.assertRaises(ValidationError):
                await public.list_articles(self.request(**args))
        with self.assertRaises(ValidationError):
            await admin.list_all_articles(self.request(self.admin, status="unknown"))

    async def test_seo_excludes_drafts_and_trash_uses_configured_origin(self):
        from app.api import seo
        await Article.create(title="Trash", slug="trash", content="Private", author=self.admin, is_published=True, deleted_at=datetime.now(timezone.utc))
        with patch.object(seo.settings, "PUBLIC_SITE_URL", "https://public.test", create=True):
            body = (await seo.sitemap(self.request())).body.decode()
            self.assertIn(f"https://public.test/articles/{self.published.id}", body)
            self.assertNotIn(f"/articles/{self.draft.id}<", body)
            self.assertNotIn("trash", body)
            self.assertIn("https://public.test/about", body)
            robots = (await seo.robots(self.request())).body.decode()
            self.assertIn("Sitemap: https://public.test/sitemap.xml", robots)

    async def test_trash_edit_rejected_and_public_delete_retains_article(self):
        await public.delete_article(self.request(self.admin), self.draft.id)
        self.assertTrue(await Article.exists(id=self.draft.id, deleted_at__isnull=False))
        request = self.request(self.admin)
        request.json = {"title": "No edit"}
        with self.assertRaises(NotFoundError):
            await public.update_article(request, self.draft.id)

    async def test_lists_do_not_select_body_and_query_count_is_constant(self):
        from tortoise import connections
        connection = connections.get("default")
        original = connection.execute_query
        statements = []
        async def trace(query, *args, **kwargs):
            statements.append(query)
            return await original(query, *args, **kwargs)
        with patch.object(connection, "execute_query", side_effect=trace):
            await public.list_articles(self.request())
        public_queries = len(statements)
        article_sql = [sql for sql in statements if 'FROM "articles"' in sql and 'COUNT(' not in sql]
        self.assertTrue(article_sql)
        self.assertTrue(all('"content"' not in sql for sql in article_sql))
        for index in range(4):
            await Article.create(title=f"Extra {index}", slug=f"extra-{index}", content="Large body", author=self.admin, is_published=True)
        statements.clear()
        with patch.object(connection, "execute_query", side_effect=trace):
            await public.list_articles(self.request())
        self.assertEqual(len(statements), public_queries)
        statements.clear()
        with patch.object(connection, "execute_query", side_effect=trace):
            await admin.list_all_articles(self.request(self.admin))
        article_sql = [sql for sql in statements if 'FROM "articles"' in sql and 'COUNT(' not in sql]
        self.assertTrue(article_sql)
        self.assertTrue(all('"content"' not in sql for sql in article_sql))

    async def test_dashboard_excludes_recycled_articles_and_their_comments(self):
        from app.api.admin.dashboard import dashboard
        await Comment.create(article=self.published, content="Pending", nickname="Guest")
        await admin.delete_article_admin(self.request(self.admin), self.published.id)
        result = self.data(await dashboard(self.request(self.admin)))
        self.assertEqual(result["total_articles"], 1)
        self.assertEqual(result["total_comments"], 0)
        self.assertEqual(result["pending_comments"], 0)

    async def test_sitemap_index_and_children_are_bounded_and_complete(self):
        from app.api import seo
        import xml.etree.ElementTree as ET
        for index in range(4):
            await Article.create(title=f"Extra {index}", slug=f"page-{index}", content="Body", author=self.admin, is_published=True)
        with patch.object(seo.settings, "PUBLIC_SITE_URL", "https://public.test"), patch.object(seo, "SITEMAP_PAGE_SIZE", 2):
            index = ET.fromstring((await seo.sitemap(self.request())).body)
            self.assertTrue(index.tag.endswith("sitemapindex"))
            self.assertEqual(len(index), 3)
            locations = []
            for page in (1, 2, 3):
                child = ET.fromstring((await seo.sitemap(self.request(page=str(page)))).body)
                locations.extend(entry[0].text for entry in child)
            articles = [url for url in locations if "/articles/" in url]
            self.assertEqual(len(articles), 5)
            self.assertEqual(len(set(articles)), 5)
            self.assertEqual(len(locations), 8)
            with self.assertRaises(ValidationError):
                await seo.sitemap(self.request(page="4"))

    async def test_sitemap_rejects_untrusted_origin_configuration(self):
        from app.api import seo
        for origin in ("javascript:bad", "https://public.test/?bad=1", "https://u:p@public.test", "https://public.test/subpath"):
            with patch.object(seo.settings, "PUBLIC_SITE_URL", origin):
                with self.assertRaises(ValidationError):
                    await seo.sitemap(self.request())
