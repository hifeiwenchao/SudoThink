"""分类与标签 Schemas。"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    slug: Optional[str] = None
    description: str = ""


class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str = ""
    created_at: datetime


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    slug: Optional[str] = None


class TagOut(BaseModel):
    id: int
    name: str
    slug: str
    created_at: datetime
