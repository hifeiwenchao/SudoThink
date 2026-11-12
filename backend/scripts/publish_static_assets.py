"""Publish a versioned Vite build to OSS before switching the site's HTML.

The .env credentials stay in this process. Only built resources are uploaded;
index.html stays at the web origin. Existing OSS objects are never deleted.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

CACHE_CONTROL = "public,max-age=31536000,immutable"
MAX_ASSET_BYTES = 50 * 1024 * 1024
CONTENT_TYPES = {
    ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
    ".json": "application/json", ".wasm": "application/wasm", ".txt": "text/plain",
    ".xml": "application/xml", ".svg": "image/svg+xml", ".ico": "image/x-icon",
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
    ".webp": "image/webp", ".avif": "image/avif", ".woff": "font/woff",
    ".woff2": "font/woff2", ".ttf": "font/ttf", ".otf": "font/otf",
    ".eot": "application/vnd.ms-fontobject", ".mp4": "video/mp4", ".webm": "video/webm",
}


@dataclass(frozen=True)
class StaticAsset:
    path: Path
    key: str
    content_type: str


def _safe_path(value: str) -> str:
    if not value or not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise ValueError("静态资源路径仅支持字母、数字、下划线、点、短横线和目录分隔符")
    if any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError("静态资源路径不能包含空目录或路径穿越")
    return value


def _https_base(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or any(char.isspace() for char in value)):
        raise ValueError("CDN 地址必须是无凭据、查询参数或片段的完整 HTTPS URL")
    return value.rstrip("/")


class _BuildReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "script" and attributes.get("src"):
            self.urls.append(attributes["src"])
        if tag == "link" and attributes.get("rel") in ("stylesheet", "modulepreload"):
            self.urls.append(attributes.get("href", ""))


def plan_assets(
    *, directory: Path, asset_base_url: str, cdn_base_url: str, static_prefix: str,
) -> list[StaticAsset]:
    """Validate the complete build before any upload can occur."""
    cdn_base = _https_base(cdn_base_url)
    asset_base = _https_base(asset_base_url) + "/"
    prefix = _safe_path(static_prefix.strip("/"))
    required_prefix = f"{cdn_base}/{prefix}/"
    if not asset_base.startswith(required_prefix):
        raise ValueError("VITE_ASSET_BASE_URL 必须位于 CDN_BASE_URL/OSS_STATIC_PREFIX/ 下")
    version = asset_base[len(required_prefix):].rstrip("/")
    _safe_path(version)
    if "/" in version:
        raise ValueError("请为静态构建使用一个独立版本目录，例如 static/release-1/")
    object_prefix = f"{prefix}/{version}"
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("构建目录不存在或是符号链接")
    index = directory / "index.html"
    if index.is_symlink() or not index.is_file():
        raise ValueError("构建目录缺少 index.html")
    parser = _BuildReferences()
    parser.feed(index.read_text(encoding="utf-8"))
    if not parser.urls:
        raise ValueError("index.html 没有可发布的脚本或样式资源")
    for url in parser.urls:
        if not url.startswith(asset_base) or urlsplit(url).query or urlsplit(url).fragment:
            raise ValueError("构建中的资源地址与 VITE_ASSET_BASE_URL 不一致，请重新构建")
        relative = _safe_path(unquote(url[len(asset_base):]))
        if not (directory / relative).is_file():
            raise ValueError(f"构建缺少入口资源：{relative}")

    assets = []
    for file in sorted(directory.rglob("*")):
        if file.is_symlink():
            raise ValueError("构建目录中不能包含符号链接")
        if not file.is_file() or file == index:
            continue
        relative = _safe_path(file.relative_to(directory).as_posix())
        mime = CONTENT_TYPES.get(file.suffix.lower())
        if mime is None or file.name.startswith("."):
            raise ValueError(f"不支持发布该文件：{relative}")
        if not 0 < file.stat().st_size <= MAX_ASSET_BYTES:
            raise ValueError(f"静态文件必须非空且不超过 50 MB：{relative}")
        assets.append(StaticAsset(file, f"{object_prefix}/{relative}", mime))
    if not assets:
        raise ValueError("没有可发布的静态资源")
    return assets


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_asset(asset: StaticAsset, form: dict) -> None:
    """OSS requires all policy fields before the file, which must be last."""
    boundary = "SudoThink" + uuid4().hex
    body = bytearray()
    for name, value in form["fields"].items():
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    filename = "asset" + asset.path.suffix.lower()
    body.extend(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: {asset.content_type}\r\n\r\n'.encode()
    )
    body.extend(asset.path.read_bytes())
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    request = Request(
        form["upload_url"], data=bytes(body), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=120) as response:
            if response.status not in (200, 201, 204):
                raise ValueError(f"OSS 上传未成功：{asset.key}")
    except HTTPError as error:
        # Do not log signed form fields or an upstream response containing credentials.
        raise ValueError(f"OSS 上传失败（HTTP {error.code}）：{asset.key}") from None
    except URLError:
        raise ValueError(f"无法连接 OSS，请检查网络和 Endpoint：{asset.key}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", type=Path, default=BACKEND_ROOT.parent / "frontend/dist")
    parser.add_argument("--dry-run", action="store_true", help="仅检查构建与 CDN 路径，不上传")
    arguments = parser.parse_args(argv)
    from app.core.config import settings
    from app.core.oss import sign_post_policy
    import os

    try:
        assets = plan_assets(
            directory=arguments.directory,
            asset_base_url=os.getenv("VITE_ASSET_BASE_URL", ""),
            cdn_base_url=settings.CDN_BASE_URL, static_prefix=settings.OSS_STATIC_PREFIX,
        )
        if arguments.dry_run:
            print(f"检查通过：{len(assets)} 个资源；HTML 保留在站点，OSS 旧资源保留。")
            return 0
        for asset in assets:
            form = sign_post_policy(
                key=asset.key, size=asset.path.stat().st_size, content_type=asset.content_type,
                config=settings, cache_control=CACHE_CONTROL,
            )
            post_asset(asset, form)
            print(f"已上传 {asset.key}")
        print(f"发布完成：{len(assets)} 个资源。请确认 CDN 可读取新资源后再切换前端容器。")
        return 0
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
