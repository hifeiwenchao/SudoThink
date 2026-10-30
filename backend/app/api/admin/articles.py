"""管理后台 - 文章管理。"""
from sanic import Blueprint, Request

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.article import Article
from app.models.user import User

bp = Blueprint("admin_articles", url_prefix="")


def _ensure_admin(user: User) -> None:
    if not user.is_admin:
        raise ForbiddenError("admin only")


@bp.get("/articles")
@login_required
async def list_all_articles(request: Request):
    """管理后台文章列表（包含未发布）。"""
    _ensure_admin(request.ctx.user)

    page = max(int(request.args.get("page", 1)), 1)
    size = min(max(int(request.args.get("size", 10)), 1), 100)
    q = (request.args.get("q") or "").strip()

    qs = Article.all()
    if q:
        qs = qs.filter(title__icontains=q)

    total = await qs.count()
    articles = (
        await qs.order_by("-created_at")
        .offset((page - 1) * size)
        .limit(size)
        .prefetch_related("author")
    )

    items = [
        {
            "id": a.id,
            "title": a.title,
            "slug": a.slug,
            "is_published": a.is_published,
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

    article = await Article.get_or_none(id=aid)
    if article is None:
        raise NotFoundError("article not found")

    await article.delete()
    return success(message="deleted")
