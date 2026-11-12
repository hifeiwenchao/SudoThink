"""Upgrade MySQL category, About, donation settings and comment schemas.

Run after deploying the new backend code and before starting application workers::

    cd backend
    python scripts/upgrade_site_content.py

For Docker deployments::

    docker compose run --rm backend python scripts/upgrade_site_content.py

This command uses the project .env, preserves existing records, and may be run
repeatedly. It preserves legacy comments and their user links while adding guest
metadata, allowing nullable authors, and marking rejections without deleting rows.
User-Agent metadata is added with an empty default for historical comments.
Existing approvals remain unchanged; unapproved comments start as pending. Old
rejections that were already deleted cannot be recovered by this migration.
The configured MYSQL_USER needs CREATE and ALTER privileges. It does not create
a database or modify administrator accounts; first deployments should
continue using scripts/init_db.py instead.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from tortoise import Tortoise

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR.parent / ".env")

from app.core.config import TORTOISE_ORM  # noqa: E402
from app.core.schema import upgrade_site_content_schema  # noqa: E402


async def upgrade() -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        await upgrade_site_content_schema()
    finally:
        await Tortoise.close_connections()
    print("分类权重、关于我、打赏设置与评论审核结构升级完成，现有数据已保留")


if __name__ == "__main__":
    try:
        asyncio.run(upgrade())
    except Exception as exc:
        print(f"站点内容升级失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
