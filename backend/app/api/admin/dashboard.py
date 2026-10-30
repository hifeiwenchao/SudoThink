"""管理后台 - 数据概览。"""
from sanic import Blueprint, Request

from app.core.exceptions import ForbiddenError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.article import Article
from app.models.comment import Comment
from app.models.user import User

bp = Blueprint("admin_dashboard", url_prefix="")


def _ensure_admin(user: User) -> None:
    if not user.is_admin:
        raise ForbiddenError("admin only")


@bp.get("/dashboard")
@login_required
async def dashboard(request: Request):
    """后台数据概览。"""
    user: User = request.ctx.user
    _ensure_admin(user)

    total_users = await User.count()
    total_articles = await Article.count()
    total_comments = await Comment.count()
    pending_comments = await Comment.filter(is_approved=False).count()

    return success({
        "total_users": total_users,
        "total_articles": total_articles,
        "total_comments": total_comments,
        "pending_comments": pending_comments,
    })
