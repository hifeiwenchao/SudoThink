"""公开站点打赏设置。"""
from sanic import Blueprint, Request

from app.core.response import success
from app.models.donations import DonationSettings

bp = Blueprint("donations", url_prefix="/donations")


def donation_settings_dict(settings: DonationSettings | None, *, admin: bool = False) -> dict:
    enabled = settings.enabled if settings is not None else False
    show_urls = settings is not None and (admin or enabled)
    data = {
        "enabled": enabled,
        "wechat_qr_url": settings.wechat_qr_url if show_urls else "",
        "alipay_qr_url": settings.alipay_qr_url if show_urls else "",
    }
    if admin:
        data["updated_at"] = settings.updated_at.isoformat() if settings is not None else None
    return data


@bp.get("")
async def get_donations(request: Request):
    return success(donation_settings_dict(await DonationSettings.get_or_none(id=1)))
