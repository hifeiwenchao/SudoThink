"""文章 Schemas。"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ArticleCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    summary: str = ""
    content: str
    cover: str = ""
    is_published: bool = False
    category_id: Optional[int] = None
    tag_ids: List[int] = []


class ArticleUpdateIn(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    summary: Optional[str] = None
    content: Optional[str] = None
    cover: Optional[str] = None
    is_published: Optional[bool] = None
    category_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None


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
