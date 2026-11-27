"""Contact discovery excludes the potentially large biography from its SQL and output."""
import importlib
import unittest
from unittest.mock import patch
from tortoise import connections
from tests import test_site_content as fixtures
from app.models.about import AboutPage


class AboutContactsTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SiteContentTests.asyncSetUp
    asyncTearDown = fixtures.SiteContentTests.asyncTearDown
    request = fixtures.SiteContentTests.request
    data = fixtures.SiteContentTests.data

    async def test_missing_contacts_default_without_creating_page(self):
        handler = getattr(importlib.import_module("app.api.about"), "get_about_contacts", None)
        self.assertIsNotNone(handler, "Lightweight public contact endpoint is missing")
        self.assertEqual(self.data(await handler(self.request())), {
            "github_url": "", "email": "", "x_url": "", "facebook_url": "", "instagram_url": "",
        })
        self.assertEqual(await AboutPage.all().count(), 0)

    async def test_saved_contacts_sql_and_response_exclude_biography_and_keep_full_about(self):
        await AboutPage.create(id=1, title="Author", content="Large biography" * 1000,
                               github_url="https://github.com/author", email="author@example.com")
        api = importlib.import_module("app.api.about")
        handler = getattr(api, "get_about_contacts", None)
        self.assertIsNotNone(handler, "Lightweight public contact endpoint is missing")
        connection = connections.get("default")
        with patch.object(connection, "execute_query_dict", wraps=connection.execute_query_dict) as queries:
            result = self.data(await handler(self.request()))
        self.assertEqual(result, {"github_url": "https://github.com/author", "email": "author@example.com",
                                  "x_url": "", "facebook_url": "", "instagram_url": ""})
        self.assertEqual(len(queries.call_args_list), 1)
        sql = queries.call_args_list[0].args[0].lower()
        self.assertNotIn('"content"', sql)
        self.assertNotIn('"title"', sql)
        full = self.data(await api.get_about(self.request()))
        self.assertEqual((full["title"], full["content"]), ("Author", "Large biography" * 1000))
