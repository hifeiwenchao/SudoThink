"""Bounded standard five-field crontab parsing shared by preview and delivery."""
from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, CroniterBadDateError, croniter


_MONTHS = {name: index for index, name in enumerate(
    ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1,
)}
_WEEKDAYS = {name: index for index, name in enumerate(("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"))}
_FIELDS = ((0, 59, 60, {}), (0, 23, 24, {}), (1, 31, 31, {}), (1, 12, 12, _MONTHS), (0, 7, 7, _WEEKDAYS))
_ITEM = re.compile(r"(\*|[0-9]{1,2}|[A-Z]{3})(?:-([0-9]{1,2}|[A-Z]{3}))?(?:/([0-9]{1,2}))?\Z")
_REFERENCE = datetime(2024, 1, 1, tzinfo=timezone.utc)


def normalize_cron(expression: str) -> str:
    """Accept numeric ranges, lists, steps and standard month/weekday names only."""
    if (not isinstance(expression, str) or not 1 <= len(expression) <= 128
            or not expression.isascii() or any(char in expression for char in "\r\n\x00")):
        raise ValueError("Crontab 须为一行且不超过 128 个字符")
    normalized = " ".join(expression.upper().split())
    parts = normalized.split(" ")
    if len(parts) != 5:
        raise ValueError("Crontab 须包含 5 段：分 时 日 月 周，不包含秒或命令")
    for field, (minimum, maximum, max_step, names) in zip(parts, _FIELDS):
        for item in field.split(","):
            match = _ITEM.fullmatch(item)
            if match is None:
                raise ValueError("Crontab 仅支持数字、*、逗号、范围、步长及月份/星期英文缩写")
            start, end, step = match.groups()
            if (start == "*" and end is not None) or (step is not None and not 1 <= int(step) <= max_step):
                raise ValueError("Crontab 范围或步长无效")
            values = []
            for value in (start, end):
                if value is None or value == "*":
                    continue
                number = names.get(value) if value.isalpha() else int(value)
                if number is None or not minimum <= number <= maximum:
                    raise ValueError("Crontab 字段值超出允许范围")
                values.append(number)
            if len(values) == 2 and values[0] > values[1]:
                raise ValueError("Crontab 范围起始值不能大于结束值")
    try:
        # A five-field calendar repeats within eight years, even over 2100's
        # skipped leap year. Bound impossible dates instead of searching forever.
        croniter(normalized, _REFERENCE, day_or=True, max_years_between_matches=8).get_next(datetime)
    except (CroniterBadCronError, CroniterBadDateError, ValueError, OverflowError):
        raise ValueError("Crontab 表达式无效或没有可执行的日期") from None
    return normalized


def cron_occurrences(expression: str, zone_name: str, *, after: datetime, count: int = 5) -> list[datetime]:
    """Find future occurrences, emitting a repeated local clock minute just once."""
    normalized = normalize_cron(expression)
    if type(count) is not int or not 1 <= count <= 10:
        raise ValueError("预览次数须为 1 至 10")
    if not isinstance(after, datetime) or after.tzinfo is None or after.utcoffset() is None:
        raise ValueError("开始时间须包含时区")
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        raise ValueError("提醒时区必须为有效的 IANA 时区") from None
    cutoff = after.astimezone(timezone.utc)
    try:
        schedule = croniter(normalized, cutoff.astimezone(zone), day_or=True, max_years_between_matches=8)
        result = []
        while len(result) < count:
            candidate = schedule.get_next(datetime)
            # During a fall-back hour croniter may return the second occurrence.
            # The first instance owns that local minute, even after a restart.
            if candidate.fold or candidate.astimezone(timezone.utc) <= cutoff:
                continue
            result.append(candidate)
            cutoff = candidate.astimezone(timezone.utc)
    except (CroniterBadCronError, CroniterBadDateError, ValueError, OverflowError):
        raise ValueError("Crontab 在所选时区没有可计算的未来执行时间") from None
    return result


def next_cron_at(expression: str, zone_name: str, *, after: datetime) -> datetime:
    return cron_occurrences(expression, zone_name, after=after, count=1)[0]
