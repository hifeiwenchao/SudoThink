"""评论模型。"""
from tortoise import fields

from app.models.base import TimestampMixin


class Comment(TimestampMixin):
    id = fields.IntField(pk=True)
    content = fields.CharField(max_length=1000, description="评论内容")
    is_approved = fields.BooleanField(default=False, description="是否审核通过")

    article = fields.ForeignKeyField(
        "models.Article", related_name="comments", on_delete=fields.CASCADE
    )
    author = fields.ForeignKeyField(
        "models.User", related_name="comments", on_delete=fields.CASCADE
    )
    parent = fields.ForeignKeyField(
        "models.Comment",
        related_name="replies",
        null=True,
        on_delete=fields.CASCADE,
    )

    class Meta:
        table = "comments"
        table_description = "评论表"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"<Comment {self.id}>"
