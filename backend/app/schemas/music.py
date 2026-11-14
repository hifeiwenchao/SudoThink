"""音乐完整表单校验，不请求远程音频或读取上传凭据。"""
import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.core.config import settings
from app.core.oss import normalize_prefix, validate_https_url


class MusicTrackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(strict=True, min_length=1, max_length=120)
    artist: str = Field(default="", strict=True, max_length=120)
    url: str = Field(strict=True, min_length=1, max_length=2048)

    @field_validator("title", "artist", mode="before")
    @classmethod
    def trim_text(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
            raise ValueError("曲名和歌手不能包含控制字符")
        return value

    @field_validator("url", mode="before")
    @classmethod
    def validate_audio_url(cls, value, info: ValidationInfo):
        if not isinstance(value, str):
            return value
        value = value.strip()
        config = (info.context or {}).get("config", settings)
        try:
            # Only objects created by this application's audio uploader are accepted.
            # No OSS secret or network call is needed to validate a saved playlist.
            base = validate_https_url(config.CDN_BASE_URL)
            prefix = normalize_prefix(config.OSS_MEDIA_PREFIX)
            expected = f"{base}/{prefix}/audios/"
            if not value.startswith(expected) or not re.fullmatch(
                r"[0-9]{4}/(?:0[1-9]|1[0-2])/[0-9a-f]{32}\.(?:mp3|m4a|wav|ogg)",
                value[len(expected):],
            ):
                raise ValueError("invalid audio URL")
        except (AttributeError, ValueError):
            raise ValueError("音频地址必须是本站上传的音频 CDN 地址") from None
        return value


class MusicSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(strict=True)
    tracks: list[MusicTrackIn] = Field(strict=True, max_length=100)

    @field_validator("tracks")
    @classmethod
    def unique_tracks(cls, tracks):
        urls = [track.url for track in tracks]
        if len(urls) != len(set(urls)):
            raise ValueError("播放列表不能包含重复音频")
        return tracks
