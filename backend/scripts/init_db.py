"""Initialize the database schema and the first administrator account.

The command is intentionally idempotent and can be run from either the
repository root or the backend directory::

    python backend/scripts/init_db.py
    cd backend && python scripts/init_db.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

import aiomysql
from dotenv import load_dotenv
from tortoise import Tortoise


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

# Always resolve the project-level .env, regardless of the current directory.
load_dotenv(PROJECT_DIR / ".env")

from app.core.config import TORTOISE_ORM  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.user import User  # noqa: E402


_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少必需环境变量: {name}")
    return value


def _database_name() -> str:
    name = _required_env("MYSQL_DATABASE")
    if not _IDENTIFIER_RE.fullmatch(name):
        raise RuntimeError("MYSQL_DATABASE 只能包含字母、数字和下划线")
    return name


async def create_database() -> None:
    host = os.getenv("MYSQL_HOST", "127.0.0.1")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_ADMIN_USER") or os.getenv("MYSQL_ROOT_USER") or os.getenv(
        "MYSQL_USER", "root"
    )
    password = os.getenv("MYSQL_ADMIN_PASSWORD") or os.getenv("MYSQL_ROOT_PASSWORD") or os.getenv(
        "MYSQL_PASSWORD", ""
    )
    database = _database_name()

    connection = await aiomysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        autocommit=True,
    )
    try:
        async with connection.cursor() as cursor:
            await cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()


async def initialize_schema() -> None:
    await Tortoise.init(config=TORTOISE_ORM)
    try:
        await Tortoise.generate_schemas(safe=True)
    finally:
        await Tortoise.close_connections()


async def initialize_admin() -> None:
    username = _required_env("ADMIN_USERNAME")
    email = _required_env("ADMIN_EMAIL")
    password = _required_env("ADMIN_PASSWORD")
    if len(password) < 6:
        raise RuntimeError("ADMIN_PASSWORD 至少需要 6 个字符")

    await Tortoise.init(config=TORTOISE_ORM)
    try:
        user = await User.get_or_none(username=username)
        if user is None:
            if await User.exists(email=email):
                raise RuntimeError(f"ADMIN_EMAIL 已被其他用户使用: {email}")
            user = await User.create(
                username=username,
                email=email,
                password_hash=hash_password(password),
                nickname=username,
                is_active=True,
                is_admin=True,
            )
            print(f"管理员已创建: {user.username}")
            return

        changed = []
        if not user.is_admin:
            user.is_admin = True
            changed.append("is_admin")
        if not user.is_active:
            user.is_active = True
            changed.append("is_active")
        if changed:
            await user.save(update_fields=[*changed, "updated_at"])
        print(f"管理员已存在，保留原密码: {user.username}")
    finally:
        await Tortoise.close_connections()


async def initialize() -> None:
    print("正在创建数据库...")
    await create_database()
    print("数据库已就绪，正在创建表...")
    await initialize_schema()
    print("数据表已就绪，正在初始化管理员...")
    await initialize_admin()
    print("初始化完成")


if __name__ == "__main__":
    try:
        asyncio.run(initialize())
    except Exception as exc:
        print(f"初始化失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
