"""站点音乐播放列表，曲目顺序即 JSON 数组顺序。"""
from tortoise import fields, models


class MusicSettings(models.Model):
    id = fields.IntField(pk=True)
    enabled = fields.BooleanField(default=False, description="是否展示音乐播放器")
    tracks = fields.JSONField(default=list, description="按播放顺序保存的音乐曲目")
    updated_at = fields.DatetimeField(auto_now=True, description="更新时间")

    class Meta:
        table = "music_settings"
        table_description = "站点音乐设置，使用固定 ID 1"
