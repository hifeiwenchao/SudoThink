"""站点“关于我”单页。"""
from tortoise import fields, models


class AboutPage(models.Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=120, default="关于我", description="页面标题")
    content = fields.TextField(default="", description="富文本 HTML 正文")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "about_pages"
        table_description = "关于我页面，使用固定 ID 1"
