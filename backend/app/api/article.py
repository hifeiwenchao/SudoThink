"""文章 API。"""
from datetime import datetime, timezone

from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request
from slugify import slugify

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.article import Article
from app.models.category import Category
from app.models.tag import Tag
from app.schemas.article import ArticleCreateIn, ArticleUpdateIn

bp = Blueprint("article", url_prefix="/articles")


async def _serialize(article: Article) -> dict:
    await article.fetch_related("author", "category", "tags")
    return {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "summary": article.summary,
        "content": article.content,
        "cover": article.cover,
        "is_published": article.is_published,
        "view_count": article.view_count,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "created_at": article.created_at.isoformat(),
        "updated_at": article.updated_at.isoformat(),
        "author": {
            "id": article.author.id,
            "username": article.author.username,
            "nickname": article.author.nickname,
            "avatar": article.author.avatar,
        },
        "category": (
            {
                "id": article.category.id,
                "name": article.category.name,
                "slug": article.category.slug,
            }
            if article.category
            else None
        ),
        "tags": [
            {"id": t.id, "name": t.name, "slug": t.slug}
            for t in article.tags
        ],
    }


@bp.get("")
async def list_articles(request: Request):
    page = max(int(request.args.get("page", 1)), 1)
    size = min(max(int(request.args.get("size", 10)), 1), 100)
    q = (request.args.get("q") or "").strip()
    category_id = request.args.get("category_id")
    tag_id = request.args.get("tag_id")

    qs = Article.filter(is_published=True)
    if q:
        qs = qs.filter(title__icontains=q)
    if category_id:
        qs = qs.filter(category_id=int(category_id))
    if tag_id:
        qs = qs.filter(tags__id=int(tag_id))

    total = await qs.count()
    articles = (
        await qs.order_by("-created_at")
        .offset((page - 1) * size)
        .limit(size)
        .prefetch_related("author", "category", "tags")
    )
    items = [await _serialize(a) for a in articles]
    return success({"items": items, "total": total, "page": page, "size": size})


@bp.get("/<aid:int>")
async def get_article(request: Request, aid: int):
    article = await Article.get_or_none(id=aid)
    if article is None:
        raise NotFoundError("article not found")
    article.view_count += 1
    await article.save(update_fields=["view_count"])
    return success(await _serialize(article))


@bp.post("")
@login_required
async def create_article(request: Request):
    try:
        payload = ArticleCreateIn(**(request.json or {}))
    except PydanticValidationError as e:
        raise ValidationError(str(e))

    slug_base = slugify(payload.title) or "article"
    slug = slug_base
    suffix = 1
    while await Article.exists(slug=slug):
        suffix += 1
        slug = f"{slug_base}-{suffix}"

    article = await Article.create(
        title=payload.title,
        slug=slug,
        summary=payload.summary,
        content=payload.content,
        cover=payload.cover,
        is_published=payload.is_published,
        published_at=datetime.now(timezone.utc) if payload.is_published else None,
        author=request.ctx.user,
        category_id=payload.category_id,
    )
    if payload.tag_ids:
        tags = await Tag.filter(id__in=payload.tag_ids)
        await article.tags.add(*tags)
    return success(await _serialize(article), message="created")


@bp.put("/<aid:int>")
@login_required
async def update_article(request: Request, aid: int):
    article = await Article.get_or_none(id=aid).prefetch_related("author")
    if article is None:
        raise NotFoundError("article not found")
    if article.author_id != request.ctx.user.id and not request.ctx.user.is_admin:
        raise ForbiddenError("no permission")

    try:
        payload = ArticleUpdateIn(**(request.json or {}))
    except PydanticValidationError as e:
        raise ValidationError(str(e))

    data = payload.model_dump(exclude_unset=True)
    tag_ids = data.pop("tag_ids", None)
    category_id = data.pop("category_id", None)

    publish_changed_to_true = (
        "is_published" in data
        and data["is_published"]
        and not article.is_published
    )

    for k, v in data.items():
        setattr(article, k, v)

    if category_id is not None:
        await Category.get_or_none(id=category_id)  # 校验存在
        article.category_id = category_id

    if publish_changed_to_true and article.published_at is None:
        article.published_at = datetime.now(timezone.utc)

    await article.save()

    if tag_ids is not None:
        await article.tags.clear()
        if tag_ids:
            tags = await Tag.filter(id__in=tag_ids)
            await article.tags.add(*tags)

    return success(await _serialize(article), message="updated")


@bp.delete("/<aid:int>")
@login_required
async def delete_article(request: Request, aid: int):
    article = await Article.get_or_none(id=aid)
    if article is None:
        raise NotFoundError("article not found")
    if article.author_id != request.ctx.user.id and not request.ctx.user.is_admin:
        raise ForbiddenError("no permission")
    await article.delete()
    return success(message="deleted")
