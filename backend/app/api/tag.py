"""标签 API。"""
from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request
from slugify import slugify

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.tag import Tag
from app.schemas.taxonomy import TagIn

bp = Blueprint("tag", url_prefix="/tags")


def _tag_dict(t: Tag) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "created_at": t.created_at.isoformat(),
    }


@bp.get("")
async def list_tags(request: Request):
    items = await Tag.all()
    return success([_tag_dict(t) for t in items])


@bp.post("")
@login_required
async def create_tag(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    try:
        payload = TagIn(**(request.json or {}))
    except PydanticValidationError as e:
        raise ValidationError(str(e))
    slug = payload.slug or slugify(payload.name)
    if await Tag.exists(slug=slug):
        raise ValidationError("tag slug already exists")
    t = await Tag.create(name=payload.name, slug=slug)
    return success(_tag_dict(t), message="created")


@bp.delete("/<tid:int>")
@login_required
async def delete_tag(request: Request, tid: int):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    t = await Tag.get_or_none(id=tid)
    if t is None:
        raise NotFoundError("tag not found")
    await t.delete()
    return success(message="deleted")
