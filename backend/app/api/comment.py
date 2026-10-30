"""评论 API。"""
from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.article import Article
from app.models.comment import Comment
from app.models.user import User
from app.schemas.common import CommentIn

bp = Blueprint("comment")


def _comment_dict(c: Comment) -> dict:
    return {
        "id": c.id,
        "content": c.content,
        "is_approved": c.is_approved,
        "created_at": c.created_at.isoformat(),
        "parent_id": c.parent_id,
        "author": {
            "id": c.author.id,
            "username": c.author.username,
            "nickname": c.author.nickname,
            "avatar": c.author.avatar,
        },
    }


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
    if not await Article.exists(id=aid):
        raise NotFoundError("article not found")
    comments = (
        await Comment.filter(article_id=aid, is_approved=True)
        .order_by("-created_at")
        .prefetch_related("author")
    )
    return success([_comment_dict(c) for c in comments])


@bp.post("/articles/<aid:int>/comments")
@login_required
async def create_comment(request: Request, aid: int):
    """提交评论，默认未审核（is_approved=False）。"""
    if not await Article.exists(id=aid):
        raise NotFoundError("article not found")
    try:
        payload = CommentIn(**(request.json or {}))
    except PydanticValidationError as e:
        raise ValidationError(str(e))

    if payload.parent_id is not None:
        parent = await Comment.get_or_none(id=payload.parent_id, article_id=aid)
        if parent is None:
            raise NotFoundError("parent comment not found")
        if not parent.is_approved:
            raise ValidationError("parent comment is not approved yet")

    comment = await Comment.create(
        article_id=aid,
        author=request.ctx.user,
        content=payload.content,
        parent_id=payload.parent_id,
        is_approved=False,
    )
    await comment.fetch_related("author")
    return success(
        _comment_dict(comment),
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
    return success([_comment_dict(c) for c in comments])


@bp.post("/comments/<cid:int>/approve")
@login_required
async def approve_comment(request: Request, cid: int):
    """审核通过评论。"""
    comment = await Comment.get_or_none(id=cid).prefetch_related("author", "article")
    if comment is None:
        raise NotFoundError("comment not found")
    await _ensure_can_moderate(request.ctx.user, comment.article)

    if comment.is_approved:
        return success(_comment_dict(comment), message="already approved")

    comment.is_approved = True
    await comment.save(update_fields=["is_approved", "updated_at"])
    return success(_comment_dict(comment), message="approved")


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
