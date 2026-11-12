"""管理后台 - 评论审核。"""
from sanic import Blueprint, Request

from app.api.comment import _comment_pagination, _moderation_comment_dict
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

    page, size = _comment_pagination(request, max_size=100)

    qs = Comment.filter(is_approved=False)
    total = await qs.count()
    comments = (
        await qs.order_by("-created_at", "-id")
        .offset((page - 1) * size)
        .limit(size)
        .prefetch_related("author", "article")
    )

    items = [
        {
            **_moderation_comment_dict(c, include_private=True),
            "article": {"id": c.article.id, "title": c.article.title},
        }
        for c in comments
    ]
    return success({"items": items, "total": total, "page": page, "size": size})
