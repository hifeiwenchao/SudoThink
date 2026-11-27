"""文章 Schemas。"""
from datetime import datetime
import unicodedata
from typing import List, Optional
from urllib.parse import urlsplit

from pydantic import AnyHttpUrl, BaseModel, Field, StrictInt, TypeAdapter, field_validator

_HTTP_URL = TypeAdapter(AnyHttpUrl)


class _ArticleInput(BaseModel):
    @field_validator("title", "summary", "content", "cover", mode="before", check_fields=False)
    @classmethod
    def reject_null_text(cls, value):
        if value is None:
            raise ValueError("article text fields must not be null")
        return value

    @field_validator("title", mode="before", check_fields=False)
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("cover", mode="before", check_fields=False)
    @classmethod
    def validate_cover(cls, value):
        if not isinstance(value, str):
            return value
        if "\\" in value or any(unicodedata.category(char) in {"Cc", "Cf"} for char in value):
            raise ValueError("cover URL contains control characters or backslashes")
        value = value.strip()
        if not value:
            return value
        if any(char.isspace() for char in value):
            raise ValueError("cover URL contains whitespace")
        try:
            parsed = urlsplit(value)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
                raise ValueError("cover URL must be complete")
            if parsed.username is not None or parsed.password is not None:
                raise ValueError("cover URL must not contain credentials")
            _HTTP_URL.validate_python(value)
        except ValueError as exc:
            raise ValueError("cover must be a valid HTTP or HTTPS URL without credentials") from exc
        return value


class ArticleCreateIn(_ArticleInput):
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(default="", max_length=512)
    content: str
    cover: str = Field(default="", max_length=512)
    is_published: bool = False
    category_id: Optional[StrictInt] = None
    tag_ids: List[StrictInt] = Field(default_factory=list)


class ArticleUpdateIn(_ArticleInput):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    summary: Optional[str] = Field(default=None, max_length=512)
    content: Optional[str] = None
    cover: Optional[str] = Field(default=None, max_length=512)
    is_published: Optional[bool] = None
    category_id: Optional[StrictInt] = None
    tag_ids: Optional[List[StrictInt]] = None


class _AuthorBrief(BaseModel):
    id: int
    username: str
    nickname: str = ""
    avatar: str = ""


class _CategoryBrief(BaseModel):
    id: int
    name: str
    slug: str


class _TagBrief(BaseModel):
    id: int
    name: str
    slug: str


class ArticleOut(BaseModel):
    id: int
    title: str
    slug: str
    summary: str = ""
    content: str
    cover: str = ""
    is_published: bool
    view_count: int
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    author: _AuthorBrief
    category: Optional[_CategoryBrief] = None
    tags: List[_TagBrief] = []
