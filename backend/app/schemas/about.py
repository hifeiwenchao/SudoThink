"""“关于我”编辑输入。"""
from pydantic import BaseModel, Field, field_validator


class AboutIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value
