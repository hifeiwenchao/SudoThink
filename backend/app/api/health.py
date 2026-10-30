"""健康检查。"""
from sanic import Blueprint, Request

from app.core.redis import get_redis
from app.core.response import success

bp = Blueprint("health", url_prefix="/health")


@bp.get("")
async def health(request: Request):
    redis_ok = False
    try:
        await get_redis().ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return success({"status": "ok", "redis": redis_ok})
