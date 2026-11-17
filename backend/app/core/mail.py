"""SMTP mail transport shared by background notifications."""
from __future__ import annotations

import smtplib
import ssl
from email.headerregistry import Address
from email.message import EmailMessage

from email_validator import EmailNotValidError, validate_email

from app.core.config import settings


class MailDeliveryError(RuntimeError):
    """Safe, actionable mail error; never includes upstream responses or credentials."""


def _address(value: str) -> str:
    if not isinstance(value, str) or any(char in value for char in "\r\n"):
        raise MailDeliveryError("邮箱地址格式不正确")
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized
    except EmailNotValidError:
        raise MailDeliveryError("邮箱地址格式不正确") from None


def _validate_config(config) -> str:
    host = config.SMTP_HOST.strip()
    if (
        not host or any(char.isspace() or char in "/\\\x00" for char in host)
        or not 1 <= config.SMTP_PORT <= 65535
        or config.SMTP_SECURITY not in {"ssl", "starttls"}
        or not config.SMTP_USERNAME.strip() or not config.SMTP_PASSWORD
        or not 1 <= config.SMTP_TIMEOUT_SECONDS <= 60
        or any(char in config.SMTP_FROM_NAME for char in "\r\n\x00")
    ):
        raise MailDeliveryError("邮件配置不完整或无效，请检查 SMTP 配置")
    return _address(config.SMTP_FROM_EMAIL or config.SMTP_USERNAME)


def smtp_ready(config=None) -> bool:
    """Indicate whether mail can be enabled, without connecting to SMTP."""
    try:
        _validate_config(config or settings)
        return True
    except (MailDeliveryError, AttributeError, TypeError, ValueError):
        return False


def validate_recipient(email: str) -> str:
    """Validate the mailbox explicitly saved for a reminder, with no fallback."""
    return _address(email)


def send_mail(subject: str, body: str, recipient: str, *, config=None) -> None:
    """Send UTF-8 plain text over verified SSL or mandatory STARTTLS."""
    config = config or settings
    sender = _validate_config(config)
    recipient = _address(recipient)
    if any(char in subject for char in "\r\n\x00"):
        raise MailDeliveryError("邮件标题不能包含换行符")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = Address(display_name=config.SMTP_FROM_NAME, addr_spec=sender)
    message["To"] = recipient
    message.set_content(body)
    context = ssl.create_default_context()
    try:
        if config.SMTP_SECURITY == "ssl":
            transport = smtplib.SMTP_SSL(
                config.SMTP_HOST, config.SMTP_PORT,
                timeout=config.SMTP_TIMEOUT_SECONDS, context=context,
            )
        else:
            transport = smtplib.SMTP(
                config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT_SECONDS,
            )
        with transport as client:
            if config.SMTP_SECURITY == "starttls":
                client.ehlo()
                client.starttls(context=context)
                client.ehlo()
            client.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            if client.send_message(message):
                raise MailDeliveryError("邮件服务器拒绝收件地址，请检查收件邮箱")
    except smtplib.SMTPAuthenticationError:
        raise MailDeliveryError("邮箱认证失败，请检查账号或客户端专用密码") from None
    except ssl.SSLError:
        raise MailDeliveryError("SMTP TLS 连接失败，请检查邮件服务器和证书") from None
    except smtplib.SMTPResponseException as exc:
        raise MailDeliveryError(f"邮件服务拒绝发送（SMTP {exc.smtp_code}）") from None
    except (smtplib.SMTPException, OSError):
        raise MailDeliveryError("邮件服务器连接或发送失败，请检查 SMTP 配置和网络") from None
