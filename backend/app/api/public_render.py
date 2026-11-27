"""Crawlable public HTML using the currently deployed SPA entry, without view writes."""
import asyncio
from html import escape
from html.parser import HTMLParser
import re
from time import monotonic
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from sanic import Blueprint, Request
from sanic.response import html

from app.api.seo import _public_base
from app.core.config import settings
from app.models.about import AboutPage
from app.models.article import Article

bp = Blueprint("public_render", url_prefix="/seo")
MAX_TEMPLATE_BYTES = 2 * 1024 * 1024
RICH_TEXT_TAG = re.compile(r'<\/?(?:p|div|h[1-6]|ul|ol|li|blockquote|pre|code|img|video|br|strong|b|em|i|u|s|a|hr|table|thead|tbody|tfoot|tr|th|td|script|iframe|style)\b[^>]*>', re.I)
_template_cache = None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch_template() -> str:
    # Only deployment configuration supplies this URL. Never use Host or path headers.
    parsed = urlsplit(settings.SPA_TEMPLATE_URL)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid SPA_TEMPLATE_URL")
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(settings.SPA_TEMPLATE_URL, timeout=3) as response:
        raw = response.read(MAX_TEMPLATE_BYTES + 1)
    if len(raw) > MAX_TEMPLATE_BYTES:
        raise ValueError("SPA template exceeds size limit")
    template = raw.decode("utf-8")
    if not re.search(r'</head\s*>', template, re.I) or not re.search(r'</body\s*>', template, re.I) or not re.search(r'<script\b', template, re.I):
        raise ValueError("SPA template is not a built entry")
    return template


async def load_template() -> str:
    global _template_cache
    now = monotonic()
    if _template_cache and _template_cache[0] == settings.SPA_TEMPLATE_URL and now < _template_cache[1]:
        return _template_cache[2]
    template = await asyncio.wait_for(asyncio.to_thread(_fetch_template), timeout=3.2)
    _template_cache = (settings.SPA_TEMPLATE_URL, monotonic() + 5, template)
    return template


class PlainContent(HTMLParser):
    """Extract readable text while dropping executable/hidden rich-text contents."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "iframe", "noscript"}:
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "pre", "blockquote", "table", "thead", "tbody", "tfoot", "tr"}:
            self.parts.append("\n")
        if tag == "img":
            self.parts.append(" " + (dict(attrs).get("alt") or "") + " ")

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()
        elif not self.hidden and tag in {"p", "div", "li", "pre", "blockquote", "table", "thead", "tbody", "tfoot", "tr"}:
            self.parts.append("\n")
        elif not self.hidden and tag in {"th", "td"}:
            self.parts.append("\t")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_content(value: str) -> str:
    # Match the frontend's legacy text detection, preserving literal tags such
    # as <example> and entity spellings in old plain-text/Markdown articles.
    if not RICH_TEXT_TAG.search(value):
        return value.replace('\r\n', '\n').replace('\r', '\n').strip()
    parser = PlainContent()
    parser.feed(value)
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


def _public_image(cover: str) -> str:
    base = _public_base() + '/'
    fallback = urljoin(base, 'favicon.svg')
    if not cover or '\\' in cover or any(ord(char) < 32 for char in cover):
        return fallback
    try:
        image = urljoin(base, cover)
        parsed = urlsplit(image)
        if parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username and not parsed.password:
            return image
    except ValueError:
        pass
    return fallback


def _render(template, title, description, canonical, content, status, article=False, cover=''):
    robots = "index, follow" if status == 200 else "noindex, nofollow"
    # The trusted build template owns scripts/styles. Replace only its SEO tags.
    template = re.sub(r'<title\b[^>]*>.*?</title\s*>', '', template, flags=re.I | re.S)
    template = re.sub(r'<meta\b(?=[^>]*(?:name\s*=\s*[\'"](?:description|robots)[\'"]|property\s*=\s*[\'"]og:[^\'"]*[\'"]))[^>]*>', '', template, flags=re.I)
    template = re.sub(r'<link\b(?=[^>]*rel\s*=\s*[\'"]canonical[\'"])[^>]*>', '', template, flags=re.I)
    title, description, canonical = map(escape, (title, description, canonical))
    metadata = (f'<title>{title}</title><meta name="description" content="{description}">'
                f'<meta name="robots" content="{robots}"><link rel="canonical" href="{canonical}">'
                f'<meta property="og:title" content="{title}"><meta property="og:description" content="{description}">'
                f'<meta property="og:url" content="{canonical}"><meta property="og:type" content="{"article" if article else "website"}">'
                f'<meta property="og:image" content="{escape(_public_image(cover))}">'
                '<meta property="og:site_name" content="SudoThink">')
    template = re.sub(r'</head\s*>', lambda _: metadata + '</head>', template, count=1, flags=re.I)
    readable = f'<noscript><main><h1>{title}</h1><div style="white-space:pre-wrap">{escape(content)}</div></main></noscript>'
    template = re.sub(r'</body\s*>', lambda _: readable + '</body>', template, count=1, flags=re.I)
    headers = {"Cache-Control": "no-cache"}
    if status != 200:
        headers["X-Robots-Tag"] = robots
    return html(template, status=status, headers=headers)


@bp.get('/page')
async def public_page(request: Request):
    try:
        template = await load_template()
    except (OSError, ValueError, TimeoutError):
        return html('<!doctype html><html lang="zh-CN"><head><meta name="robots" content="noindex"></head><body>页面暂时无法加载，请稍后重试。</body></html>', status=503,
                    headers={"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store", "Retry-After": "5"})
    # Frontend NGINX overwrites this header with its normalized path. Query strings
    # remain on the browser URL for the SPA and never affect SQL/canonical URLs.
    path = request.headers.get('X-Public-Path', '')
    # Vue Router accepts a terminal slash; canonical public URLs omit it.
    if path.endswith('/') and path != '/':
        path = path.rstrip('/') or '/'
    cover = ''
    title, description, content, status = '页面不存在 | SudoThink', '页面不存在或已移除。', '页面不存在或已移除，请返回首页浏览。', 404
    if path in {'/', '/about', '/tools'}:
        status = 200
        if path == '/':
            title, description = '记录、思考，然后构建 | SudoThink', 'SudoThink：分享技术探索、实践经验与日常思考。'
            content = description
        elif path == '/tools':
            title, description = '工具箱 | SudoThink', '浏览器本地工具：时间戳、二维码、JSON 与 cron。'
            content = description
        else:
            about = await AboutPage.get_or_none(id=1)
            title = (about.title if about else '关于我') + ' | SudoThink'
            content = plain_content(about.content) if about else '关于我'
            description = ' '.join(content.split())[:200] or '关于我'
    elif re.fullmatch(r'/articles/[0-9]{1,10}', path):
        article = await Article.filter(id=int(path.rsplit('/', 1)[1]), is_published=True, deleted_at__isnull=True).first()
        if article:
            status = 200
            title = article.title + ' | SudoThink'
            content = plain_content(article.content)
            cover = article.cover
            description = plain_content(article.summary) or ' '.join(content.split())[:200]
    canonical_path = path if status == 200 else '/'
    return _render(template, title, description, _public_base() + canonical_path, content, status,
                   article=status == 200 and path.startswith('/articles/'), cover=cover)
