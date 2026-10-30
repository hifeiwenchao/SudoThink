"""管理后台 - 用户管理。"""
from sanic import Blueprint, Request

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.user import User

bp = Blueprint("admin_users", url_prefix="")


def _ensure_admin(user: User) -> None:
    if not user.is_admin:
        raise ForbiddenError("admin only")


@bp.get("/users")
@login_required
async def list_users(request: Request):
    """用户列表。"""
    _ensure_admin(request.ctx.user)

    page = max(int(request.args.get("page", 1)), 1)
    size = min(max(int(request.args.get("size", 10)), 1), 100)

    total = await User.count()
    users = (
        await User.all()
        .order_by("-created_at")
        .offset((page - 1) * size)
        .limit(size)
    )

    items = [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "nickname": u.nickname,
            "avatar": u.avatar,
            "bio": u.bio,
            "is_active": u.is_active,
            "is_admin": u.is_admin,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]
    return success({"items": items, "total": total, "page": page, "size": size})


@bp.post("/users/<uid:int>/toggle-admin")
@login_required
async def toggle_admin(request: Request, uid: int):
    """切换管理员权限。"""
    _ensure_admin(request.ctx.user)

    if uid == request.ctx.user.id:
        raise ForbiddenError("cannot toggle own admin status")

    user = await User.get_or_none(id=uid)
    if user is None:
        raise NotFoundError("user not found")

    user.is_admin = not user.is_admin
    await user.save(update_fields=["is_admin", "updated_at"])

    return success(
        {
            "id": user.id,
            "username": user.username,
            "is_admin": user.is_admin,
        },
        message="admin status toggled",
    )


@bp.post("/users/<uid:int>/toggle-active")
@login_required
async def toggle_active(request: Request, uid: int):
    """切换用户启用状态。"""
    _ensure_admin(request.ctx.user)

    if uid == request.ctx.user.id:
        raise ForbiddenError("cannot toggle own active status")

    user = await User.get_or_none(id=uid)
    if user is None:
        raise NotFoundError("user not found")

    user.is_active = not user.is_active
    await user.save(update_fields=["is_active", "updated_at"])

    return success(
        {
            "id": user.id,
            "username": user.username,
            "is_active": user.is_active,
        },
        message="active status toggled",
    )
