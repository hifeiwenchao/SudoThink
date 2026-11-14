"""管理后台音乐完整设置，单次保存原子替换播放列表。"""
from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request
from sanic.exceptions import BadRequest

from app.api.music import music_settings_dict
from app.core.config import settings
from app.core.exceptions import ForbiddenError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.music import MusicSettings
from app.schemas.music import MusicSettingsIn

bp = Blueprint("admin_music", url_prefix="/music")


@bp.get("")
@login_required
async def get_music_admin(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    return success(music_settings_dict(await MusicSettings.get_or_none(id=1), admin=True))


@bp.put("")
@login_required
async def update_music_admin(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    if request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise ValidationError("request body must be JSON")
    try:
        body = request.json
    except BadRequest:
        raise ValidationError("invalid JSON request body") from None
    if not isinstance(body, dict):
        raise ValidationError("request body must be an object")
    try:
        payload = MusicSettingsIn.model_validate(body, context={"config": settings})
    except PydanticValidationError as exc:
        raise ValidationError(str(exc)) from None
    saved, _ = await MusicSettings.update_or_create(id=1, defaults=payload.model_dump())
    return success(music_settings_dict(saved, admin=True), message="updated")
