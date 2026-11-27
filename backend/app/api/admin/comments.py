"""管理后台 - 评论管理。"""
from sanic import Blueprint, Request
from sanic.exceptions import BadRequest
from tortoise.transactions import in_transaction
from tortoise.timezone import now

from app.api.comment import _comment_pagination, _moderation_comment_dict
from app.core.comment_context import locate_comment_ip_detail
from app.core.exceptions import ForbiddenError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.comment import Comment
from app.models.user import User

bp = Blueprint("admin_comments", url_prefix="")


def _ensure_admin(user: User) -> None:
    if not user.is_admin:
        raise ForbiddenError("admin only")


@bp.post("/comments/batch-review")
@login_required
async def batch_review_comments(request: Request):
    """Apply one moderation decision atomically; keep every comment record."""
    _ensure_admin(request.ctx.user)
    try:
        body = request.json
    except BadRequest as exc:
        raise ValidationError("请求正文必须为有效 JSON") from exc
    if not isinstance(body, dict) or set(body) != {"ids", "action"}:
        raise ValidationError("请提供评论编号和审核操作")
    ids = body["ids"]
    action = body["action"]
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 100
            or any(type(cid) is not int or cid < 1 or cid > 9223372036854775807 for cid in ids)
            or len(set(ids)) != len(ids)):
        raise ValidationError("评论编号须为 1 至 100 个不重复的正整数")
    if not isinstance(action, str) or action not in {"approve", "reject"}:
        raise ValidationError("审核操作必须为 approve 或 reject")
    async with in_transaction() as connection:
        records = await Comment.filter(id__in=ids).using_db(connection).select_for_update()
        if len(records) != len(ids):
            raise ValidationError("部分评论不存在，请刷新后重试")
        updated = await Comment.filter(id__in=ids).using_db(connection).update(
            is_approved=action == "approve", is_rejected=action == "reject", updated_at=now(),
        )
    return success({"updated": updated})


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

    items = []
    locations = {}
    for comment in comments:
        item = {
            **_moderation_comment_dict(comment, include_private=True),
            "article": {
                "id": comment.article.id, "title": comment.article.title,
                "is_published": comment.article.is_published,
            },
        }
        # Stored locations contain only province/city names. Resolve the full
        # location for this private view, once per IP on the current page.
        if comment.ip_address not in locations:
            locations[comment.ip_address] = await locate_comment_ip_detail(comment.ip_address)
        detail = locations[comment.ip_address]
        if detail != "未知":
            item["location_detail"] = detail
        items.append(item)
    return success({"items": items, "total": total, "page": page, "size": size})
