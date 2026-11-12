"""通用 Schemas。"""
from datetime import datetime
from typing import Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

T = TypeVar("T")

# Unicode Script=Han ranges (Unicode 17), kept in the application so the
# validation rule matches the browser's ``/\p{Script=Han}/u`` check without a
# runtime regex dependency. This includes Han radicals, iteration marks,
# extension planes, and compatibility ideographs (including 𠮷 and 〇).
# Source: https://www.unicode.org/Public/17.0.0/ucd/Scripts.txt
_HAN_RANGES = (
    (0x2E80, 0x2E99), (0x2E9B, 0x2EF3), (0x2F00, 0x2FD5),
    (0x3005, 0x3005), (0x3007, 0x3007),
    (0x3021, 0x3029), (0x3038, 0x303B), (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF), (0xF900, 0xFA6D), (0xFA70, 0xFAD9),
    (0x16FE2, 0x16FE3), (0x16FF0, 0x16FF6), (0x20000, 0x2A6DF),
    (0x2A700, 0x2B81D), (0x2B820, 0x2CEAD), (0x2CEB0, 0x2EBE0),
    (0x2EBF0, 0x2EE5D), (0x2F800, 0x2FA1D), (0x30000, 0x3134A),
    (0x31350, 0x33479),
)


def _is_han(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in _HAN_RANGES)


class PageOut(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int = 1
    size: int = 10


class CommentIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    nickname: str = Field(min_length=1, max_length=32)
    email: EmailStr | Literal[""] = Field(default="", max_length=254)
    content: str = Field(min_length=1, max_length=1000)
    parent_id: Optional[int] = Field(default=None, gt=0)

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, value: str) -> str:
        for character in value:
            if character in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_":
                continue
            if not _is_han(character):
                raise ValueError("昵称只能包含中文、英文字母、数字和下划线")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def trim_email(cls, value):
        return value.strip() if isinstance(value, str) else value


class CommentOut(BaseModel):
    id: int
    content: str
    nickname: str
    location: str
    created_at: datetime
    parent_id: Optional[int] = None
