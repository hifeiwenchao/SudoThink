"""站点打赏设置。"""
from tortoise import fields, models


class DonationSettings(models.Model):
    id = fields.IntField(pk=True)
    enabled = fields.BooleanField(default=False, description="是否启用打赏")
    wechat_qr_url = fields.CharField(max_length=2048, default="", description="微信收款码 URL")
    alipay_qr_url = fields.CharField(max_length=2048, default="", description="支付宝收款码 URL")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "donation_settings"
        table_description = "站点打赏设置，使用固定 ID 1"
