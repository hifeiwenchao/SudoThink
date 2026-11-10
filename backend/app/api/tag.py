"""标签 API。"""
from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request
from slugify import slugify
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q

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
    items = await Tag.all().order_by("id")
    return success([_tag_dict(t) for t in items])


@bp.post("")
@login_required
async def create_tag(request: Request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    payload, slug = _tag_payload(request)
    await _ensure_unique(payload.name, slug)
    try:
        t = await Tag.create(name=payload.name, slug=slug)
    except IntegrityError as exc:
        raise ValidationError("tag name or slug already exists") from exc
    return success(_tag_dict(t), message="created")


def _tag_payload(request: Request) -> tuple[TagIn, str]:
    if not isinstance(request.json, dict):
        raise ValidationError("request body must be an object")
    try:
        payload = TagIn(**request.json)
    except PydanticValidationError as exc:
        raise ValidationError(str(exc)) from exc
    slug = payload.slug or slugify(payload.name, max_length=64) or "tag"
    return payload, slug


async def _ensure_unique(name: str, slug: str, exclude_id: int | None = None) -> None:
    existing = Tag.filter(Q(name=name) | Q(slug=slug))
    if exclude_id is not None:
        existing = existing.exclude(id=exclude_id)
    if await existing.exists():
        raise ValidationError("tag name or slug already exists")


@bp.put("/<tid:int>")
@login_required
async def update_tag(request: Request, tid: int):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")
    t = await Tag.get_or_none(id=tid)
    if t is None:
        raise NotFoundError("tag not found")
    payload, slug = _tag_payload(request)
    await _ensure_unique(payload.name, slug, exclude_id=tid)
    t.name = payload.name
    t.slug = slug
    try:
        await t.save()
    except IntegrityError as exc:
        raise ValidationError("tag name or slug already exists") from exc
    return success(_tag_dict(t), message="updated")


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
