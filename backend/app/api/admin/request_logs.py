"""管理后台 API 请求记录查询。"""
from sanic import Blueprint, Request

from app.core.exceptions import ForbiddenError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.api_request_log import ApiRequestLog

bp = Blueprint("admin_request_logs", url_prefix="/operations")
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"}


def _argument(arguments, name, default):
    value = arguments.get(name, default)
    if hasattr(arguments, "getlist") and name in arguments and len(arguments.getlist(name)) != 1:
        raise ValidationError(f"{name} 不允许重复")
    if not isinstance(value, str):
        raise ValidationError(f"{name} 必须为字符串")
    return value


def _integer(arguments, name, default, minimum, maximum):
    value = _argument(arguments, name, default)
    if (not value.isascii() or not value.isdecimal() or len(value) > 10
            or not minimum <= int(value) <= maximum):
        raise ValidationError(f"{name} 必须为 {minimum} 至 {maximum} 的整数")
    return int(value)


def _record_dict(record):
    return {
        "id": record.id, "method": record.method, "url": record.url, "path": record.path,
        "query_params": record.query_params, "path_params": record.path_params,
        "body_params": record.body_params, "status_code": record.status_code,
        "duration_ms": record.duration_ms, "created_at": record.created_at.isoformat(),
    }


@bp.get("/requests")
@login_required
async def list_request_logs(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    # Sanic's args property drops blank values, which would treat invalid
    # method=/status_code= filters as absent instead of rejecting them.
    arguments = request.get_args(keep_blank_values=True)
    page = _integer(arguments, "page", "1", 1, 2147483647)
    size = _integer(arguments, "size", "20", 1, 100)
    url = _argument(arguments, "url", "")
    if len(url) > 2048:
        raise ValidationError("URL 最多 2048 个字符")
    qs = ApiRequestLog.all()
    if url:
        qs = qs.filter(url__contains=url)
    if "method" in arguments:
        method = _argument(arguments, "method", "")
        if method not in METHODS:
            raise ValidationError("HTTP 方法无效")
        qs = qs.filter(method=method)
    if "status_code" in arguments:
        qs = qs.filter(status_code=_integer(arguments, "status_code", "", 100, 599))
    total = await qs.count()
    records = await qs.order_by("-created_at", "-id").offset((page - 1) * size).limit(size)
    return success({"items": [_record_dict(record) for record in records],
                    "total": total, "page": page, "size": size})
