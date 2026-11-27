"""文章 API。"""
from datetime import datetime, timezone

from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request
from slugify import slugify
from tortoise.transactions import in_transaction
from tortoise.expressions import Case, Q, When
from tortoise.functions import Count

from app.core.article_views import record_article_view
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.article import Article
from app.models.category import Category
from app.models.tag import Tag
from app.schemas.article import ArticleCreateIn, ArticleUpdateIn

bp = Blueprint("article", url_prefix="/articles")

RECOMMENDATION_FIELDS = ("id", "title", "summary", "category_id")


def recommendation_dict(article: Article) -> dict:
    category = article.category
    return {"id": article.id, "title": article.title, "summary": article.summary,
            "category": {"id": category.id, "name": category.name, "slug": category.slug} if category else None}


@bp.get("/<aid:int>/related")
async def get_related_articles(request: Request, aid: int):
    source = await Article.get_or_none(id=aid, is_published=True, deleted_at__isnull=True).only("id", "category_id")
    if source is None:
        raise NotFoundError("article not found")
    tag_ids = await source.tags.all().values_list("id", flat=True)
    if source.category_id is None and not tag_ids:
        return success([])
    related = Q(tags__id__in=tag_ids)
    if source.category_id is not None:
        related |= Q(category_id=source.category_id)
    # SQL ranks/limits candidates without fetching article bodies or recording views.
    query = Article.filter(related, is_published=True, deleted_at__isnull=True).exclude(id=aid).annotate(
        same_category=Case(When(category_id=source.category_id, then=int(source.category_id is not None)), default=0),
        shared_tags=Count("tags", distinct=True, _filter=Q(tags__id__in=tag_ids)),
    )
    results = await query.order_by("-same_category", "-shared_tags", "-published_at", "-created_at", "-id").limit(3).only(
        *RECOMMENDATION_FIELDS
    ).prefetch_related("category")
    return success([recommendation_dict(item) for item in results])


async def _selected_tags(tag_ids: list[int]) -> list[Tag]:
    unique_ids = list(dict.fromkeys(tag_ids))
    tags = await Tag.filter(id__in=unique_ids)
    if len(tags) != len(unique_ids):
        raise ValidationError("tag not found")
    return tags


async def _serialize(article: Article, *, include_content: bool = True, fetch_related: bool = True) -> dict:
    if fetch_related:
        await article.fetch_related("author", "category", "tags")
    data = {
        "id": article.id,
        "title": article.title,
        "slug": article.slug,
        "summary": article.summary,
        "cover": article.cover,
        "is_published": article.is_published,
        "deleted_at": article.deleted_at.isoformat() if article.deleted_at else None,
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

    if include_content:
        data["content"] = article.content
    return data


def _positive_query_int(args, name: str, default: int | None = None, maximum: int = 2147483647) -> int | None:
    raw = args.get(name, default)
    if raw is None:
        return None
    try:
        value = int(raw)
    except (ValueError, TypeError, OverflowError):
        raise ValidationError(f"{name} must be a positive integer") from None
    if str(raw) != str(value) or not 1 <= value <= maximum:
        raise ValidationError(f"{name} must be between 1 and {maximum}")
    return value


def _list_fields() -> list[str]:
    return [name for name in Article._meta.db_fields if name != "content"]


@bp.get("")
async def list_articles(request: Request):
    page = _positive_query_int(request.args, "page", 1)
    size = _positive_query_int(request.args, "size", 10, 100)
    q = (request.args.get("q") or "").strip()
    category_id = _positive_query_int(request.args, "category_id")
    tag_id = _positive_query_int(request.args, "tag_id")

    qs = Article.filter(is_published=True, deleted_at__isnull=True)
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
        .only(*_list_fields()).prefetch_related("author", "category", "tags")
    )
    items = [await _serialize(a, include_content=False, fetch_related=False) for a in articles]
    return success({"items": items, "total": total, "page": page, "size": size})


@bp.get("/<aid:int>")
async def get_article(request: Request, aid: int):
    article = await Article.get_or_none(id=aid, is_published=True, deleted_at__isnull=True)
    if article is None:
        raise NotFoundError("article not found")
    data = await _serialize(article)
    if getattr(request, "method", "GET") == "GET":
        data["view_count"] = await record_article_view(article)
    return success(data)


@bp.post("")
@login_required
async def create_article(request: Request):
    try:
        payload = ArticleCreateIn(**(request.json or {}))
    except PydanticValidationError as e:
        raise ValidationError(str(e))

    async with in_transaction():
        if payload.category_id is not None and not await Category.exists(id=payload.category_id):
            raise ValidationError("category not found")
        tags = await _selected_tags(payload.tag_ids)

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
        if tags:
            await article.tags.add(*tags)
    return success(await _serialize(article), message="created")


@bp.put("/<aid:int>")
@login_required
async def update_article(request: Request, aid: int):
    article = await Article.get_or_none(id=aid, deleted_at__isnull=True).prefetch_related("author")
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
    update_fields = ["updated_at"]
    async with in_transaction():
        tags = await _selected_tags(tag_ids) if tag_ids is not None else None
        if "category_id" in data:
            category_id = data.pop("category_id")
            if category_id is not None and not await Category.exists(id=category_id):
                raise ValidationError("category not found")
            article.category_id = category_id
            update_fields.append("category_id")

        publish_changed_to_true = (
            "is_published" in data
            and data["is_published"]
            and not article.is_published
        )

        for k, v in data.items():
            setattr(article, k, v)
            update_fields.append(k)

        if publish_changed_to_true and article.published_at is None:
            article.published_at = datetime.now(timezone.utc)
            update_fields.append("published_at")

        await article.save(update_fields=update_fields)

        if tags is not None:
            await article.tags.clear()
            if tags:
                await article.tags.add(*tags)

    return success(await _serialize(article), message="updated")


@bp.delete("/<aid:int>")
@login_required
async def delete_article(request: Request, aid: int):
    article = await Article.get_or_none(id=aid, deleted_at__isnull=True)
    if article is None:
        raise NotFoundError("article not found")
    if article.author_id != request.ctx.user.id and not request.ctx.user.is_admin:
        raise ForbiddenError("no permission")
    article.deleted_at = datetime.now(timezone.utc)
    await article.save(update_fields=["deleted_at", "updated_at"])
    return success(message="deleted")
