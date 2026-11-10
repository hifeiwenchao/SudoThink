"""分类与标签 Schemas。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    slug: Optional[str] = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=255)
    weight: int = Field(default=0, strict=True, ge=0, le=999999)

    @field_validator("name", "slug", mode="before")
    @classmethod
    def strip_identifiers(cls, value):
        return value.strip() if isinstance(value, str) else value


class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str = ""
    weight: int = 0
    created_at: datetime


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=6)
    slug: Optional[str] = Field(default=None, max_length=64)

    @field_validator("name", "slug", mode="before")
    @classmethod
    def strip_identifiers(cls, value):
        return value.strip() if isinstance(value, str) else value


class TagOut(BaseModel):
    id: int
    name: str
    slug: str
    created_at: datetime
