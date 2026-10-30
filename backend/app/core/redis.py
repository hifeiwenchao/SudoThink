"""Redis 客户端封装。"""
from __future__ import annotations

from typing import Optional

from redis.asyncio import Redis, from_url

from app.core.config import settings

_redis: Optional[Redis] = None


async def init_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(settings.REDIS_URL, decode_responses=True)
        await _redis.ping()
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


def get_redis() -> Redis:
    if _redis is None:
        raise RuntimeError("Redis 尚未初始化，请确认应用已启动。")
    return _redis
