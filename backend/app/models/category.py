"""分类模型。"""
from tortoise import fields

from app.models.base import TimestampMixin


class Category(TimestampMixin):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=64, unique=True, description="分类名称")
    slug = fields.CharField(max_length=64, unique=True, description="URL Slug")
    description = fields.CharField(max_length=255, default="", description="分类描述")
    weight = fields.IntField(default=0, description="排序权重，越大越靠前")

    class Meta:
        table = "categories"
        table_description = "文章分类"
        ordering = ["-weight", "id"]

    def __str__(self) -> str:
        return f"<Category {self.id} {self.name}>"
