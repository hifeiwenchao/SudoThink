"""分类 API。"""
from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request
from slugify import slugify
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q

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
        "weight": c.weight,
        "created_at": c.created_at.isoformat(),
    }


@bp.get("")
async def list_categories(request: Request):
    items = await Category.all().order_by("-weight", "id")
    return success([_category_dict(c) for c in items])


@bp.post("")
@login_required
async def create_category(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    payload, slug = _category_payload(request)
    await _ensure_unique(payload.name, slug)
    try:
        c = await Category.create(
            name=payload.name, slug=slug, description=payload.description, weight=payload.weight
        )
    except IntegrityError as exc:
        raise ValidationError("category name or slug already exists") from exc
    return success(_category_dict(c), message="created")


def _category_payload(request: Request) -> tuple[CategoryIn, str]:
    if not isinstance(request.json, dict):
        raise ValidationError("request body must be an object")
    try:
        payload = CategoryIn(**request.json)
    except PydanticValidationError as exc:
        raise ValidationError(str(exc)) from exc
    slug = payload.slug or slugify(payload.name, max_length=64) or "category"
    return payload, slug


async def _ensure_unique(name: str, slug: str, exclude_id: int | None = None) -> None:
    existing = Category.filter(Q(name=name) | Q(slug=slug))
    if exclude_id is not None:
        existing = existing.exclude(id=exclude_id)
    if await existing.exists():
        raise ValidationError("category name or slug already exists")


@bp.put("/<cid:int>")
@login_required
async def update_category(request: Request, cid: int):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    c = await Category.get_or_none(id=cid)
    if c is None:
        raise NotFoundError("category not found")
    payload, slug = _category_payload(request)
    await _ensure_unique(payload.name, slug, exclude_id=cid)
    c.name = payload.name
    c.slug = slug
    c.description = payload.description
    c.weight = payload.weight
    try:
        await c.save()
    except IntegrityError as exc:
        raise ValidationError("category name or slug already exists") from exc
    return success(_category_dict(c), message="updated")


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
