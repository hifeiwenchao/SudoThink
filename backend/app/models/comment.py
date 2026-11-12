"""评论模型。"""
from tortoise import fields

from app.models.base import TimestampMixin


class Comment(TimestampMixin):
    id = fields.IntField(pk=True)
    content = fields.CharField(max_length=1000, description="评论内容")
    is_approved = fields.BooleanField(default=False, description="是否审核通过")
    is_rejected = fields.BooleanField(default=False, description="是否已驳回")
    nickname = fields.CharField(max_length=32, default="", description="访客昵称")
    email = fields.CharField(max_length=254, default="", description="访客邮箱，仅供管理")
    ip_address = fields.CharField(max_length=45, default="", description="服务端记录的评论 IP")
    user_agent = fields.CharField(max_length=1024, default="", description="评论请求 User-Agent，仅供管理")
    location = fields.CharField(max_length=256, default="", description="评论 IP 归属地")

    article = fields.ForeignKeyField(
        "models.Article", related_name="comments", on_delete=fields.CASCADE
    )
    author = fields.ForeignKeyField(
        "models.User", related_name="comments", null=True, on_delete=fields.SET_NULL
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
