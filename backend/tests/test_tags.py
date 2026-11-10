"""Tag management and article associations, using an isolated in-memory SQLite database."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ.setdefault("JWT_SECRET", "tag-tests-only-32-byte-secret-value")

from tortoise import Tortoise
from tortoise.exceptions import IntegrityError
from tortoise.fields.relational import ManyToManyRelation

from app.api import article as articles
from app.api import tag as tags
from app.core.exceptions import ForbiddenError, NotFoundError, UnauthorizedError, ValidationError
from app.core.security import create_access_token
from app.models.article import Article
from app.models.category import Category
from app.models.tag import Tag
from app.models.user import User


class TagTests(unittest.IsolatedAsyncioTestCase):
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

    def update_handler(self):
        handler = getattr(tags, "update_tag", None)
        self.assertIsNotNone(handler, "Tag editing endpoint is missing")
        return handler

    async def article(self, **fields):
        return await Article.create(
            title="Original", slug="original", content="Original body", author=self.admin,
            **fields,
        )

    async def test_tag_crud_normalizes_name_and_slug_and_allows_unchanged_fields(self):
        created = self.data(await tags.create_tag(self.request(self.admin, {
            "name": "  Python  ", "slug": "  python  ",
        })))
        self.assertEqual((created["name"], created["slug"]), ("Python", "python"))
        edited = self.data(await self.update_handler()(self.request(self.admin, {
            "name": "  DevOps  ", "slug": "  engineering  ",
        }), created["id"]))
        self.assertEqual((edited["name"], edited["slug"]), ("DevOps", "engineering"))
        unchanged = self.data(await self.update_handler()(self.request(self.admin, {
            "name": "DevOps", "slug": "engineering",
        }), created["id"]))
        self.assertEqual(unchanged, edited)
        persisted = await Tag.get(id=created["id"])
        self.assertEqual((persisted.name, persisted.slug), ("DevOps", "engineering"))
        await tags.delete_tag(self.request(self.admin), persisted.id)
        self.assertFalse(await Tag.exists(id=persisted.id))

    async def test_public_tag_list_is_an_array_in_id_order_with_existing_fields(self):
        second = await Tag.create(id=20, name="Second", slug="second")
        first = await Tag.create(id=10, name="First", slug="first")
        result = self.data(await tags.list_tags(self.request()))
        self.assertIsInstance(result, list)
        self.assertEqual([item["id"] for item in result], [first.id, second.id])
        self.assertEqual(set(result[0]), {"id", "name", "slug", "created_at"})
        self.assertEqual(result[0]["name"], "First")

    async def test_tag_mutations_require_administrator(self):
        tag = await Tag.create(name="Secure", slug="protected")
        for handler, args in (
            (tags.create_tag, ()), (self.update_handler(), (tag.id,)),
            (tags.delete_tag, (tag.id,)),
        ):
            for user, error in ((None, UnauthorizedError), (self.reader, ForbiddenError)):
                with self.subTest(handler=handler.__name__, user=user), self.assertRaises(error):
                    await handler(self.request(user, {"name": "Edited"}), *args)
        self.assertEqual(await Tag.all().count(), 1)

    async def test_tag_create_and_edit_reject_invalid_bodies_as_422(self):
        tag = await Tag.create(name="Exists", slug="existing")
        for payload in (
            None, [], ["not an object"], "invalid", {}, {"name": "   "},
            {"name": "x" * 65}, {"name": "Valid", "slug": "x" * 65},
            {"name": "Valid", "slug": 4}, {"name": ["invalid"]},
        ):
            for handler, args in (
                (tags.create_tag, ()), (self.update_handler(), (tag.id,)),
            ):
                with self.subTest(payload=payload, handler=handler.__name__):
                    with self.assertRaises(ValidationError) as error:
                        await handler(self.request(self.admin, payload), *args)
                    self.assertEqual(error.exception.status, 422)
        self.assertEqual(await Tag.all().count(), 1)
        await tag.refresh_from_db()
        self.assertEqual((tag.name, tag.slug), ("Exists", "existing"))

    async def test_duplicate_tag_names_and_slugs_are_422_without_changes(self):
        await Tag.create(name="Exists", slug="existing")
        other = await Tag.create(name="Other", slug="other")
        for payload in (
            {"name": "  Exists  ", "slug": "new-slug"},
            {"name": "New", "slug": "existing"},
        ):
            for handler, args in (
                (tags.create_tag, ()), (self.update_handler(), (other.id,)),
            ):
                with self.subTest(payload=payload, handler=handler.__name__):
                    with self.assertRaises(ValidationError) as error:
                        await handler(self.request(self.admin, payload), *args)
                    self.assertEqual(error.exception.status, 422)
        await other.refresh_from_db()
        self.assertEqual((other.name, other.slug), ("Other", "other"))
        self.assertEqual(await Tag.all().count(), 2)

    async def test_database_duplicate_races_are_reported_as_422(self):
        tag = await Tag.create(name="Exists", slug="existing")
        # Persistence may reject a duplicate inserted after the API's uniqueness check.
        for method, handler, args in (
            ("create", tags.create_tag, ()), ("save", self.update_handler(), (tag.id,)),
        ):
            with self.subTest(method=method), patch.object(
                Tag, method, side_effect=IntegrityError("duplicate key")
            ):
                with self.assertRaises(ValidationError) as error:
                    await handler(self.request(self.admin, {"name": "Unique"}), *args)
                self.assertEqual(error.exception.status, 422)

    async def test_generated_slugs_are_nonempty_and_fit_64_characters(self):
        for name in ("编" * 6, "!!!"):
            with self.subTest(name=name):
                created = self.data(await tags.create_tag(self.request(self.admin, {
                    "name": name, "slug": "   ",
                })))
                self.assertTrue(created["slug"].strip())
                self.assertLessEqual(len(created["slug"]), 64)

    async def test_six_chinese_characters_are_accepted_after_trimming_on_create_and_edit(self):
        created = self.data(await tags.create_tag(self.request(self.admin, {
            "name": "  前后端开发者  ", "slug": "x" * 64,
        })))
        self.assertEqual(created["name"], "前后端开发者")
        self.assertEqual(created["slug"], "x" * 64)
        edited = self.data(await self.update_handler()(self.request(self.admin, {
            "name": "  技术生活随笔  ",
        }), created["id"]))
        self.assertEqual(edited["name"], "技术生活随笔")

    async def test_create_rejects_seven_character_names(self):
        for name in ("ABCDEFG", "前后端开发人员", "  前后端开发人员  "):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError) as error:
                    await tags.create_tag(self.request(self.admin, {"name": name}))
                self.assertEqual(error.exception.status, 422)
        self.assertEqual(await Tag.all().count(), 0)

    async def test_seven_character_edit_preserves_original_name_and_slug(self):
        tag = await Tag.create(name="Python", slug="python")
        for name in ("ABCDEFG", "前后端开发人员", "  前后端开发人员  "):
            with self.subTest(name=name):
                with self.assertRaises(ValidationError) as error:
                    await self.update_handler()(self.request(self.admin, {"name": name}), tag.id)
                self.assertEqual(error.exception.status, 422)
                await tag.refresh_from_db()
                self.assertEqual((tag.name, tag.slug), ("Python", "python"))
        self.assertEqual(await Tag.all().count(), 1)

    async def test_legacy_tag_names_are_returned_without_truncation(self):
        legacy = await Tag.create(name="Existing long tag", slug="legacy")
        result = self.data(await tags.list_tags(self.request()))
        self.assertEqual(result[0]["name"], "Existing long tag")
        await legacy.refresh_from_db()
        self.assertEqual(legacy.name, "Existing long tag")

    async def test_tag_edit_and_delete_missing_return_404(self):
        for handler in (self.update_handler(), tags.delete_tag):
            with self.subTest(handler=handler.__name__), self.assertRaises(NotFoundError) as error:
                await handler(self.request(self.admin, {"name": "Absent"}), 999999)
            self.assertEqual(error.exception.status, 404)

    async def test_deleting_a_tag_retains_article_and_its_other_tags(self):
        removed = await Tag.create(name="Gone", slug="removed")
        retained = await Tag.create(name="Kept", slug="retained")
        article = await self.article()
        await article.tags.add(removed, retained)
        await tags.delete_tag(self.request(self.admin), removed.id)
        await article.refresh_from_db()
        self.assertEqual(article.content, "Original body")
        self.assertEqual(await article.tags.all().values_list("id", flat=True), [retained.id])

    async def test_article_create_accepts_multiple_tags_and_deduplicates_ids(self):
        first = await Tag.create(name="First", slug="first")
        second = await Tag.create(name="Second", slug="second")
        result = self.data(await articles.create_article(self.request(self.admin, {
            "title": "Tagged", "content": "Body", "tag_ids": [first.id, second.id, first.id],
        })))
        self.assertCountEqual([tag["id"] for tag in result["tags"]], [first.id, second.id])
        article = await Article.get(id=result["id"])
        self.assertEqual(await article.tags.all().count(), 2)

    async def test_article_update_replaces_and_clears_multiple_tags(self):
        first = await Tag.create(name="First", slug="first")
        second = await Tag.create(name="Second", slug="second")
        third = await Tag.create(name="Third", slug="third")
        article = await self.article()
        await article.tags.add(first)
        result = self.data(await articles.update_article(self.request(self.admin, {
            "tag_ids": [second.id, third.id, second.id],
        }), article.id))
        self.assertCountEqual([tag["id"] for tag in result["tags"]], [second.id, third.id])
        await articles.update_article(self.request(self.admin, {"tag_ids": []}), article.id)
        self.assertEqual(await article.tags.all().count(), 0)

    async def test_article_update_without_tags_or_with_null_preserves_existing_tags(self):
        tag = await Tag.create(name="Kept", slug="retained")
        article = await self.article()
        await article.tags.add(tag)
        for payload in ({"content": "Edited"}, {"tag_ids": None}):
            with self.subTest(payload=payload):
                await articles.update_article(self.request(self.admin, payload), article.id)
                self.assertEqual(await article.tags.all().values_list("id", flat=True), [tag.id])

    async def test_article_create_rejects_any_missing_tag_without_creating_an_article(self):
        tag = await Tag.create(name="Exists", slug="existing")
        with self.assertRaises(ValidationError) as error:
            await articles.create_article(self.request(self.admin, {
                "title": "Invalid", "content": "Body", "tag_ids": [tag.id, 999999],
            }))
        self.assertEqual(error.exception.status, 422)
        self.assertEqual(await Article.all().count(), 0)

    async def test_invalid_tags_cannot_partially_update_article_or_clear_existing_tags(self):
        original = await Tag.create(name="First", slug="original")
        replacement = await Tag.create(name="Next", slug="replacement")
        category = await Category.create(name="Changed category", slug="changed-category")
        article = await self.article()
        await article.tags.add(original)
        with self.assertRaises(ValidationError) as error:
            await articles.update_article(self.request(self.admin, {
                "title": "Should not persist", "content": "Should not persist",
                "category_id": category.id, "is_published": True,
                "tag_ids": [replacement.id, 999999],
            }), article.id)
        self.assertEqual(error.exception.status, 422)
        await article.refresh_from_db()
        self.assertEqual((article.title, article.content), ("Original", "Original body"))
        self.assertIsNone(article.category_id)
        self.assertFalse(article.is_published)
        self.assertIsNone(article.published_at)
        self.assertEqual(await article.tags.all().values_list("id", flat=True), [original.id])

    async def test_failed_tag_association_rolls_back_article_create(self):
        tag = await Tag.create(name="Exists", slug="existing")
        with patch.object(ManyToManyRelation, "add", side_effect=IntegrityError("write failed")):
            with self.assertRaises(IntegrityError):
                await articles.create_article(self.request(self.admin, {
                    "title": "Failed creation", "content": "Body", "tag_ids": [tag.id],
                }))
        self.assertEqual(await Article.all().count(), 0)

    async def test_failed_tag_replacement_rolls_back_article_fields_and_existing_tags(self):
        original = await Tag.create(name="First", slug="original")
        replacement = await Tag.create(name="Next", slug="replacement")
        article = await self.article()
        await article.tags.add(original)
        with patch.object(ManyToManyRelation, "add", side_effect=IntegrityError("write failed")):
            with self.assertRaises(IntegrityError):
                await articles.update_article(self.request(self.admin, {
                    "content": "Should not persist", "tag_ids": [replacement.id],
                }), article.id)
        await article.refresh_from_db()
        self.assertEqual(article.content, "Original body")
        self.assertEqual(await article.tags.all().values_list("id", flat=True), [original.id])

    async def test_article_create_and_update_reject_category_arrays(self):
        category = await Category.create(name="Single", slug="single")
        article = await self.article(category=category)
        for handler, args, payload in (
            (articles.create_article, (), {
                "title": "Invalid", "content": "Body", "category_id": [category.id],
            }),
            (articles.update_article, (article.id,), {
                "content": "Should not persist", "category_id": [category.id],
            }),
        ):
            with self.subTest(handler=handler.__name__), self.assertRaises(ValidationError):
                await handler(self.request(self.admin, payload), *args)
        await article.refresh_from_db()
        self.assertEqual((article.content, article.category_id), ("Original body", category.id))
        self.assertEqual(await Article.all().count(), 1)

    async def test_article_create_and_update_require_tag_id_arrays(self):
        article = await self.article()
        for tag_ids in (1, "1", {"id": 1}, [1, [2]], [True], [1.5]):
            for handler, args, payload in (
                (articles.create_article, (), {"title": "Invalid", "content": "Body"}),
                (articles.update_article, (article.id,), {"content": "Should not persist"}),
            ):
                with self.subTest(tag_ids=tag_ids, handler=handler.__name__):
                    with self.assertRaises(ValidationError):
                        await handler(self.request(self.admin, {**payload, "tag_ids": tag_ids}), *args)
        await article.refresh_from_db()
        self.assertEqual(article.content, "Original body")
        self.assertEqual(await Article.all().count(), 1)


if __name__ == "__main__":
    unittest.main()
