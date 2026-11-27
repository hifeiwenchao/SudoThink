"""公开站点“关于我”页面。"""
from sanic import Blueprint, Request

from app.core.response import success
from app.models.about import AboutPage
from app.models.article import Article
from app.api.article import recommendation_dict, RECOMMENDATION_FIELDS
from app.schemas.about import CurrentProjectIn
from pydantic import ValidationError

bp = Blueprint("about", url_prefix="/about")

CONTACT_FIELDS = ("github_url", "email", "x_url", "facebook_url", "instagram_url")


def _about_dict(page: AboutPage | None, *, include_settings: bool = True) -> dict:
    settings = {
        "featured_article_ids": (page.featured_article_ids or []) if page else [],
        "current_projects": (page.current_projects or []) if page else [],
    } if include_settings else {}
    if page is None:
        return {"id": 1, "title": "关于我", "content": "", "updated_at": None,
                **settings, **dict.fromkeys(CONTACT_FIELDS, "")}
    return {
        "id": page.id,
        "title": page.title,
        "content": page.content,
        **settings,
        **{name: getattr(page, name) for name in CONTACT_FIELDS},
        "updated_at": page.updated_at.isoformat(),
    }


async def read_about(*, include_settings: bool = True) -> dict:
    return _about_dict(await AboutPage.get_or_none(id=1), include_settings=include_settings)


@bp.get("")
async def get_about(request: Request):
    return success(await read_about(include_settings=False))


@bp.get("/contacts")
async def get_about_contacts(request: Request):
    """Read only public contact columns for the shared site footer."""
    pages = await AboutPage.filter(id=1).limit(1).values(*CONTACT_FIELDS)
    return success(pages[0] if pages else dict.fromkeys(CONTACT_FIELDS, ""))


@bp.get("/sidebar")
async def get_about_sidebar(request: Request):
    pages = await AboutPage.filter(id=1).limit(1).values("featured_article_ids", "current_projects")
    settings = pages[0] if pages else {}
    ids = settings.get("featured_article_ids") or []
    articles = await Article.filter(id__in=ids, is_published=True, deleted_at__isnull=True).only(
        *RECOMMENDATION_FIELDS
    ).prefetch_related("category") if ids else []
    by_id = {item.id: recommendation_dict(item) for item in articles}
    projects = []
    # Validate persisted legacy/manual data too: public links must stay credential-free.
    for item in (settings.get("current_projects") or [])[:3]:
        try:
            projects.append(CurrentProjectIn.model_validate(item).model_dump())
        except ValidationError:
            continue
    return success({"featured_articles": [by_id[aid] for aid in ids[:5] if aid in by_id],
                    "current_projects": projects})
