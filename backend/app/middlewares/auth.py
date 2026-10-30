"""鉴权装饰器。"""
from __future__ import annotations

from functools import wraps
from typing import Callable

import jwt
from sanic import Request

from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from app.models.user import User


def login_required(handler: Callable) -> Callable:
    """需要登录态的路由装饰器。"""

    @wraps(handler)
    async def _wrapper(request: Request, *args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise UnauthorizedError("missing or invalid Authorization header")
        token = auth[len("Bearer "):].strip()
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            raise UnauthorizedError("token expired")
        except jwt.InvalidTokenError:
            raise UnauthorizedError("invalid token")

        user_id = payload.get("sub")
        user = await User.get_or_none(id=user_id)
        if user is None:
            raise UnauthorizedError("user not found")
        if not user.is_active:
            raise UnauthorizedError("user is inactive")

        request.ctx.user = user
        request.ctx.jwt_payload = payload
        return await handler(request, *args, **kwargs)

    return _wrapper
