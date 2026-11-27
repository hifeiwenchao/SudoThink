"""“关于我”编辑输入。"""
import unicodedata
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, TypeAdapter, field_validator

_HTTP_URL = TypeAdapter(AnyHttpUrl)


class AboutIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str
    github_url: str = Field(default="", max_length=512)
    email: EmailStr | Literal[""] = Field(default="", max_length=254)
    x_url: str = Field(default="", max_length=512)
    facebook_url: str = Field(default="", max_length=512)
    instagram_url: str = Field(default="", max_length=512)

    @field_validator("email", mode="before")
    @classmethod
    def strip_email(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("github_url", "x_url", "facebook_url", "instagram_url", mode="before")
    @classmethod
    def validate_contact_url(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value:
            return value
        if "\\" in value or any(
            char.isspace() or unicodedata.category(char) in {"Cc", "Cf"} for char in value
        ):
            raise ValueError("contact URL contains whitespace or control characters")
        try:
            parsed = urlsplit(value)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                raise ValueError("contact URL must be a complete HTTP or HTTPS URL")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("contact URL must not contain credentials")
            _HTTP_URL.validate_python(value)
        except ValueError as exc:
            raise ValueError("contact URL must be a valid HTTP or HTTPS URL without credentials") from exc
        return value

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value
