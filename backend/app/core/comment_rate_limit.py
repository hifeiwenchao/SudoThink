"""Atomic per-IP comment throttling without putting raw IPs in Redis keys."""
import hashlib
import secrets
import time

from redis.exceptions import RedisError

from app.core.exceptions import APIError
from app.core.redis import get_redis

# One sorted set records the accepted submissions in the rolling ten-minute window.
# The check and insertion share one Lua invocation so concurrent workers cannot race.
_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local cooldown = tonumber(ARGV[2])
local window = tonumber(ARGV[3])
local maximum = tonumber(ARGV[4])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local latest = redis.call('ZREVRANGE', key, 0, 0, 'WITHSCORES')
if #latest > 0 and now - tonumber(latest[2]) < cooldown then
    return math.ceil((tonumber(latest[2]) + cooldown - now) / 1000)
end
if redis.call('ZCARD', key) >= maximum then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    return math.ceil((tonumber(oldest[2]) + window - now) / 1000)
end
redis.call('ZADD', key, now, ARGV[5])
redis.call('PEXPIRE', key, window)
return 0
"""


async def enforce_comment_rate_limit(ip_address: str) -> None:
    """Allow a comment every 30 seconds and at most five in ten minutes."""
    try:
        redis = get_redis()
    except RuntimeError:
        # Unit tests and startup without Redis have no shared limiter available.
        return

    key = "comment:rate:" + hashlib.sha256(ip_address.encode("utf-8")).hexdigest()
    try:
        retry_after = await redis.eval(
            _RATE_LIMIT_SCRIPT, 1, key, int(time.time() * 1000), 30000, 600000, 5,
            secrets.token_hex(16),
        )
    except RedisError:
        # A cache outage must not discard otherwise valid comments.
        return
    if retry_after:
        raise APIError(
            f"评论提交过于频繁，请在 {int(retry_after)} 秒后重试", code=10429, status=429
        )
