"""通用 Schemas。"""
from datetime import datetime
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageOut(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int = 1
    size: int = 10


class CommentIn(BaseModel):
    content: str = Field(min_length=1, max_length=1000)
    parent_id: Optional[int] = None


class _CommentAuthor(BaseModel):
    id: int
    username: str
    nickname: str = ""
    avatar: str = ""


class CommentOut(BaseModel):
    id: int
    content: str
    is_approved: bool
    created_at: datetime
    parent_id: Optional[int] = None
    author: _CommentAuthor
