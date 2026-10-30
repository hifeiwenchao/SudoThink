"""模型基类。"""
from tortoise import fields, models


class TimestampMixin(models.Model):
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        abstract = True
