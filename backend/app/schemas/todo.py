"""待办完整表单与完成状态校验。"""
import unicodedata
from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.mail import MailDeliveryError, validate_recipient


class TodoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(strict=True, min_length=1, max_length=200)
    content: str = Field(strict=True, max_length=10000)
    due_at: AwareDatetime | None
    reminder_enabled: bool = Field(strict=True)
    reminder_email: str = Field(default="", strict=True, max_length=254)

    @field_validator("title", "content", mode="before")
    @classmethod
    def trim_text(cls, value, info):
        if not isinstance(value, str):
            return value
        value = value.strip()
        allowed = {"\r", "\n", "\t"} if info.field_name == "content" else set()
        if any(unicodedata.category(char) in {"Cc", "Cf"} and char not in allowed for char in value):
            raise ValueError("标题或详情不能包含控制字符")
        return value

    @field_validator("due_at", mode="before")
    @classmethod
    def explicit_datetime(cls, value):
        if value is not None and not isinstance(value, (str, datetime)):
            raise ValueError("截止时间必须是带时区的 ISO 时间")
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                raise ValueError("截止时间必须是带时区的 ISO 时间") from None
        return value

    @field_validator("reminder_email", mode="before")
    @classmethod
    def validate_email(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip()
        if any(char in value for char in "\r\n\x00"):
            raise ValueError("提醒邮箱格式不正确")
        if not value:
            return value
        try:
            return validate_recipient(value)
        except (MailDeliveryError, ValueError, TypeError):
            raise ValueError("提醒邮箱格式不正确") from None

    @model_validator(mode="after")
    def reminder_requires_date(self):
        if self.reminder_enabled and self.due_at is None:
            raise ValueError("启用邮件提醒时必须设置截止时间")
        if self.reminder_enabled and not self.reminder_email:
            raise ValueError("启用邮件提醒时必须填写提醒邮箱")
        return self


class TodoCompletionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_completed: bool = Field(strict=True)
