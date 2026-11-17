"""Calendar reminders anchored to the original local date and clock time."""
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def next_reminder_at(anchor: datetime, repeat: str, zone_name: str, *, after: datetime) -> datetime | None:
    """Return the first occurrence strictly after ``after``, skipping missed periods.

    Short months clamp to their final day without changing the original anchor.
    DST gaps move forward by the clock gap; repeated local times use the first
    occurrence. UTC comparisons prevent a second send during a repeated hour.
    """
    if repeat == "once":
        return None
    if repeat not in {"daily", "monthly", "yearly"}:
        raise ValueError("Unknown reminder repetition")
    zone = ZoneInfo(zone_name)
    local = anchor.astimezone(zone)
    cutoff = after.astimezone(timezone.utc)
    cutoff_local = cutoff.astimezone(zone)
    if repeat == "daily":
        period = max(0, (cutoff_local.date() - local.date()).days)
    elif repeat == "monthly":
        period = max(0, (cutoff_local.year - local.year) * 12 + cutoff_local.month - local.month)
    else:
        period = max(0, cutoff_local.year - local.year)
    while True:
        try:
            if period == 0:
                candidate = local
            elif repeat == "daily":
                candidate = local + timedelta(days=period)
            else:
                if repeat == "monthly":
                    year, month = divmod(local.year * 12 + local.month - 1 + period, 12)
                    month += 1
                else:
                    year, month = local.year + period, local.month
                candidate = local.replace(year=year, month=month, day=min(local.day, monthrange(year, month)[1]))
            if period:
                candidate = candidate.replace(fold=0)
                candidate = candidate.astimezone(timezone.utc).astimezone(zone)
        except (ValueError, OverflowError):
            # datetime's upper bound has no representable future occurrence.
            return None
        if candidate.astimezone(timezone.utc) > cutoff:
            return candidate
        period += 1
