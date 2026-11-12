"""评论 API。"""
from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request

from app.core.comment_context import display_comment_location, get_comment_ip, locate_comment_ip
from app.core.comment_rate_limit import enforce_comment_rate_limit
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.article import Article
from app.models.comment import Comment
from app.models.user import User
from app.schemas.common import CommentIn

bp = Blueprint("comment")


def _comment_dict(c: Comment) -> dict:
    """Public comment fields; never include a contact address or raw IP."""
    return {
        "id": c.id,
        "content": c.content,
        "nickname": c.nickname or (
            (c.author.nickname or c.author.username) if c.author_id is not None else "访客"
        ),
        "location": display_comment_location(c.location),
        "created_at": c.created_at.isoformat(),
        "parent_id": c.parent_id,
    }


def _moderation_comment_dict(c: Comment, *, include_private: bool = False) -> dict:
    result = {
        **_comment_dict(c),
        "is_approved": c.is_approved,
        "author": {
            "id": c.author.id,
            "username": c.author.username,
            "nickname": c.author.nickname,
        } if c.author_id is not None else None,
    }
    if include_private:
        result.update(email=c.email, ip_address=c.ip_address)
    return result


def _comment_pagination(request: Request, max_size: int = 50) -> tuple[int, int]:
    values = []
    for name, default in (("page", "1"), ("size", "10")):
        raw = request.args.get(name, default)
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
            raise ValidationError("分页参数必须为正整数")
        # Bound the decimal length before int() to avoid unbounded integer parsing.
        if len(raw) > 10:
            raise ValidationError("分页参数超出范围")
        values.append(int(raw))
    page, size = values
    if page < 1 or size < 1 or size > max_size:
        raise ValidationError(f"page 必须大于 0，size 必须为 1 至 {max_size}")
    return page, size


async def _ensure_can_moderate(user: User, article: Article) -> None:
    """仅文章作者或管理员可审核。"""
    if user.is_admin:
        return
    if article.author_id == user.id:
        return
    raise ForbiddenError("no permission to moderate")


@bp.get("/articles/<aid:int>/comments")
async def list_comments(request: Request, aid: int):
    """公开列表：仅返回审核通过的评论。"""
    if not await Article.exists(id=aid, is_published=True):
        raise NotFoundError("article not found")
    page, size = _comment_pagination(request)
    qs = Comment.filter(article_id=aid, is_approved=True)
    total = await qs.count()
    comments = (
        await qs.order_by("-created_at", "-id")
        .offset((page - 1) * size).limit(size)
        .prefetch_related("author")
    )
    return success({"items": [_comment_dict(c) for c in comments], "total": total,
                    "page": page, "size": size})


@bp.post("/articles/<aid:int>/comments")
async def create_comment(request: Request, aid: int):
    """提交评论，默认未审核（is_approved=False）。"""
    if not await Article.exists(id=aid, is_published=True):
        raise NotFoundError("article not found")
    try:
        payload = CommentIn.model_validate(request.json or {})
    except PydanticValidationError as e:
        first = e.errors(include_input=False, include_url=False)[0]
        field = first["loc"][0] if first["loc"] else ""
        messages = {
            "nickname": "昵称必填，限 1 至 32 个中文、英文字母、数字或下划线",
            "email": "邮箱格式不正确或超过 254 个字符",
            "content": "评论正文必填，限 1 至 1000 个字符",
            "parent_id": "回复的评论编号无效",
        }
        raise ValidationError(messages.get(field, "不支持的评论字段或格式")) from None

    if payload.parent_id is not None:
        parent = await Comment.get_or_none(id=payload.parent_id, article_id=aid)
        if parent is None:
            raise NotFoundError("parent comment not found")
        if not parent.is_approved:
            raise ValidationError("parent comment is not approved yet")

    ip_address = get_comment_ip(request)
    await enforce_comment_rate_limit(ip_address)
    location = await locate_comment_ip(ip_address)
    comment = await Comment.create(
        article_id=aid,
        author=None,
        nickname=payload.nickname,
        email=str(payload.email),
        ip_address=ip_address,
        location=location,
        content=payload.content,
        parent_id=payload.parent_id,
        is_approved=False,
    )
    return success(
        {"id": comment.id, "is_approved": False},
        message="评论已提交，等待审核",
    )


@bp.get("/articles/<aid:int>/comments/pending")
@login_required
async def list_pending_comments(request: Request, aid: int):
    """审核中评论列表：仅文章作者或管理员可见。"""
    article = await Article.get_or_none(id=aid)
    if article is None:
        raise NotFoundError("article not found")
    await _ensure_can_moderate(request.ctx.user, article)

    comments = (
        await Comment.filter(article_id=aid, is_approved=False)
        .order_by("-created_at")
        .prefetch_related("author")
    )
    return success([
        _moderation_comment_dict(c, include_private=request.ctx.user.is_admin)
        for c in comments
    ])


@bp.post("/comments/<cid:int>/approve")
@login_required
async def approve_comment(request: Request, cid: int):
    """审核通过评论。"""
    comment = await Comment.get_or_none(id=cid).prefetch_related("author", "article")
    if comment is None:
        raise NotFoundError("comment not found")
    await _ensure_can_moderate(request.ctx.user, comment.article)

    if comment.is_approved:
        return success(
            _moderation_comment_dict(comment, include_private=request.ctx.user.is_admin),
            message="already approved",
        )

    comment.is_approved = True
    await comment.save(update_fields=["is_approved", "updated_at"])
    return success(
        _moderation_comment_dict(comment, include_private=request.ctx.user.is_admin),
        message="approved",
    )


@bp.post("/comments/<cid:int>/reject")
@login_required
async def reject_comment(request: Request, cid: int):
    """驳回评论：直接删除。"""
    comment = await Comment.get_or_none(id=cid).prefetch_related("article")
    if comment is None:
        raise NotFoundError("comment not found")
    await _ensure_can_moderate(request.ctx.user, comment.article)

    await comment.delete()
    return success(message="rejected")


@bp.delete("/comments/<cid:int>")
@login_required
async def delete_comment(request: Request, cid: int):
    """删除评论：本人、文章作者或管理员可删。"""
    comment = await Comment.get_or_none(id=cid).prefetch_related("article")
    if comment is None:
        raise NotFoundError("comment not found")

    user: User = request.ctx.user
    if (
        comment.author_id != user.id
        and comment.article.author_id != user.id
        and not user.is_admin
    ):
        raise ForbiddenError("no permission")
    await comment.delete()
    return success(message="deleted")
