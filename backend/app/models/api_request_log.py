"""API 请求与参数记录。"""
from tortoise import fields, models


class ApiRequestLog(models.Model):
    id = fields.BigIntField(pk=True)
    method = fields.CharField(max_length=16)
    url = fields.CharField(max_length=2048)
    path = fields.CharField(max_length=512)
    query_params = fields.JSONField(default=dict)
    path_params = fields.JSONField(default=dict)
    body_params = fields.JSONField(null=True)
    status_code = fields.IntField()
    duration_ms = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True, index=True)

    class Meta:
        table = "api_request_logs"
        table_description = "API 请求记录"
        ordering = ["-created_at", "-id"]
