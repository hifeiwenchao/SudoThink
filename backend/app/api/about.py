"""公开站点“关于我”页面。"""
from sanic import Blueprint, Request

from app.core.response import success
from app.models.about import AboutPage

bp = Blueprint("about", url_prefix="/about")

CONTACT_FIELDS = ("github_url", "email", "x_url", "facebook_url", "instagram_url")


def _about_dict(page: AboutPage | None) -> dict:
    if page is None:
        return {"id": 1, "title": "关于我", "content": "", "updated_at": None, **dict.fromkeys(CONTACT_FIELDS, "")}
    return {
        "id": page.id,
        "title": page.title,
        "content": page.content,
        **{name: getattr(page, name) for name in CONTACT_FIELDS},
        "updated_at": page.updated_at.isoformat(),
    }


async def read_about() -> dict:
    return _about_dict(await AboutPage.get_or_none(id=1))


@bp.get("")
async def get_about(request: Request):
    return success(await read_about())
