"""有界、脱敏的 API 请求日志；写入失败不得影响业务响应。"""
from __future__ import annotations

import json
import logging
import math
import re
from time import perf_counter
from urllib.parse import parse_qsl, urlencode

from sanic import Sanic

from app.models.api_request_log import ApiRequestLog

logger = logging.getLogger("app.request_log")
MAX_RAW_BYTES = 64 * 1024
MAX_PARAMS_BYTES = 16 * 1024
MAX_STRING_CHARS = 1024
MAX_KEY_CHARS = 128
MAX_VALUES = 100
MAX_DEPTH = 6
REDACTED = "[REDACTED]"
TRUNCATED = "[TRUNCATED]"


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return any(part in normalized for part in (
        "password", "passwd", "pwd", "token", "secret", "accesskey", "apikey",
        "credential", "authorization", "cookie", "privatekey",
    ))


def _json_size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"))


class _Sanitizer:
    def __init__(self):
        self.remaining = MAX_VALUES

    def clean(self, value, depth=0):
        if depth >= MAX_DEPTH or self.remaining <= 0:
            return TRUNCATED
        self.remaining -= 1
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                if self.remaining <= 0:
                    result["_truncated"] = True
                    break
                key = str(key)
                safe_key = key[:MAX_KEY_CHARS]
                result[safe_key] = REDACTED if _sensitive_key(key) else self.clean(item, depth + 1)
                # Redactions also consume a value, preventing unbounded secret fields.
                if _sensitive_key(key):
                    self.remaining -= 1
            return result
        if isinstance(value, (list, tuple)):
            result = []
            for item in value:
                if self.remaining <= 0:
                    result.append(TRUNCATED)
                    break
                result.append(self.clean(item, depth + 1))
            return result
        if isinstance(value, str):
            return value if len(value) <= MAX_STRING_CHARS else value[:MAX_STRING_CHARS] + TRUNCATED
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, float):
            return value if math.isfinite(value) else TRUNCATED
        # Matched route values can include UUID/date objects; do not inspect arbitrary objects.
        return str(value)[:MAX_STRING_CHARS]


def _form_parameters(raw: str):
    if len(raw.encode("utf-8")) > MAX_RAW_BYTES:
        return {"_omitted": "query too large"}
    # parse_qsl otherwise allocates every field before our recursive limits apply.
    pairs = parse_qsl(raw, keep_blank_values=True, max_num_fields=MAX_VALUES)
    result = {}
    for key, value in pairs:
        if key in result:
            if not isinstance(result[key], list):
                result[key] = [result[key]]
            result[key].append(value)
        else:
            result[key] = value
    return result


def _query_parameters(raw: str):
    try:
        return _form_parameters(raw)
    except (ValueError, UnicodeError):
        return {"_omitted": "too many or invalid query fields"}


def _body_parameters(request):
    body = request.body
    if not body:
        return None
    if len(body) > MAX_RAW_BYTES:
        return {"_omitted": "body too large", "bytes": len(body)}
    content_type = request.content_type.lower()
    if content_type == "application/json" or content_type.endswith("+json"):
        try:
            return json.loads(body)
        except (ValueError, UnicodeError, RecursionError):
            return {"_omitted": "invalid JSON body", "bytes": len(body)}
    if content_type == "application/x-www-form-urlencoded":
        try:
            return _form_parameters(body.decode("utf-8"))
        except (ValueError, UnicodeError):
            return {"_omitted": "invalid or excessive form fields", "bytes": len(body)}
    # Multipart/file/plain text payloads are never parsed or copied into logs.
    return {"_omitted": "non-JSON body", "bytes": len(body)}


def _safe_parameters(request):
    sanitizer = _Sanitizer()
    # Keep matched route params first: aid must survive a large query/body for view accounting.
    path_params = sanitizer.clean(request.match_info or {})
    query_params = sanitizer.clean(_query_parameters(request.query_string))
    body_params = sanitizer.clean(_body_parameters(request))
    parameters = [query_params, path_params, body_params]
    # Bound stored JSON bytes as well as recursion/node/string limits. Prefer retaining
    # the matched route and query; a very wide body can be omitted independently.
    if _json_size(parameters) > MAX_PARAMS_BYTES:
        body_params = {"_omitted": "parameter size limit"}
    if _json_size([query_params, path_params, body_params]) > MAX_PARAMS_BYTES:
        query_params = {"_omitted": "parameter size limit"}
    if _json_size([query_params, path_params, body_params]) > MAX_PARAMS_BYTES:
        path_params = {"_omitted": "parameter size limit"}
    return query_params, path_params, body_params


def _safe_url(request, query_params):
    # Rebuild the URL from sanitized query values; never truncate an unsanitized URL.
    query = urlencode(query_params, doseq=True)
    return (request.path + ("?" + query if query else ""))[:2048]


def register_request_logging(app: Sanic) -> None:
    @app.middleware("request", priority=100)
    async def _start_request_log(request):
        if request.path == "/api" or request.path.startswith("/api/"):
            request.ctx.api_log_started = perf_counter()

    @app.middleware("response", priority=100)
    async def _save_request_log(request, response):
        if request.path != "/api" and not request.path.startswith("/api/"):
            return
        # Error responses for unmatched routes may bypass request middleware.
        finished = perf_counter()
        started = getattr(request.ctx, "api_log_started", finished)
        try:
            query_params, path_params, body_params = _safe_parameters(request)
            await ApiRequestLog.create(
                method=request.method[:16], url=_safe_url(request, query_params),
                path=request.path[:512], query_params=query_params, path_params=path_params,
                body_params=body_params, status_code=response.status,
                duration_ms=min(2147483647, max(0, int((finished - started) * 1000))),
            )
        except Exception:
            # Exception messages/tracebacks may contain SQL parameters or credentials.
            logger.warning("API request log could not be saved")
