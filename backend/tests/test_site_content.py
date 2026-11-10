"""Category management and About content, using only an isolated SQLite database."""
import importlib
import importlib.util
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# Never load developer database credentials when importing application settings.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "site-content-tests-only-32-byte-secret")

from tortoise import Tortoise
from tortoise.exceptions import IntegrityError

from app.api import category as categories
from app.api import article as articles
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from app.core.security import create_access_token
from app.models.article import Article
from app.models.category import Category
from app.models.user import User


class SiteContentTests(unittest.IsolatedAsyncioTestCase):
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

    def request(self, user=None, payload=None):
        headers = {}
        if user is not None:
            headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
        return SimpleNamespace(headers=headers, ctx=SimpleNamespace(), json=payload)

    def data(self, response):
        body = json.loads(response.body)
        self.assertEqual(body["code"], 0)
        return body["data"]

    def update_category_handler(self):
        handler = getattr(categories, "update_category", None)
        self.assertIsNotNone(handler, "Category editing endpoint is missing")
        return handler

    def about_handler(self, name, admin=False):
        path = "app.api.admin.about" if admin else "app.api.about"
        self.assertIsNotNone(importlib.util.find_spec(path), "About endpoint is missing")
        return getattr(importlib.import_module(path), name)

    async def test_categories_default_to_zero_weight_and_stable_priority_order(self):
        first = await Category.create(name="First", slug="first")
        second = await Category.create(name="Second", slug="second")
        featured = self.data(await categories.create_category(
            self.request(self.admin, {"name": "Featured", "weight": 7})
        ))
        result = self.data(await categories.list_categories(self.request()))
        self.assertEqual([item["id"] for item in result], [featured["id"], first.id, second.id])
        self.assertEqual([item["weight"] for item in result], [7, 0, 0])

    async def test_category_crud_persists_edited_fields_and_normalizes_names(self):
        created = self.data(await categories.create_category(self.request(self.admin, {
            "name": "  Python  ", "slug": "  python  ", "description": "Original", "weight": 2,
        })))
        self.assertEqual((created["name"], created["slug"]), ("Python", "python"))
        edited = self.data(await self.update_category_handler()(self.request(self.admin, {
            "name": "  Engineering  ", "slug": "engineering", "description": "Updated",
            "weight": 999999,
        }), created["id"]))
        persisted = await Category.get(id=created["id"])
        self.assertEqual(edited["name"], "Engineering")
        self.assertEqual(persisted.description, "Updated")
        self.assertEqual(persisted.slug, "engineering")
        self.assertEqual(persisted.weight, 999999)
        await categories.delete_category(self.request(self.admin), persisted.id)
        self.assertFalse(await Category.exists(id=persisted.id))

    async def test_category_edit_allows_unchanged_unique_fields(self):
        category = await Category.create(name="Original", slug="original")
        result = self.data(await self.update_category_handler()(self.request(self.admin, {
            "name": "Original", "slug": "original", "weight": 3,
        }), category.id))
        self.assertEqual(result["weight"], 3)

    async def test_deleting_category_retains_article_without_category(self):
        category = await Category.create(name="Used", slug="used")
        article = await Article.create(
            title="Retained", slug="retained", content="Body", author=self.admin, category=category
        )
        await categories.delete_category(self.request(self.admin), category.id)
        await article.refresh_from_db()
        self.assertIsNone(article.category_id)

    async def test_category_mutations_require_administrator(self):
        category = await Category.create(name="Protected", slug="protected")
        handlers = (
            (categories.create_category, ()),
            (self.update_category_handler(), (category.id,)),
            (categories.delete_category, (category.id,)),
        )
        for handler, args in handlers:
            for user, error in ((None, UnauthorizedError), (self.reader, ForbiddenError)):
                with self.subTest(handler=handler.__name__, user=user), self.assertRaises(error):
                    await handler(self.request(user, {"name": "New"}), *args)
        self.assertEqual(await Category.all().count(), 1)

    async def test_category_create_and_edit_reject_invalid_input(self):
        category = await Category.create(name="Existing", slug="existing")
        invalid = (
            {"name": "   "},
            {"name": "Valid", "slug": "x" * 65},
            {"name": "Valid", "description": "x" * 256},
            {"name": "Valid", "weight": -1},
            {"name": "Valid", "weight": 1000000},
            {"name": "Valid", "weight": 1.5},
            {"name": "Valid", "weight": "1"},
            {"name": "Valid", "weight": True},
        )
        for payload in invalid:
            for handler, args in (
                (categories.create_category, ()),
                (self.update_category_handler(), (category.id,)),
            ):
                with self.subTest(payload=payload, handler=handler.__name__):
                    with self.assertRaises(ValidationError):
                        await handler(self.request(self.admin, payload), *args)
        self.assertEqual(await Category.all().count(), 1)

    async def test_category_duplicate_name_or_slug_is_a_validation_error(self):
        await Category.create(name="Existing", slug="existing")
        other = await Category.create(name="Other", slug="other")
        for payload in (
            {"name": "Existing", "slug": "new-slug"},
            {"name": "New name", "slug": "existing"},
        ):
            for handler, args in (
                (categories.create_category, ()),
                (self.update_category_handler(), (other.id,)),
            ):
                with self.subTest(payload=payload, handler=handler.__name__):
                    with self.assertRaises(ValidationError):
                        await handler(self.request(self.admin, payload), *args)
        self.assertEqual(await Category.all().count(), 2)

    async def test_category_concurrent_duplicate_is_a_validation_error(self):
        with patch.object(Category, "create", side_effect=IntegrityError("duplicate key")):
            with self.assertRaises(ValidationError):
                await categories.create_category(self.request(self.admin, {"name": "Unique"}))

    async def test_category_generated_slug_respects_database_length(self):
        # Transliteration can expand a valid 64-character Chinese category name.
        result = self.data(await categories.create_category(
            self.request(self.admin, {"name": "编" * 64})
        ))
        self.assertLessEqual(len(result["slug"]), 64)
        self.assertTrue(result["slug"])

    async def test_category_update_and_delete_missing_returns_not_found(self):
        with self.assertRaises(NotFoundError):
            await self.update_category_handler()(
                self.request(self.admin, {"name": "Missing"}), 999999
            )
        with self.assertRaises(NotFoundError):
            await categories.delete_category(self.request(self.admin), 999999)

    async def test_about_defaults_are_public_and_do_not_create_a_record(self):
        response = await self.about_handler("get_about")(self.request())
        self.assertEqual(self.data(response), {
            "id": 1, "title": "关于我", "content": "", "updated_at": None,
        })
        from app.models.about import AboutPage
        self.assertEqual(await AboutPage.all().count(), 0)

    async def test_about_admin_save_is_persistent_and_updates_the_singleton(self):
        save = self.about_handler("update_about_admin", admin=True)
        public_read = self.about_handler("get_about")
        admin_read = self.about_handler("get_about_admin", admin=True)
        first = self.data(await save(self.request(self.admin, {
            "title": "  About the author  ", "content": "<h2>Hello</h2><p>Biography</p>",
        })))
        self.assertEqual(first["title"], "About the author")
        self.assertIsInstance(first["updated_at"], str)
        self.assertEqual(self.data(await public_read(self.request())), first)
        self.assertEqual(self.data(await admin_read(self.request(self.admin))), first)
        await save(self.request(self.admin, {"title": "Updated", "content": ""}))
        updated = self.data(await public_read(self.request()))
        self.assertEqual((updated["title"], updated["content"]), ("Updated", ""))
        from app.models.about import AboutPage
        self.assertEqual(await AboutPage.all().count(), 1)

    async def test_about_administrator_endpoints_require_administrator(self):
        for name in ("get_about_admin", "update_about_admin"):
            handler = self.about_handler(name, admin=True)
            for user, error in ((None, UnauthorizedError), (self.reader, ForbiddenError)):
                with self.subTest(handler=name, user=user), self.assertRaises(error):
                    await handler(self.request(user, {"title": "Valid", "content": "Body"}))

    async def test_about_rejects_invalid_content_without_overwriting_saved_page(self):
        save = self.about_handler("update_about_admin", admin=True)
        await save(self.request(self.admin, {"title": "Saved", "content": "Retained"}))
        for payload in (
            {}, {"title": "   ", "content": "Body"},
            {"title": "x" * 121, "content": "Body"},
            {"title": "Valid", "content": None},
            {"title": "Valid", "content": 123},
            [], "invalid body",
        ):
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                await save(self.request(self.admin, payload))
        result = self.data(await self.about_handler("get_about")(self.request()))
        self.assertEqual((result["title"], result["content"]), ("Saved", "Retained"))

    async def test_article_update_can_keep_clear_and_replace_category(self):
        first = await Category.create(name="First", slug="first")
        second = await Category.create(name="Second", slug="second")
        article = await Article.create(
            title="Categorized", slug="categorized", content="Body", author=self.admin,
            category=first,
        )
        await articles.update_article(self.request(self.admin, {"title": "Changed"}), article.id)
        await article.refresh_from_db()
        self.assertEqual(article.category_id, first.id)
        await articles.update_article(self.request(self.admin, {"category_id": None}), article.id)
        await article.refresh_from_db()
        self.assertIsNone(article.category_id)
        await articles.update_article(self.request(self.admin, {"category_id": second.id}), article.id)
        await article.refresh_from_db()
        self.assertEqual(article.category_id, second.id)

    async def test_article_update_rejects_missing_category_without_partial_changes(self):
        category = await Category.create(name="Existing", slug="existing")
        article = await Article.create(
            title="Original", slug="original", content="Body", author=self.admin,
            category=category,
        )
        with self.assertRaises(ValidationError):
            await articles.update_article(self.request(self.admin, {
                "title": "Should not persist", "category_id": 999999,
            }), article.id)
        await article.refresh_from_db()
        self.assertEqual((article.title, article.category_id), ("Original", category.id))

    async def test_article_create_rejects_missing_category(self):
        with self.assertRaises(ValidationError):
            await articles.create_article(self.request(self.admin, {
                "title": "Invalid category", "content": "Body", "category_id": 999999,
            }))
        self.assertEqual(await Article.all().count(), 0)


if __name__ == "__main__":
    unittest.main()
