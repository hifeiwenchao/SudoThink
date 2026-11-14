"""公开站点音乐列表；关闭播放入口时不公开曲目。"""
from sanic import Blueprint, Request

from app.core.response import success
from app.models.music import MusicSettings

bp = Blueprint("music", url_prefix="/music")


def music_settings_dict(settings: MusicSettings | None, *, admin: bool = False) -> dict:
    enabled = bool(settings is not None and settings.enabled)
    tracks = settings.tracks if settings is not None and (admin or enabled) else []
    data = {"enabled": enabled if admin else enabled and bool(tracks), "tracks": tracks}
    if admin:
        data["updated_at"] = settings.updated_at.isoformat() if settings is not None else None
    return data


@bp.get("")
async def get_music(request: Request):
    return success(music_settings_dict(await MusicSettings.get_or_none(id=1)))
