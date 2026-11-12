"""Short-lived OSS V4 PostObject credentials, without an OSS SDK or network calls.

The HMAC derivation and policy format follow Alibaba Cloud's V4 PostObject guide:
https://help.aliyun.com/zh/oss/developer-reference/signature-version-4-recommend
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit, urlunsplit
from uuid import uuid4

from app.core.config import settings


IMAGE_TYPES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/gif": [".gif"],
    "image/webp": [".webp"],
    "image/avif": [".avif"],
}
VIDEO_TYPES = {"video/mp4": [".mp4"], "video/webm": [".webm"]}
POLICY_LIFETIME_SECONDS = 300


def _visible_ascii(value: str, maximum: int) -> bool:
    return (
        isinstance(value, str) and 0 < len(value) <= maximum
        and all(33 <= ord(char) <= 126 for char in value)
    )


def normalize_prefix(value: str) -> str:
    """Normalize an object prefix while rejecting traversal and encoded separators."""
    if not isinstance(value, str):
        raise ValueError("invalid object prefix")
    prefix = value.strip("/")
    if not prefix or len(prefix) > 768 or any(
        not re.fullmatch(r"[A-Za-z0-9_-]+", segment) for segment in prefix.split("/")
    ):
        raise ValueError("invalid object prefix")
    return prefix


def validate_https_url(value: str, *, allow_path: bool = True) -> str:
    """Validate a public HTTPS base URL without credentials, queries or fragments."""
    if (
        not isinstance(value, str) or not value or len(value) > 2048
        or any(ord(char) <= 32 or ord(char) == 127 for char in value)
        or "\\" in value
    ):
        raise ValueError("invalid HTTPS URL")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        raise ValueError("invalid HTTPS URL") from None
    if (
        parts.scheme != "https" or not parts.hostname
        or parts.username is not None or parts.password is not None
        or parts.query or parts.fragment or "?" in value or "#" in value
        or port is not None and not 1 <= port <= 65535
        or not allow_path and parts.path not in {"", "/"}
    ):
        raise ValueError("invalid HTTPS URL")
    hostname = parts.hostname
    if len(hostname) > 253 or any(
        not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
        for label in hostname.split(".")
    ):
        raise ValueError("invalid HTTPS hostname")
    decoded_path = unquote(parts.path)
    if (
        "\\" in decoded_path or any(ord(char) < 32 or ord(char) == 127 for char in decoded_path)
        or any(segment in {".", ".."} for segment in decoded_path.split("/"))
        or "//" in decoded_path
    ):
        raise ValueError("invalid HTTPS path")
    return urlunsplit(("https", parts.netloc, parts.path.rstrip("/"), "", ""))


def validate_oss_config(config=settings) -> dict[str, str]:
    """Return safe endpoints or raise a generic error which contains no credentials."""
    if (
        not _visible_ascii(config.ACCESS_KEY_ID, 128)
        or not re.fullmatch(r"[A-Za-z0-9_-]+", config.ACCESS_KEY_ID)
        or not _visible_ascii(config.ACCESS_KEY_SECRET, 512)
        or config.OSS_SECURITY_TOKEN and not _visible_ascii(config.OSS_SECURITY_TOKEN, 16384)
        or not isinstance(config.OSS_REGION, str)
        or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+", config.OSS_REGION)
        or not isinstance(config.OSS_BUCKET, str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", config.OSS_BUCKET)
    ):
        raise ValueError("invalid OSS configuration")
    endpoint = validate_https_url(config.OSS_ENDPOINT, allow_path=False)
    if endpoint != f"https://oss-{config.OSS_REGION}.aliyuncs.com":
        raise ValueError("invalid OSS endpoint")
    cdn_base_url = validate_https_url(config.CDN_BASE_URL)
    media_prefix = normalize_prefix(config.OSS_MEDIA_PREFIX)
    for size in (config.OSS_IMAGE_MAX_BYTES, config.OSS_VIDEO_MAX_BYTES):
        if type(size) is not int or size < 1:
            raise ValueError("invalid upload size limit")
    return {
        "upload_url": f"https://{config.OSS_BUCKET}.oss-{config.OSS_REGION}.aliyuncs.com",
        "cdn_base_url": cdn_base_url,
        "media_prefix": media_prefix,
    }


def get_upload_configuration(config=settings) -> dict:
    """Only return public upload capabilities; invalid/missing config is disabled."""
    try:
        validate_oss_config(config)
        enabled = True
    except ValueError:
        enabled = False
    return {
        "enabled": enabled,
        "image_max_bytes": config.OSS_IMAGE_MAX_BYTES,
        "video_max_bytes": config.OSS_VIDEO_MAX_BYTES,
        "image_types": IMAGE_TYPES,
        "video_types": VIDEO_TYPES,
    }


def sign_v4_policy(policy: str, secret: str, date: str, region: str) -> str:
    """Sign the base64 policy using OSS's four-stage V4 HMAC derivation."""
    signing_key = ("aliyun_v4" + secret).encode("utf-8")
    for value in (date, region, "oss", "aliyun_v4_request"):
        signing_key = hmac.new(signing_key, value.encode("utf-8"), hashlib.sha256).digest()
    return hmac.new(signing_key, policy.encode("ascii"), hashlib.sha256).hexdigest()


