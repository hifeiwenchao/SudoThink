"""分类 API。"""
from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request
from slugify import slugify

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.response import success
from app.middlewares.auth import login_required
from app.models.category import Category
from app.schemas.taxonomy import CategoryIn

bp = Blueprint("category", url_prefix="/categories")


def _category_dict(c: Category) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "slug": c.slug,
        "description": c.description,
        "created_at": c.created_at.isoformat(),
    }


@bp.get("")
async def list_categories(request: Request):
    items = await Category.all()
    return success([_category_dict(c) for c in items])


@bp.post("")
@login_required
async def create_category(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    try:
        payload = CategoryIn(**(request.json or {}))
    except PydanticValidationError as e:
        raise ValidationError(str(e))
    slug = payload.slug or slugify(payload.name)
    if await Category.exists(slug=slug):
        raise ValidationError("category slug already exists")
    c = await Category.create(name=payload.name, slug=slug, description=payload.description)
    return success(_category_dict(c), message="created")


@bp.delete("/<cid:int>")
@login_required
async def delete_category(request: Request, cid: int):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    c = await Category.get_or_none(id=cid)
    if c is None:
        raise NotFoundError("category not found")
    await c.delete()
    return success(message="deleted")
