"""Administrator-only credentials for direct browser uploads to OSS."""
from sanic import Blueprint, Request
from sanic.exceptions import BadRequest

from app.core.config import settings
from app.core.exceptions import APIError, ForbiddenError, ValidationError
from app.core.oss import create_media_upload_policy, get_upload_configuration
from app.core.response import success
from app.middlewares.auth import login_required

bp = Blueprint("admin_uploads", url_prefix="/uploads")


@bp.get("/config")
@login_required
async def get_upload_config(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    return success(get_upload_configuration(settings))


@bp.post("/policy")
@login_required
async def create_upload_policy(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    if not get_upload_configuration(settings)["enabled"]:
        raise APIError("上传服务尚未配置或配置无效", code=10503, status=503)
    content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise ValidationError("request body must be JSON")
    try:
        payload = request.json
    except BadRequest:
        raise ValidationError("invalid JSON request body") from None
    if not isinstance(payload, dict) or set(payload) != {"filename", "size", "content_type"}:
        raise ValidationError("expected filename, size and content_type")
    try:
        result = create_media_upload_policy(**payload, config=settings)
    except ValueError as exc:
        raise ValidationError(str(exc)) from None
    return success(result)
