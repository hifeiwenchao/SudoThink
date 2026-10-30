"""文章模型。"""
from tortoise import fields

from app.models.base import TimestampMixin


class Article(TimestampMixin):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255, description="标题")
    slug = fields.CharField(max_length=255, unique=True, description="URL Slug")
    summary = fields.CharField(max_length=512, default="", description="摘要")
    content = fields.TextField(description="正文 (Markdown)")
    cover = fields.CharField(max_length=512, default="", description="封面图")
    is_published = fields.BooleanField(default=False, description="是否发布")
    view_count = fields.IntField(default=0, description="阅读量")
    published_at = fields.DatetimeField(null=True, description="发布时间")

    author = fields.ForeignKeyField(
        "models.User", related_name="articles", on_delete=fields.CASCADE
    )
    category = fields.ForeignKeyField(
        "models.Category",
        related_name="articles",
        null=True,
        on_delete=fields.SET_NULL,
    )
    tags = fields.ManyToManyField(
        "models.Tag", related_name="articles", through="article_tags"
    )

    class Meta:
        table = "articles"
        table_description = "文章表"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"<Article {self.id} {self.title}>"
