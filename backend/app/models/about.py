"""站点“关于我”单页。"""
from tortoise import fields, models


class AboutPage(models.Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=120, default="关于我", description="页面标题")
    content = fields.TextField(default="", description="富文本 HTML 正文")
    github_url = fields.CharField(max_length=512, default="", description="GitHub 主页")
    email = fields.CharField(max_length=254, default="", description="公开联系邮箱")
    x_url = fields.CharField(max_length=512, default="", description="X 主页")
    facebook_url = fields.CharField(max_length=512, default="", description="Facebook 主页")
    instagram_url = fields.CharField(max_length=512, default="", description="Instagram 主页")
    featured_article_ids = fields.JSONField(default=list, description="精选文章 ID，按展示顺序")
    current_projects = fields.JSONField(default=list, description="正在折腾的项目动态")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "about_pages"
        table_description = "关于我页面，使用固定 ID 1"
