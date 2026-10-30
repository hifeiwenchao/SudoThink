"""用户模型。"""
from tortoise import fields

from app.models.base import TimestampMixin


class User(TimestampMixin):
    id = fields.IntField(pk=True)
    username = fields.CharField(max_length=64, unique=True, description="用户名")
    email = fields.CharField(max_length=128, unique=True, description="邮箱")
    password_hash = fields.CharField(max_length=255, description="密码哈希")
    nickname = fields.CharField(max_length=64, default="", description="昵称")
    avatar = fields.CharField(max_length=255, default="", description="头像 URL")
    bio = fields.CharField(max_length=255, default="", description="个人简介")
    is_active = fields.BooleanField(default=True, description="是否启用")
    is_admin = fields.BooleanField(default=False, description="是否管理员")

    class Meta:
        table = "users"
        table_description = "用户表"

    def __str__(self) -> str:
        return f"<User {self.id} {self.username}>"
