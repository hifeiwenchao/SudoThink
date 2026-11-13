"""微信网页 JS-SDK 签名与凭证缓存。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from app.core.config import settings
from app.core.redis import get_redis

_ACCESS_TOKEN_KEY = "wechat:access_token"
_JSAPI_TICKET_KEY = "wechat:jsapi_ticket"
_WECHAT_API_TIMEOUT = 8
_MAX_SHARE_URL_LENGTH = 2048


class WeChatError(RuntimeError):
    """微信接口或签名配置错误，不携带凭据和远端响应内容。"""


def validate_share_url(value: Any) -> str:
    """校验微信签名使用的页面地址。"""
    if not isinstance(value, str):
        raise ValueError("url must be a string")
    url = value.strip()
    if not url or len(url) > _MAX_SHARE_URL_LENGTH:
        raise ValueError("invalid url")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in url):
        raise ValueError("invalid url")

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("invalid url")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("invalid url")
    if parsed.fragment:
        raise ValueError("url must not contain a fragment")
    if settings.APP_ENV.strip().lower() == "production" and parsed.scheme != "https":
        raise ValueError("https url is required")
    return url


def _sync_request_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=_WECHAT_API_TIMEOUT) as response:
            raw = response.read(1_000_000)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise WeChatError("wechat service unavailable") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeChatError("wechat service returned invalid data") from exc
    if not isinstance(payload, dict):
        raise WeChatError("wechat service returned invalid data")
    return payload


async def _request_json(url: str) -> dict[str, Any]:
    """在线程中执行 urllib，避免阻塞 Sanic 事件循环。"""
    return await asyncio.to_thread(_sync_request_json, url)


async def _cached_value(redis_client: Any, key: str) -> str | None:
    if redis_client is None:
        return None
    try:
        value = await redis_client.get(key)
    except Exception:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    return value.strip() if isinstance(value, str) and value.strip() else None


async def _cache_value(redis_client: Any, key: str, value: str, expires_in: Any) -> None:
    if redis_client is None:
        return
    try:
        seconds = max(int(expires_in) - 120, 60)
    except (TypeError, ValueError):
        seconds = 60
    try:
        await redis_client.set(key, value, ex=seconds)
    except Exception:
        # Redis 暂时不可用时仍允许本次分享签名完成，下一次请求会重新获取凭证。
        return


def _api_error(payload: dict[str, Any]) -> bool:
    try:
        return int(payload.get("errcode", 0)) != 0
    except (TypeError, ValueError):
        return True


async def _access_token(redis_client: Any) -> str:
    cached = await _cached_value(redis_client, _ACCESS_TOKEN_KEY)
    if cached:
        return cached
    if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET:
        raise WeChatError("wechat sharing is not configured")

    query = urlencode({
        "grant_type": "client_credential",
        "appid": settings.WECHAT_APP_ID,
        "secret": settings.WECHAT_APP_SECRET,
    })
    payload = await _request_json(f"https://api.weixin.qq.com/cgi-bin/token?{query}")
    if _api_error(payload) or not isinstance(payload.get("access_token"), str):
        raise WeChatError("wechat access token request failed")
    token = payload["access_token"].strip()
    if not token:
        raise WeChatError("wechat access token request failed")
    await _cache_value(redis_client, _ACCESS_TOKEN_KEY, token, payload.get("expires_in"))
    return token


async def _jsapi_ticket(redis_client: Any) -> str:
    cached = await _cached_value(redis_client, _JSAPI_TICKET_KEY)
    if cached:
        return cached
    token = await _access_token(redis_client)
    query = urlencode({"access_token": token, "type": "jsapi"})
    payload = await _request_json(f"https://api.weixin.qq.com/cgi-bin/ticket/getticket?{query}")
    if _api_error(payload) or not isinstance(payload.get("ticket"), str):
        raise WeChatError("wechat jsapi ticket request failed")
    ticket = payload["ticket"].strip()
    if not ticket:
        raise WeChatError("wechat jsapi ticket request failed")
    await _cache_value(redis_client, _JSAPI_TICKET_KEY, ticket, payload.get("expires_in"))
    return ticket


async def create_signature(url: str, redis_client: Any = None) -> dict[str, Any]:
    """生成 wx.config 所需的签名参数。"""
    normalized_url = validate_share_url(url)
    if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET:
        raise WeChatError("wechat sharing is not configured")
    if redis_client is None:
        try:
            redis_client = get_redis()
        except Exception:
            redis_client = None

    ticket = await _jsapi_ticket(redis_client)
    nonce_str = secrets.token_hex(16)
    timestamp = int(time.time())
    canonical = (
        f"jsapi_ticket={ticket}&noncestr={nonce_str}"
        f"&timestamp={timestamp}&url={normalized_url}"
    )
    signature = hashlib.sha1(canonical.encode("utf-8")).hexdigest()
    return {
        "app_id": settings.WECHAT_APP_ID,
        "timestamp": timestamp,
        "nonce_str": nonce_str,
        "signature": signature,
    }
