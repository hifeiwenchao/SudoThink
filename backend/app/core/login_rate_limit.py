"""Shared, atomic login reservations. Redis keys contain only hashed identifiers."""
import asyncio
import hashlib
import unicodedata

from app.core.comment_context import get_comment_ip
from app.core.redis import get_redis

WINDOW_SECONDS = 900
ACCOUNT_MAXIMUM = 5
IP_MAXIMUM = 30
REDIS_TIMEOUT_SECONDS = 2.5

# Reserve before checking credentials: concurrent requests cannot all observe
# the same remaining slot. IP attempts include requests blocked by the account.
# Windows start with the first attempt and are never extended by blocked calls.
RESERVE_SCRIPT = """
local window = tonumber(ARGV[1])
local account_maximum = tonumber(ARGV[2])
local ip_maximum = tonumber(ARGV[3])
local ip_count = tonumber(redis.call('GET', KEYS[2]) or '0')
if ip_count >= ip_maximum then
    return math.max(1, redis.call('TTL', KEYS[2]))
end
local ip_new = redis.call('INCR', KEYS[2])
if ip_new == 1 then redis.call('EXPIRE', KEYS[2], window) end
local account_count = tonumber(redis.call('GET', KEYS[1]) or '0')
if account_count >= account_maximum then
    return math.max(1, redis.call('TTL', KEYS[1]))
end
local account_new = redis.call('INCR', KEYS[1])
if account_new == 1 then redis.call('EXPIRE', KEYS[1], window) end
return 0
"""


class LoginProtectionUnavailable(Exception):
    """The shared limiter cannot safely make a decision."""


def _account_key(username: str) -> str:
    # MySQL usernames commonly use case/accent insensitive collations. Merge
    # spelling variants conservatively so they cannot evade the account budget.
    normalized = unicodedata.normalize('NFKD', username).casefold().rstrip()
    normalized = ''.join(char for char in normalized if not unicodedata.combining(char))
    return 'login:account:' + hashlib.sha256(normalized.encode('utf-8')).hexdigest()


async def reserve_login(username: str, request) -> tuple[str, int]:
    key = _account_key(username)
    ip_key = 'login:ip:' + hashlib.sha256(get_comment_ip(request).encode('utf-8')).hexdigest()
    try:
        retry = await asyncio.wait_for(
            get_redis().eval(RESERVE_SCRIPT, 2, key, ip_key, WINDOW_SECONDS, ACCOUNT_MAXIMUM, IP_MAXIMUM),
            timeout=REDIS_TIMEOUT_SECONDS,
        )
        return key, max(0, int(retry))
    except Exception:
        raise LoginProtectionUnavailable() from None


async def clear_login_failures(account_key: str) -> None:
    try:
        await asyncio.wait_for(get_redis().delete(account_key), timeout=REDIS_TIMEOUT_SECONDS)
    except Exception:
        raise LoginProtectionUnavailable() from None
