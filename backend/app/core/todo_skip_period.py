"""Move recurring reminders beyond the current local calendar period."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.todo_cron import next_cron_at
from app.core.todo_recurrence import next_reminder_at
from app.models.todo import Todo


def skip_period_schedule(todo: Todo, period: str, *, now: datetime) -> tuple[datetime, datetime]:
    """Return the next period boundary and first retained reminder at or after it.

    The current instant owns the period, so repeated requests do not skip an
    additional period. An already postponed reminder always keeps its later time.
    """
    if not todo.reminder_enabled or todo.is_completed or todo.reminder_repeat == "once":
        raise ValueError("仅开启提醒且未完成的重复待办可以跳过本周期")
    try:
        zone = ZoneInfo(todo.reminder_timezone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError("提醒时区必须为有效的 IANA 时区") from None
    local = now.astimezone(zone)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0, fold=0)
    if period == "day":
        boundary = midnight + timedelta(days=1)
    elif period == "week":
        boundary = midnight + timedelta(days=7 - midnight.weekday())
    elif period == "month":
        boundary = midnight.replace(year=local.year + 1, month=1, day=1) if local.month == 12 else (
            midnight.replace(month=local.month + 1, day=1)
        )
    elif period == "year":
        boundary = midnight.replace(year=local.year + 1, month=1, day=1)
    else:
        raise ValueError("跳过周期必须为 day、week、month 或 year")
    # Some zones move clocks at midnight. Resolve a missing local midnight to
    # the first real instant of that date, and choose fold=0 for repeated ones.
    boundary = boundary.astimezone(timezone.utc).astimezone(zone)
    cutoff = boundary.astimezone(timezone.utc) - timedelta(microseconds=1)
    if todo.reminder_repeat == "cron":
        next_run = next_cron_at(todo.reminder_cron, todo.reminder_timezone, after=cutoff)
    else:
        next_run = next_reminder_at(todo.due_at, todo.reminder_repeat, todo.reminder_timezone, after=cutoff)
    if next_run is None:
        raise ValueError("提醒规则没有可计算的未来执行时间")
    if (todo.reminder_next_run_at is not None
            and todo.reminder_next_run_at.astimezone(timezone.utc) > next_run.astimezone(timezone.utc)):
        next_run = todo.reminder_next_run_at
    return boundary, next_run
