"""Alibaba Cloud CDN cache operations using the standard-library RPC signer.

API version: 2018-05-10. Credentials stay on the server; callers can only use
the explicitly implemented refresh, preload, and task-list operations.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
from http.client import HTTPException
import ipaddress
import json
import re
import socket
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from app.core.config import settings


CDN_ENDPOINT = "https://cdn.aliyuncs.com/"
CDN_API_VERSION = "2018-05-10"
MAX_URL_LENGTH = 1024
REFRESH_LIMITS = {"File": 1000, "Directory": 100, "Regex": 1}
PRELOAD_LIMIT = 100
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class CDNError(Exception):
    """A safe error for the administrator, without upstream messages or keys."""

    def __init__(self, message: str, *, status: int = 502):
        super().__init__(message)
        self.status = status


def _credentials(config) -> tuple[str, str, str]:
    values = tuple(getattr(config, name, "") for name in (
        "ACCESS_KEY_ID", "ACCESS_KEY_SECRET", "OSS_SECURITY_TOKEN",
    ))
    if any(not isinstance(value, str) for value in values):
        raise ValueError("CDN credentials are invalid")
    key_id, secret, token = values
    if (
        not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key_id)
        or not 1 <= len(secret) <= 512
        or any(not 33 <= ord(char) <= 126 for char in secret)
        or len(token) > 16384
        or any(not 33 <= ord(char) <= 126 for char in token)
    ):
        raise ValueError("CDN credentials are invalid")
    return key_id, secret, token


def get_cdn_configuration(config=settings) -> dict:
    try:
        _credentials(config)
        enabled = True
    except ValueError:
        enabled = False
    base_url = getattr(config, "CDN_BASE_URL", "")
    try:
        base_url = validate_cdn_url(base_url) if base_url else ""
    except ValueError:
        base_url = ""
    return {
        "enabled": enabled,
        "cdn_base_url": base_url,
        "refresh_types": list(REFRESH_LIMITS),
        "limits": {
            "refresh_file": REFRESH_LIMITS["File"],
            "refresh_directory": REFRESH_LIMITS["Directory"],
            "refresh_regex": REFRESH_LIMITS["Regex"],
            "preload": PRELOAD_LIMIT,
            "max_url_length": MAX_URL_LENGTH,
        },
    }


def validate_cdn_url(value: str, *, object_type: str = "File") -> str:
    """Validate an HTTP(S) URL; Alibaba Cloud checks CDN domain ownership.

    URLs are passed only to Alibaba Cloud's fixed RPC endpoint, never fetched
    by this server. Other CDN domains belonging to the account are supported.
    Regular expressions are allowed only in the path/query, not in the host.
    """
    if (
        not isinstance(value, str) or not value or len(value) > MAX_URL_LENGTH
        or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        or "#" in value
    ):
        raise ValueError(f"URL 必须为 1 至 {MAX_URL_LENGTH} 个字符且不能包含空白或片段")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise ValueError("URL 格式无效") from None
    if (
        parts.scheme not in {"http", "https"} or not parts.hostname
        or parts.username is not None or parts.password is not None
        or parts.fragment or port is not None
        or len(parts.hostname) > 253
    ):
        raise ValueError("URL 必须使用 http/https CDN 域名且不能包含账号、端口或片段")
    hostname = parts.hostname
    if any(
        not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
        for label in hostname.split(".")
    ):
        raise ValueError("URL 域名无效")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("请使用 CDN 加速域名，不支持 IP 地址")
    if object_type == "Directory" and (not parts.path.endswith("/") or parts.query):
        raise ValueError("目录 URL 必须以 / 结尾且不能包含查询参数")
    if object_type != "Regex" and "\\" in value:
        raise ValueError("URL 不能包含反斜杠")
    if object_type == "Regex":
        remaining = parts.path + ("?" + parts.query if parts.query else "")
        for pattern in ("[0-9]", "[a-z]", "[^/]*", ".*"):
            remaining = remaining.replace(pattern, "")
        if any(char in remaining for char in "[]*\\{}()|^$"):
            raise ValueError("正则刷新仅支持 [0-9]、[a-z]、[^/]* 和 .* 模式")
    return value


def validate_cdn_urls(urls, *, object_type: str = "File", preload: bool = False) -> list[str]:
    if not isinstance(object_type, str) or object_type not in REFRESH_LIMITS:
        raise ValueError("刷新类型必须为 File、Directory 或 Regex")
    maximum = PRELOAD_LIMIT if preload else REFRESH_LIMITS[object_type]
    if not isinstance(urls, list) or not 1 <= len(urls) <= maximum:
        raise ValueError(f"请提交 1 至 {maximum} 个 URL")
    result = [validate_cdn_url(value, object_type=object_type) for value in urls]
    if preload:
        if any(urlsplit(value).path in {"", "/"} or urlsplit(value).path.endswith("/") for value in result):
            raise ValueError("预热仅支持具体文件 URL，不支持目录")
        if any(any(char in value for char in "*[]") for value in result):
            raise ValueError("预热仅支持具体文件 URL，不支持正则表达式")
    if len(set(result)) != len(result):
        raise ValueError("URL 不能重复")
    if len({urlsplit(value).hostname for value in result}) > 10:
        raise ValueError("单次请求最多包含 10 个 CDN 域名")
    return result


def _percent(value) -> str:
    return quote(str(value), safe="~")


def _signed_request(action: str, arguments: dict, config, *, now=None, nonce=None) -> Request:
    key_id, secret, token = _credentials(config)
    current = now or datetime.now(timezone.utc)
    params = {
        "Action": action,
        "Version": CDN_API_VERSION,
        "Format": "JSON",
        "AccessKeyId": key_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": nonce or uuid4().hex,
        "Timestamp": current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        **arguments,
    }
    if token:
        params["SecurityToken"] = token
    canonical = "&".join(_percent(key) + "=" + _percent(value) for key, value in sorted(params.items()))
    message = "POST&%2F&" + _percent(canonical)
    params["Signature"] = base64.b64encode(hmac.new(
        (secret + "&").encode("utf-8"), message.encode("utf-8"), hashlib.sha1,
    ).digest()).decode("ascii")
    return Request(
        CDN_ENDPOINT, data=urlencode(params).encode("ascii"), method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_response(response) -> dict:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise CDNError("CDN 服务返回数据过大")
    try:
        result = json.loads(body)
    except (ValueError, UnicodeError):
        raise CDNError("CDN 服务返回数据无效") from None
    if not isinstance(result, dict):
        raise CDNError("CDN 服务返回数据无效")
    return result


def _upstream_error(result: dict) -> CDNError:
    code = result.get("Code", "UnknownError")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", code):
        code = "UnknownError"
    if any(word in code.lower() for word in ("throttl", "quota", "exceed")):
        return CDNError(f"CDN 请求频率或配额已达上限（{code}）", status=429)
    if any(word in code.lower() for word in ("accesskey", "signature", "unauthor", "forbidden", "securitytoken")):
        return CDNError(f"CDN 服务鉴权失败，请检查服务端权限配置（{code}）", status=502)
    return CDNError(f"CDN 操作失败（{code}）")


def _rpc(action: str, arguments: dict, config=settings) -> dict:
    try:
        request = _signed_request(action, arguments, config)
    except ValueError:
        raise CDNError("CDN 服务尚未配置或配置无效", status=503) from None
    opener = build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            result = _read_response(response)
    except HTTPError as exc:
        try:
            result = _read_response(exc)
        finally:
            exc.close()
        raise _upstream_error(result) from None
    except (URLError, TimeoutError, socket.timeout, OSError, HTTPException):
        # Never expose exceptions containing signed request URLs or tokens.
        raise CDNError("CDN 服务暂不可用，请先查询任务确认是否已提交，再决定是否重试") from None
    if result.get("Code"):
        raise _upstream_error(result)
    return result


def _safe_string(value, maximum: int = 2048) -> str:
    return value[:maximum] if isinstance(value, str) else str(value)[:maximum] if isinstance(value, (int, float)) else ""


def _submission(result: dict, key: str) -> dict:
    task_id = result.get(key)
    if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_,.-]{1,2048}", task_id):
        raise CDNError("CDN 服务未返回任务编号，请查询任务列表确认提交结果")
    return {"task_id": task_id, "request_id": _safe_string(result.get("RequestId"), 128)}


async def refresh_cdn_cache(urls, *, object_type: str, config=settings) -> dict:
    validated = validate_cdn_urls(urls, object_type=object_type)
    result = await asyncio.to_thread(_rpc, "RefreshObjectCaches", {
        "ObjectPath": "\n".join(validated), "ObjectType": object_type,
    }, config)
    return _submission(result, "RefreshTaskId")


async def preload_cdn_cache(urls, *, config=settings) -> dict:
    validated = validate_cdn_urls(urls, preload=True)
    result = await asyncio.to_thread(_rpc, "PushObjectCache", {
        "ObjectPath": "\n".join(validated),
    }, config)
    return _submission(result, "PushTaskId")


async def list_cdn_tasks(*, task_id: str = "", page: int = 1, size: int = 20, config=settings) -> dict:
    if not isinstance(task_id, str) or task_id and not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", task_id):
        raise ValueError("任务编号无效，请逐个查询任务编号")
    if type(page) is not int or not 1 <= page <= 100000 or type(size) is not int or not 1 <= size <= 50:
        raise ValueError("分页参数无效，size 必须为 1 至 50")
    arguments = {"PageNumber": page, "PageSize": size}
    if task_id:
        arguments["TaskId"] = task_id
    result = await asyncio.to_thread(_rpc, "DescribeRefreshTasks", arguments, config)
    rows = result.get("Tasks", {}).get("CDNTask", []) if isinstance(result.get("Tasks"), dict) else []
    if not isinstance(rows, list):
        raise CDNError("CDN 服务返回任务数据无效")
    fields = {
        "task_id": "TaskId", "object_path": "ObjectPath", "object_type": "ObjectType",
        "status": "Status", "process": "Process", "creation_time": "CreationTime",
        "description": "Description",
    }
    items = [{key: _safe_string(row.get(source)) for key, source in fields.items()}
             for row in rows if isinstance(row, dict)]
    total = result.get("TotalCount", 0)
    try:
        total = max(0, int(total))
    except (ValueError, TypeError):
        raise CDNError("CDN 服务返回任务总数无效") from None
    return {
        "items": items, "total": total, "page": page, "size": size,
        "request_id": _safe_string(result.get("RequestId"), 128),
    }
