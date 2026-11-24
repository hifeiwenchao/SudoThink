"""Fixed seven-day API log retention, using bounded delete batches."""
from datetime import datetime, timedelta, timezone

from tortoise.timezone import get_default_timezone, get_use_tz, make_naive


def database_time(value: datetime) -> datetime:
    """Existing request log timestamps use the configured database wall clock."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("时间须包含时区")
    return value if get_use_tz() else make_naive(value, get_default_timezone())


async def cleanup_request_logs(*, now: datetime | None = None, batch_size: int = 1000) -> dict:
    from app.models.api_request_log import ApiRequestLog

    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("清理批次须为 1 至 1000")
    cutoff = database_time((now or datetime.now(timezone.utc)) - timedelta(days=7))
    deleted = 0
    # Bound a run to 100k rows so a backlog cannot occupy the worker indefinitely.
    for _ in range(100):
        ids = await ApiRequestLog.filter(created_at__lt=cutoff).order_by("created_at", "id").limit(batch_size).values_list("id", flat=True)
        if not ids:
            break
        deleted += await ApiRequestLog.filter(id__in=ids, created_at__lt=cutoff).delete()
        if len(ids) < batch_size:
            break
    return {"deleted": deleted, "retention_days": 7}
