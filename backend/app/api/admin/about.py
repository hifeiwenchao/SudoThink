"""管理后台“关于我”编辑。"""
from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request

from app.api.about import _about_dict, read_about
from app.core.exceptions import ForbiddenError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.about import AboutPage
from app.schemas.about import AboutIn

bp = Blueprint("admin_about", url_prefix="/about")


@bp.get("")
@login_required
async def get_about_admin(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    return success(await read_about())


@bp.put("")
@login_required
async def update_about_admin(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    if not isinstance(request.json, dict):
        raise ValidationError("request body must be an object")
    try:
        payload = AboutIn(**request.json)
    except PydanticValidationError as exc:
        raise ValidationError(str(exc)) from exc
    page, _ = await AboutPage.update_or_create(id=1, defaults=payload.model_dump())
    return success(_about_dict(page), message="updated")
