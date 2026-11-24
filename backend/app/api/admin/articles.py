"""管理后台 - 文章管理。"""
from datetime import datetime, timezone

from sanic import Blueprint, Request

from app.api.article import _serialize, _positive_query_int, _list_fields
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.article import Article
from app.models.user import User

bp = Blueprint("admin_articles", url_prefix="")


def _ensure_admin(user: User) -> None:
    if not user.is_admin:
        raise ForbiddenError("admin only")


@bp.get("/articles/<aid:int>")
@login_required
async def get_article_admin(request: Request, aid: int):
    """Read an article for editing without counting a public page view."""
    _ensure_admin(request.ctx.user)
    article = await Article.get_or_none(id=aid, deleted_at__isnull=True)
    if article is None:
        raise NotFoundError("article not found")
    return success(await _serialize(article))


@bp.get("/articles")
@login_required
async def list_all_articles(request: Request):
    """管理后台文章列表（包含未发布）。"""
    _ensure_admin(request.ctx.user)

    page = _positive_query_int(request.args, "page", 1)
    size = _positive_query_int(request.args, "size", 10, 100)
    q = (request.args.get("q") or "").strip()

    status = request.args.get("status", "all")
    if status not in {"all", "published", "draft", "trash"}:
        raise ValidationError("invalid article status")
    qs = Article.filter(deleted_at__isnull=status != "trash")
    if status in {"published", "draft"}:
        qs = qs.filter(is_published=status == "published")
    if q:
        qs = qs.filter(title__icontains=q)

    total = await qs.count()
    articles = (
        await qs.order_by("-created_at")
        .offset((page - 1) * size)
        .limit(size)
        .only(*_list_fields()).prefetch_related("author")
    )

    items = [
        {
            "id": a.id,
            "title": a.title,
            "slug": a.slug,
            "is_published": a.is_published,
            "deleted_at": a.deleted_at.isoformat() if a.deleted_at else None,
            "view_count": a.view_count,
            "created_at": a.created_at.isoformat(),
            "author": {"id": a.author.id, "username": a.author.username},
        }
        for a in articles
    ]
    return success({"items": items, "total": total, "page": page, "size": size})


@bp.delete("/articles/<aid:int>")
@login_required
async def delete_article_admin(request: Request, aid: int):
    """管理后台删除文章。"""
    _ensure_admin(request.ctx.user)

    article = await Article.get_or_none(id=aid, deleted_at__isnull=True)
    if article is None:
        raise NotFoundError("article not found")

    article.deleted_at = datetime.now(timezone.utc)
    await article.save(update_fields=["deleted_at", "updated_at"])
    return success(message="deleted")


@bp.post("/articles/<aid:int>/restore")
@login_required
async def restore_article_admin(request: Request, aid: int):
    """Restore without changing publication state or retained relations."""
    _ensure_admin(request.ctx.user)
    article = await Article.get_or_none(id=aid, deleted_at__isnull=False)
    if article is None:
        raise NotFoundError("article not found")
    article.deleted_at = None
    await article.save(update_fields=["deleted_at", "updated_at"])
    return success(await _serialize(article), message="restored")
