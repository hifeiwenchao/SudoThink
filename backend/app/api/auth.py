"""鉴权 API。"""
from sanic import Blueprint, Request

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.response import success
from app.core.security import create_access_token, verify_password
from app.middlewares.auth import login_required
from app.models.user import User
from app.schemas.auth import LoginIn, TokenOut, UserOut

bp = Blueprint("auth", url_prefix="/auth")


def _user_out(user: User) -> dict:
    return UserOut(
        id=user.id,
        username=user.username,
        email=user.email,
        nickname=user.nickname,
        avatar=user.avatar,
        bio=user.bio,
        is_admin=user.is_admin,
        created_at=user.created_at,
    ).model_dump(mode="json")


@bp.post("/register")
async def register(request: Request):
    raise ForbiddenError("registration is disabled")


@bp.post("/login")
async def login(request: Request):
    try:
        payload = LoginIn(**(request.json or {}))
    except PydanticValidationError as e:
        raise ValidationError(str(e))

    user = await User.get_or_none(username=payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise UnauthorizedError("invalid username or password")
    if not user.is_active:
        raise UnauthorizedError("user is inactive")

    token = create_access_token(user.id, extra_claims={"is_admin": user.is_admin})
    return success(
        TokenOut(access_token=token, user=UserOut(**_user_out(user))).model_dump(mode="json"),
        message="login success",
    )


@bp.get("/me")
@login_required
async def me(request: Request):
    user: User = request.ctx.user
    return success(_user_out(user))
