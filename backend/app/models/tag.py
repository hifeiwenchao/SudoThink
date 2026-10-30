"""标签模型。"""
from tortoise import fields

from app.models.base import TimestampMixin


class Tag(TimestampMixin):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=64, unique=True, description="标签名称")
    slug = fields.CharField(max_length=64, unique=True, description="URL Slug")

    class Meta:
        table = "tags"
        table_description = "文章标签"

    def __str__(self) -> str:
        return f"<Tag {self.id} {self.name}>"
