"""Article validation boundaries use real SQLite persistence."""
import unittest
from pydantic import ValidationError as PydanticValidationError
from tests import test_site_content as fixtures
from app.api import article
from app.core.exceptions import ValidationError
from app.models.article import Article
from app.schemas.article import ArticleCreateIn, ArticleUpdateIn


class ArticleSchemaTests(unittest.TestCase):
    def test_create_and_update_validate_title_lengths_and_safe_cover(self):
        invalid = ({"title": " \n\t"}, {"title": ""}, {"title": "t" * 256},
                   {"summary": "s" * 513}, {"cover": "https://example.com/" + "c" * 500})
        urls = ("/cover.png", "//example.com/a", "javascript:alert(1)", "https:///image",
                "https://u:p@example.com/a", "https://example.com\\@evil.test/a",
                "https://example.com/a\nb", "https://example.com/a\u200bb", "https://example.com:bad/a",
                "https://example.com/a\n", "\thttps://example.com/a")
        for schema in (ArticleCreateIn, ArticleUpdateIn):
            self.assertEqual(schema(title="  标题  ", content="").title, "标题")
            for payload in (*invalid, *({"cover": url} for url in urls)):
                with self.subTest(schema=schema, payload=payload), self.assertRaises(PydanticValidationError):
                    schema(**{"title": "Title", "content": "", **payload})
            self.assertEqual(len(schema(title="t" * 255, summary="s" * 512, content="").summary), 512)
            for cover, expected in (("  ", ""), (" https://example.com/a?x=1#cover ", "https://example.com/a?x=1#cover"),
                                    ("http://localhost:8000/image", "http://localhost:8000/image")):
                self.assertEqual(schema(title="Title", content="", cover=cover).cover, expected)

    def test_update_preserves_omission_blanks_and_rejects_null_text(self):
        self.assertEqual(ArticleUpdateIn().model_dump(exclude_unset=True), {})
        self.assertEqual(ArticleUpdateIn(summary="", content="", cover="").model_dump(exclude_unset=True),
                         {"summary": "", "content": "", "cover": ""})
        for field in ("title", "summary", "content", "cover"):
            with self.subTest(field=field), self.assertRaises(PydanticValidationError):
                ArticleUpdateIn(**{field: None})


class ArticleInputApiTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.SiteContentTests.asyncSetUp
    asyncTearDown = fixtures.SiteContentTests.asyncTearDown
    request = fixtures.SiteContentTests.request
    data = fixtures.SiteContentTests.data

    async def test_invalid_create_update_raise_422_without_mutation(self):
        saved = await Article.create(title="Saved", slug="saved", summary="Keep", content="Body", author=self.admin)
        for payload in ({"title": " "}, {"summary": "x" * 513}, {"cover": "javascript:alert(1)"}, {"title": None}):
            for update in (False, True):
                request = self.request(self.admin, payload if update else {"title": "Title", "content": "Body", **payload})
                with self.subTest(update=update, payload=payload), self.assertRaises(ValidationError) as caught:
                    if update:
                        await article.update_article(request, saved.id)
                    else:
                        await article.create_article(request)
                self.assertEqual(caught.exception.status, 422)
            self.assertEqual(await Article.all().count(), 1)
            await saved.refresh_from_db()
            self.assertEqual((saved.title, saved.summary, saved.content), ("Saved", "Keep", "Body"))

    async def test_update_preserves_omitted_fields_and_clears_explicit_blanks(self):
        created = self.data(await article.create_article(self.request(self.admin, {
            "title": "  Saved  ", "summary": "Summary", "content": "Body", "cover": "https://example.com/image",
        })))
        self.assertEqual(created["title"], "Saved")
        edited = self.data(await article.update_article(self.request(self.admin, {"summary": ""}), created["id"]))
        self.assertEqual((edited["title"], edited["summary"], edited["content"], edited["cover"]),
                         ("Saved", "", "Body", "https://example.com/image"))
        edited = self.data(await article.update_article(self.request(self.admin, {"content": "", "cover": " "}), created["id"]))
        self.assertEqual((edited["content"], edited["cover"]), ("", ""))
