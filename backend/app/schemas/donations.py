"""打赏设置完整表单校验；只解析 URL，不访问远端资源。"""
import unicodedata
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter
from pydantic import field_validator, model_validator


_HTTP_URL = TypeAdapter(AnyHttpUrl)


class DonationSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(strict=True)
    wechat_qr_url: str = Field(strict=True, max_length=2048)
    alipay_qr_url: str = Field(strict=True, max_length=2048)

    @field_validator("wechat_qr_url", "alipay_qr_url", mode="before")
    @classmethod
    def validate_qr_url(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            return value
        if "\\" in value or "#" in value or any(
            char.isspace() or unicodedata.category(char) in {"Cc", "Cf"} for char in value
        ):
            raise ValueError("QR code URL contains whitespace, control characters or a fragment")
        try:
            parsed = urlsplit(value)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                raise ValueError("QR code URL must be a complete HTTP or HTTPS URL")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("QR code URL must not contain credentials")
            # Validate hostname and port syntax without changing the saved URL/query.
            _HTTP_URL.validate_python(value)
        except ValueError as exc:
            raise ValueError("QR code URL must be a valid HTTP or HTTPS URL without credentials") from exc
        return value

    @model_validator(mode="after")
    def require_code_when_enabled(self):
        if self.enabled and not (self.wechat_qr_url or self.alipay_qr_url):
            raise ValueError("at least one QR code URL is required when donations are enabled")
        return self