def sign_post_policy(
    *, key: str, size: int, content_type: str, config=settings,
    now: datetime | None = None, cache_control: str | None = None,
) -> dict:
    """Sign one exact object; callers separately enforce their allowed media types.

    The static publisher reuses this function for CSS/JS and immutable cache headers.
    Each supplied form field is pinned by an exact policy condition; the binary
    ``file`` part must be added last by the client, using the same MIME type.
    """
    validated = validate_oss_config(config)
    if (
        not isinstance(key, str) or len(key.encode("utf-8")) > 1023
        or not re.fullmatch(r"[A-Za-z0-9._/-]+", key)
        or any(part in {"", ".", ".."} for part in key.split("/"))
    ):
        raise ValueError("invalid object key")
    if type(size) is not int or size < 1:
        raise ValueError("invalid object size")
    if not isinstance(content_type, str) or not re.fullmatch(
        r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(?:; ?charset=[A-Za-z0-9_-]+)?",
        content_type,
    ):
        raise ValueError("invalid content type")
    if cache_control is not None and (
        not isinstance(cache_control, str) or not 1 <= len(cache_control) <= 256
        or any(ord(char) < 32 or ord(char) > 126 for char in cache_control)
    ):
        raise ValueError("invalid cache control")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("signing time must include a timezone")
    current = current.astimezone(timezone.utc).replace(microsecond=0)
    expiration = current + timedelta(seconds=POLICY_LIFETIME_SECONDS)
    date = current.strftime("%Y%m%d")
    fields = {
        "key": key,
        "Content-Type": content_type,
        "success_action_status": "201",
        "x-oss-signature-version": "OSS4-HMAC-SHA256",
        "x-oss-credential": (
            f"{config.ACCESS_KEY_ID}/{date}/{config.OSS_REGION}/oss/aliyun_v4_request"
        ),
        "x-oss-date": current.strftime("%Y%m%dT%H%M%SZ"),
    }
    if config.OSS_SECURITY_TOKEN:
        fields["x-oss-security-token"] = config.OSS_SECURITY_TOKEN
    if cache_control is not None:
        fields["Cache-Control"] = cache_control
    conditions = [
        ["eq", "$bucket", config.OSS_BUCKET],
        ["content-length-range", size, size],
        *[["eq", "$" + name.lower(), value] for name, value in fields.items()],
    ]
    policy = {
        "expiration": expiration.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "conditions": conditions,
    }
    encoded = base64.b64encode(
        json.dumps(policy, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    fields["policy"] = encoded
    fields["x-oss-signature"] = sign_v4_policy(
        encoded, config.ACCESS_KEY_SECRET, date, config.OSS_REGION
    )
    return {
        "upload_url": validated["upload_url"],
        "public_url": f"{validated['cdn_base_url']}/{key}",
        "key": key,
        "fields": fields,
        "expires_at": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def create_media_upload_policy(
    *, filename: str, size: int, content_type: str, config=settings,
) -> dict:
    """Apply the media allowlist before generating a random, server-owned key."""
    validated = validate_oss_config(config)
    if (
        not isinstance(filename, str) or not 1 <= len(filename) <= 255
        or any(ord(char) < 32 or ord(char) == 127 for char in filename)
        or type(size) is not int or size < 1
        or not isinstance(content_type, str)
    ):
        raise ValueError("invalid file metadata")
    extension = PurePosixPath(filename).suffix.lower()
    if content_type in IMAGE_TYPES and extension in IMAGE_TYPES[content_type]:
        kind, limit = "images", config.OSS_IMAGE_MAX_BYTES
    elif content_type in VIDEO_TYPES and extension in VIDEO_TYPES[content_type]:
        kind, limit = "videos", config.OSS_VIDEO_MAX_BYTES
    else:
        raise ValueError("unsupported file type or mismatched extension")
    if size > limit:
        raise ValueError("file exceeds upload size limit")
    current = datetime.now(timezone.utc)
    key = f"{validated['media_prefix']}/{kind}/{current:%Y/%m}/{uuid4().hex}{extension}"
    return sign_post_policy(
        key=key, size=size, content_type=content_type, config=config, now=current,
    )
