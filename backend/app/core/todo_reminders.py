"""Database-backed single reminders, with conditional claims and restart recovery."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tortoise.expressions import Q

from app.core.config import settings
from app.core.mail import MailDeliveryError, send_mail, smtp_ready, validate_recipient
from app.models.todo import Todo


logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
CLAIM_SECONDS = 300
SCAN_LIMIT = 20


def _ready(now: datetime) -> Q:
    return Q(
        Q(reminder_status="pending", reminder_next_attempt_at__lte=now)
        | Q(reminder_status="sending", reminder_claim_until__lte=now),
        is_completed=False, reminder_enabled=True, due_at__lte=now,
    ) & ~Q(reminder_email="")


async def claim_reminder(todo_id: int, *, now: datetime | None = None) -> tuple[int, str] | None:
    """Atomically claim one eligible reminder; an expired worker lease can be reclaimed."""
    now = now or datetime.now(timezone.utc)
    todo = await Todo.filter(_ready(now), id=todo_id).first()
    if todo is None:
        return None
    if todo.reminder_attempts >= MAX_ATTEMPTS:
        # The final attempt may have died without saving an outcome.
        await Todo.filter(_ready(now), id=todo_id, reminder_revision=todo.reminder_revision).update(
            reminder_status="failed", reminder_next_attempt_at=None,
            reminder_claim_token="", reminder_claim_until=None,
            reminder_error="提醒发送中断，请手动重试", updated_at=now,
        )
        return None
    token = uuid4().hex
    updated = await Todo.filter(
        _ready(now), id=todo.id, reminder_revision=todo.reminder_revision,
        reminder_attempts=todo.reminder_attempts,
    ).update(
        reminder_status="sending", reminder_claim_token=token,
        reminder_claim_until=now + timedelta(seconds=CLAIM_SECONDS),
        reminder_attempts=todo.reminder_attempts + 1, updated_at=now,
    )
    return (todo.reminder_revision, token) if updated else None


def _message(todo: Todo, config) -> tuple[str, str]:
    try:
        display_zone = ZoneInfo(config.CELERY_TIMEZONE)
    except (ZoneInfoNotFoundError, AttributeError):
        display_zone = ZoneInfo("Asia/Shanghai")
    title = " ".join(todo.title.splitlines())
    due = todo.due_at.astimezone(display_zone).strftime("%Y-%m-%d %H:%M %Z")
    return (
        f"[SudoThink] 待办提醒：{title}",
        f"你的待办事项已到期。\n\n事项：{title}\n到期时间：{due}\n\n"
        f"{todo.content or '（无补充说明）'}\n\n请在管理后台查看或标记完成。\n",
    )


async def deliver_reminder(
    todo_id: int, revision: int, token: str, *, now: datetime | None = None, config=None,
) -> str:
    """Recheck the claim before SMTP and never overwrite a newer edit with an old result."""
    config = config or settings
    now = now or datetime.now(timezone.utc)
    claim = dict(
        id=todo_id, reminder_revision=revision,
        reminder_claim_token=token, reminder_status="sending",
    )
    todo = await Todo.filter(
        **claim, is_completed=False, reminder_enabled=True,
        due_at__lte=now, reminder_claim_until__gt=now,
    ).prefetch_related("owner").first()
    if todo is None:
        return "skipped"
    if not todo.owner.is_admin or not todo.owner.is_active:
        await Todo.filter(**claim).update(
            reminder_status="disabled", reminder_enabled=False,
            reminder_claim_token="", reminder_claim_until=None,
            reminder_next_attempt_at=None, updated_at=now,
        )
        return "skipped"
    try:
        recipient = validate_recipient(todo.reminder_email)
        subject, body = _message(todo, config)
        await asyncio.to_thread(send_mail, subject, body, recipient, config=config)
    except Exception as exc:
        # Neither SMTP raw responses nor arbitrary exceptions belong in user-visible records.
        error = str(exc) if isinstance(exc, MailDeliveryError) else "邮件发送失败，请检查邮件服务或稍后重试"
        retry = todo.reminder_attempts < MAX_ATTEMPTS
        delay = 60 if todo.reminder_attempts == 1 else 300
        changed = await Todo.filter(**claim).update(
            reminder_status="pending" if retry else "failed",
            reminder_error=error[:255], reminder_claim_token="", reminder_claim_until=None,
            reminder_next_attempt_at=now + timedelta(seconds=delay) if retry else None,
            updated_at=now,
        )
        if changed:
            logger.warning("Todo reminder %s delivery failed (attempt %s)", todo_id, todo.reminder_attempts)
        return "failed" if changed else "skipped"
    changed = await Todo.filter(**claim).update(
        reminder_status="sent", reminder_sent_at=now, reminder_error="",
        reminder_claim_token="", reminder_claim_until=None,
        reminder_next_attempt_at=None, updated_at=now,
    )
    return "sent" if changed else "skipped"


async def process_due_reminders(*, now: datetime | None = None, config=None) -> dict:
    """Process a bounded batch. No SMTP configuration means no attempts are consumed."""
    config = config or settings
    outcome = {"sent": 0, "failed": 0, "skipped": 0, "email_configured": smtp_ready(config)}
    if not outcome["email_configured"]:
        return outcome
    scan_time = now or datetime.now(timezone.utc)
    ids = await Todo.filter(
        _ready(scan_time), owner__is_admin=True, owner__is_active=True,
    ).order_by("reminder_next_attempt_at", "id").limit(SCAN_LIMIT).values_list("id", flat=True)
    for todo_id in ids:
        current = now or datetime.now(timezone.utc)
        claimed = await claim_reminder(todo_id, now=current)
        if claimed is None:
            outcome["skipped"] += 1
            continue
        revision, token = claimed
        result = await deliver_reminder(todo_id, revision, token, now=current, config=config)
        outcome[result] += 1
    return outcome
