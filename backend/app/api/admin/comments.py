"""管理后台 - 评论管理。"""
from sanic import Blueprint, Request

from app.api.comment import _comment_pagination, _moderation_comment_dict
from app.core.exceptions import ForbiddenError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.comment import Comment
from app.models.user import User

bp = Blueprint("admin_comments", url_prefix="")


def _ensure_admin(user: User) -> None:
    if not user.is_admin:
        raise ForbiddenError("admin only")


@bp.get("/comments")
@login_required
async def list_comments(request: Request):
    """管理后台：按文章和审核状态筛选评论。"""
    _ensure_admin(request.ctx.user)

    page, size = _comment_pagination(request, max_size=100)

    status = request.args.get("status", "all")
    if not isinstance(status, str) or status not in {"all", "pending", "approved", "rejected"}:
        raise ValidationError("评论状态必须为 all、pending、approved 或 rejected")

    qs = Comment.all()
    if "article_id" in request.args:
        raw = request.args.get("article_id")
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
            raise ValidationError("文章编号必须为正整数")
        if len(raw) > 10 or int(raw) < 1:
            raise ValidationError("文章编号超出范围")
        qs = qs.filter(article_id=int(raw))
    if status == "pending":
        qs = qs.filter(is_approved=False, is_rejected=False)
    elif status == "approved":
        qs = qs.filter(is_approved=True)
    elif status == "rejected":
        qs = qs.filter(is_approved=False, is_rejected=True)
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
            "article": {
                "id": c.article.id, "title": c.article.title,
                "is_published": c.article.is_published,
            },
        }
        for c in comments
    ]
    return success({"items": items, "total": total, "page": page, "size": size})
