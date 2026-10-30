"""管理后台 - 评论审核。"""
from sanic import Blueprint, Request

from app.core.exceptions import ForbiddenError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.comment import Comment
from app.models.user import User

bp = Blueprint("admin_comments", url_prefix="")


def _ensure_admin(user: User) -> None:
    if not user.is_admin:
        raise ForbiddenError("admin only")


@bp.get("/comments/pending")
@login_required
async def list_all_pending_comments(request: Request):
    """管理后台：所有待审核评论。"""
    _ensure_admin(request.ctx.user)

    page = max(int(request.args.get("page", 1)), 1)
    size = min(max(int(request.args.get("size", 10)), 1), 100)

    qs = Comment.filter(is_approved=False)
    total = await qs.count()
    comments = (
        await qs.order_by("-created_at")
        .offset((page - 1) * size)
        .limit(size)
        .prefetch_related("author", "article")
    )

    items = [
        {
            "id": c.id,
            "content": c.content,
            "created_at": c.created_at.isoformat(),
            "article": {"id": c.article.id, "title": c.article.title},
            "author": {
                "id": c.author.id,
                "username": c.author.username,
                "nickname": c.author.nickname,
            },
        }
        for c in comments
    ]
    return success({"items": items, "total": total, "page": page, "size": size})
