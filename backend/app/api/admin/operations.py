"""Administrator-only CDN cache operations."""
from sanic import Blueprint, Request
from sanic.exceptions import BadRequest

from app.core.cdn import (
    CDNError, get_cdn_configuration, list_cdn_tasks, preload_cdn_cache, refresh_cdn_cache,
)
from app.core.config import settings
from app.core.exceptions import APIError, ForbiddenError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required

bp = Blueprint("admin_operations", url_prefix="/operations/cdn")


def _ensure_admin(request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")


def _payload(request, fields):
    content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise ValidationError("request body must be JSON")
    try:
        payload = request.json
    except BadRequest:
        raise ValidationError("invalid JSON request body") from None
    if not isinstance(payload, dict) or set(payload) != set(fields):
        raise ValidationError("请求字段必须为 " + "、".join(fields))
    return payload


async def _run(operation, **kwargs):
    if not get_cdn_configuration(settings)["enabled"]:
        raise APIError("CDN 服务尚未配置或配置无效", code=10503, status=503)
    try:
        return await operation(**kwargs, config=settings)
    except ValueError as exc:
        raise ValidationError(str(exc)) from None
    except CDNError as exc:
        raise APIError(str(exc), code=10000 + exc.status, status=exc.status) from None


@bp.get("/config")
@login_required
async def get_config(request: Request):
    _ensure_admin(request)
    return success(get_cdn_configuration(settings))


@bp.post("/refresh")
@login_required
async def refresh(request: Request):
    _ensure_admin(request)
    payload = _payload(request, ("urls", "object_type"))
    return success(await _run(refresh_cdn_cache, **payload), message="CDN 刷新任务已提交")


@bp.post("/preload")
@login_required
async def preload(request: Request):
    _ensure_admin(request)
    payload = _payload(request, ("urls",))
    return success(await _run(preload_cdn_cache, **payload), message="CDN 预热任务已提交")


@bp.get("/tasks")
@login_required
async def tasks(request: Request):
    _ensure_admin(request)
    arguments = {}
    for name, default, maximum in (("page", "1", 100000), ("size", "20", 50)):
        value = request.args.get(name, default)
        if (not isinstance(value, str) or not value.isascii() or not value.isdecimal()
                or len(value) > 6 or not 1 <= int(value) <= maximum):
            raise ValidationError(f"{name} 必须为 1 至 {maximum}")
        arguments[name] = int(value)
    arguments["task_id"] = request.args.get("task_id", "")
    return success(await _run(list_cdn_tasks, **arguments))
