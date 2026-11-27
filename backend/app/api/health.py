"""Process liveness and bounded, read-only dependency readiness probes."""
import asyncio
from collections.abc import Awaitable

from kombu import Connection
from sanic import Blueprint, Request
from tortoise import connections

from app.core.config import settings
from app.core.redis import get_redis
from app.core.response import fail, success

bp = Blueprint("health", url_prefix="/health")
CHECK_TIMEOUT_SECONDS = 2.5


async def _check_mysql() -> None:
    await connections.get("default").execute_query("SELECT 1")


async def _check_redis() -> None:
    if not await get_redis().ping():
        raise RuntimeError("Redis ping failed")


def _connect_rabbitmq() -> None:
    # Connecting does not declare queues/exchanges or publish/consume messages.
    connection = Connection(settings.CELERY_BROKER_URL, connect_timeout=2)
    try:
        connection.ensure_connection(max_retries=0)
    finally:
        connection.release()


async def _check_rabbitmq() -> None:
    # Kombu is synchronous; never block the web event loop on a broker socket.
    await asyncio.to_thread(_connect_rabbitmq)


async def _probe(check: Awaitable[None]) -> bool:
    try:
        await asyncio.wait_for(check, timeout=CHECK_TIMEOUT_SECONDS)
        return True
    except Exception:
        # Dependency exceptions may contain credentials or connection URLs.
        return False


@bp.get("/live")
async def live(request: Request):
    return success({"status": "ok"})


@bp.get("/ready")
async def ready(request: Request):
    results = await asyncio.gather(
        _probe(_check_mysql()), _probe(_check_redis()), _probe(_check_rabbitmq())
    )
    checks = dict(zip(("mysql", "redis", "rabbitmq"), results))
    healthy = all(results)
    data = {"status": "ok" if healthy else "degraded", "redis": checks["redis"], "checks": checks}
    if not healthy:
        return fail("service unavailable", code=10503, status=503, data=data)
    return success(data)


@bp.get("")
async def health(request: Request):
    """Preserve legacy fields while reporting dependency readiness honestly."""
    return await ready(request)
