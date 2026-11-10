"""公开站点“关于我”页面。"""
from sanic import Blueprint, Request

from app.core.response import success
from app.models.about import AboutPage

bp = Blueprint("about", url_prefix="/about")


def _about_dict(page: AboutPage | None) -> dict:
    if page is None:
        return {"id": 1, "title": "关于我", "content": "", "updated_at": None}
    return {
        "id": page.id,
        "title": page.title,
        "content": page.content,
        "updated_at": page.updated_at.isoformat(),
    }


async def read_about() -> dict:
    return _about_dict(await AboutPage.get_or_none(id=1))


@bp.get("")
async def get_about(request: Request):
    return success(await read_about())
