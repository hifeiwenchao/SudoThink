"""管理员私有待办与可恢复的邮件提醒状态。"""
from datetime import datetime

from tortoise import fields
from tortoise.timezone import get_default_timezone, get_use_tz, is_naive, make_aware, make_naive

from app.models.base import TimestampMixin


class TodoDatetimeField(fields.DatetimeField):
    """Keep aware Python instants while using the existing database wall-clock timezone.

    With ``use_tz=False``, Tortoise strips offsets without converting them. Todos
    accept browser UTC timestamps, so normalize the offset before that conversion
    and restore the database timezone when reading. Query values use the same
    conversion as writes; the rest of the application's legacy fields are unchanged.
    """

    def to_python_value(self, value):
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if isinstance(value, datetime) and not is_naive(value):
            value = value.astimezone(get_default_timezone())
        converted = super().to_python_value(value)
        if converted is not None and is_naive(converted):
            return make_aware(converted, get_default_timezone())
        return converted

    def to_db_value(self, value, instance):
        if isinstance(value, datetime):
            value = self.to_python_value(value)
        converted = super().to_db_value(value, instance)
        if isinstance(converted, datetime) and not get_use_tz() and not is_naive(converted):
            return make_naive(converted, get_default_timezone())
        return converted


class Todo(TimestampMixin):
    id = fields.IntField(pk=True)
    created_at = TodoDatetimeField(auto_now_add=True, description="创建时间")
    updated_at = TodoDatetimeField(auto_now=True, description="更新时间")
    owner = fields.ForeignKeyField("models.User", related_name="todos", on_delete=fields.CASCADE)
    title = fields.CharField(max_length=200, description="待办标题")
    content = fields.TextField(default="", description="待办详情")
    due_at = TodoDatetimeField(null=True, db_index=True, description="截止及提醒时间")
    is_completed = fields.BooleanField(default=False, description="是否已完成")
    reminder_enabled = fields.BooleanField(default=False, description="是否启用邮件提醒")
    reminder_email = fields.CharField(max_length=254, default="", description="提醒收件邮箱")
    reminder_repeat = fields.CharField(max_length=16, default="once", description="提醒重复频率")
    reminder_timezone = fields.CharField(max_length=64, default="Asia/Shanghai", description="提醒日历时区")
    reminder_next_run_at = TodoDatetimeField(null=True, description="本次计划提醒时间")
    reminder_status = fields.CharField(max_length=16, default="disabled", description="提醒发送状态")
    reminder_sent_at = TodoDatetimeField(null=True, description="最近一次提醒发送时间")
    reminder_attempts = fields.IntField(default=0, description="本次提醒发送尝试次数")
    reminder_error = fields.CharField(max_length=255, default="", description="脱敏后的提醒错误")
    reminder_next_attempt_at = TodoDatetimeField(null=True, db_index=True, description="下次尝试时间")
    reminder_claim_token = fields.CharField(max_length=32, default="", description="任务领取令牌")
    reminder_claim_until = TodoDatetimeField(null=True, description="任务领取租约到期时间")
    reminder_revision = fields.IntField(default=1, description="提醒版本，修改后令旧任务失效")

    class Meta:
        table = "todos"
        table_description = "管理员私有待办事项"
        indexes = (("is_completed", "reminder_enabled", "reminder_status", "reminder_next_attempt_at"),)
