"""管理后台打赏设置。"""
from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request

from app.api.donations import donation_settings_dict
from app.core.exceptions import ForbiddenError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.donations import DonationSettings
from app.schemas.donations import DonationSettingsIn

bp = Blueprint("admin_donations", url_prefix="/donations")


@bp.get("")
@login_required
async def get_donations_admin(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    settings = await DonationSettings.get_or_none(id=1)
    return success(donation_settings_dict(settings, admin=True))


@bp.put("")
@login_required
async def update_donations_admin(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    if not isinstance(request.json, dict):
        raise ValidationError("request body must be an object")
    try:
        payload = DonationSettingsIn(**request.json)
    except PydanticValidationError as exc:
        raise ValidationError(str(exc)) from exc
    settings, _ = await DonationSettings.update_or_create(id=1, defaults=payload.model_dump())
    return success(donation_settings_dict(settings, admin=True), message="updated")
