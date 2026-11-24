"""鉴权 API。"""
from sanic import Blueprint, Request
from sanic.exceptions import BadRequest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ForbiddenError, UnauthorizedError, ValidationError
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
        body = request.json
        if not isinstance(body, dict):
            raise ValidationError("login body must be a JSON object")
        payload = LoginIn.model_validate(body)
    except (PydanticValidationError, BadRequest) as e:
        raise ValidationError("invalid login request") from e

    user = await User.get_or_none(username=payload.username)
    try:
        valid_password = user is not None and verify_password(payload.password, user.password_hash)
    except ValueError:
        valid_password = False
    if not valid_password:
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
