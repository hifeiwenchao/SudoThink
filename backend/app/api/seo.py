"""Public crawl endpoints with a configured origin and bounded SQL reads."""
from math import ceil
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from sanic import Blueprint, Request
from sanic.response import text

from app.api.article import _positive_query_int
from app.core.config import settings
from app.core.exceptions import ValidationError
from app.models.article import Article

bp = Blueprint("seo", url_prefix="/seo")
SITEMAP_PAGE_SIZE = 10000


def _public_base() -> str:
    base = settings.PUBLIC_SITE_URL.strip().rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise ValidationError("PUBLIC_SITE_URL must be an HTTP(S) site origin")
    return base


def _xml(root: str, entries: list[str]):
    return text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<{root} xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(entries) + f'</{root}>',
        content_type="application/xml; charset=utf-8",
    )


@bp.get("/sitemap.xml")
async def sitemap(request: Request):
    base = _public_base()
    page = _positive_query_int(request.args, "page")
    qs = Article.filter(is_published=True, deleted_at__isnull=True)
    total = await qs.count()
    pages = max(1, ceil(total / SITEMAP_PAGE_SIZE))
    if page is None and pages > 1:
        # Sitemap indexes themselves are limited to 50,000 children.
        if pages > 50000:
            raise ValidationError("sitemap capacity exceeded")
        return _xml("sitemapindex", [
            f'<sitemap><loc>{escape(base + "/sitemap.xml?page=" + str(number))}</loc></sitemap>'
            for number in range(1, pages + 1)
        ])
    page = page or 1
    if page > pages:
        raise ValidationError("sitemap page out of range")
    entries = []
    if page == 1:
        entries.extend(f'<url><loc>{escape(base + path)}</loc></url>' for path in ("/", "/about", "/tools"))
    rows = await qs.order_by("id").offset((page - 1) * SITEMAP_PAGE_SIZE).limit(SITEMAP_PAGE_SIZE).values("id", "updated_at")
    entries.extend(
        f'<url><loc>{escape(base + "/articles/" + str(row["id"]))}</loc>'
        f'<lastmod>{escape(row["updated_at"].isoformat())}</lastmod></url>'
        for row in rows
    )
    return _xml("urlset", entries)


@bp.get("/robots.txt")
async def robots(request: Request):
    return text("User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /login\nSitemap: " + _public_base() + "/sitemap.xml\n")
