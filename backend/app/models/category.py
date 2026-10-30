"""分类模型。"""
from tortoise import fields

from app.models.base import TimestampMixin


class Category(TimestampMixin):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=64, unique=True, description="分类名称")
    slug = fields.CharField(max_length=64, unique=True, description="URL Slug")
    description = fields.CharField(max_length=255, default="", description="分类描述")

    class Meta:
        table = "categories"
        table_description = "文章分类"

    def __str__(self) -> str:
        return f"<Category {self.id} {self.name}>"
