"""Explicit, idempotent upgrades for site content and comment moderation."""
import hashlib
import re

from tortoise import Tortoise, connections


def _identifier(value: str) -> str:
    """Quote names read from MySQL metadata, including custom legacy FK names."""
    return "`" + value.replace("`", "``") + "`"


async def _upgrade_guest_comments(connection) -> None:
    columns = await connection.execute_query_dict(
        "SELECT COLUMN_NAME, IS_NULLABLE, COLUMN_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'comments'"
    )
    existing = {column["COLUMN_NAME"]: column for column in columns}
    additions = {
        "is_rejected": "BOOL NOT NULL DEFAULT 0 COMMENT '是否已驳回'",
        "nickname": "VARCHAR(32) NOT NULL DEFAULT '' COMMENT '访客昵称'",
        "email": "VARCHAR(254) NOT NULL DEFAULT '' COMMENT '访客邮箱，仅供管理'",
        "ip_address": "VARCHAR(45) NOT NULL DEFAULT '' COMMENT '服务端记录的评论 IP'",
        "user_agent": "VARCHAR(1024) NOT NULL DEFAULT '' COMMENT '评论请求 User-Agent，仅供管理'",
        "location": "VARCHAR(256) NOT NULL DEFAULT '' COMMENT '评论 IP 归属地'",
    }
    changes = [
        f"ADD COLUMN `{name}` {definition}"
        for name, definition in additions.items() if name not in existing
    ]
    author_column = existing.get("author_id")
    if author_column is None:
        raise RuntimeError("comments 表缺少 author_id，无法安全升级访客评论")
    if author_column["IS_NULLABLE"] != "YES":
        column_type = author_column["COLUMN_TYPE"]
        if not re.fullmatch(r"(?:tinyint|smallint|mediumint|int|bigint)(?:\(\d+\))?(?: unsigned)?", column_type, re.IGNORECASE):
            raise RuntimeError("comments.author_id 类型异常，无法安全升级")
        changes.append(f"MODIFY COLUMN `author_id` {column_type} NULL")

    foreign_keys = await connection.execute_query_dict(
        "SELECT kcu.CONSTRAINT_NAME, kcu.REFERENCED_TABLE_NAME, "
        "kcu.REFERENCED_COLUMN_NAME, rc.DELETE_RULE, rc.UPDATE_RULE "
        "FROM information_schema.KEY_COLUMN_USAGE AS kcu "
        "JOIN information_schema.REFERENTIAL_CONSTRAINTS AS rc "
        "ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA "
        "AND rc.TABLE_NAME = kcu.TABLE_NAME AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME "
        "WHERE kcu.TABLE_SCHEMA = DATABASE() AND kcu.TABLE_NAME = 'comments' "
        "AND kcu.COLUMN_NAME = 'author_id' AND kcu.REFERENCED_TABLE_NAME IS NOT NULL"
    )
    if len(foreign_keys) > 1:
        raise RuntimeError("comments.author_id 外键结构异常，无法安全升级")
    foreign_key = foreign_keys[0] if foreign_keys else {
        "CONSTRAINT_NAME": "fk_comments_author_users", "REFERENCED_TABLE_NAME": "users",
        "REFERENCED_COLUMN_NAME": "id", "DELETE_RULE": "", "UPDATE_RULE": "RESTRICT",
    }
    if foreign_key["DELETE_RULE"] != "SET NULL":
        legacy_name = foreign_key["CONSTRAINT_NAME"]
        if foreign_keys:
            changes.insert(0, f"DROP FOREIGN KEY {_identifier(legacy_name)}")
        # MySQL retains the old FK name until an ALTER completes, so replacing it
        # atomically must use a new schema-wide name (maximum 64 characters).
        digest = hashlib.sha256(legacy_name.encode("utf-8")).hexdigest()[:16]
        name = _identifier("fk_comments_guest_" + digest)
        update_rule = foreign_key["UPDATE_RULE"]
        if update_rule not in {"CASCADE", "RESTRICT", "SET NULL", "NO ACTION", "SET DEFAULT"}:
            raise RuntimeError("comments.author_id 外键规则异常，无法安全升级")
        changes.append(
            f"ADD CONSTRAINT {name} FOREIGN KEY (`author_id`) "
            f"REFERENCES {_identifier(foreign_key['REFERENCED_TABLE_NAME'])} "
            f"({_identifier(foreign_key['REFERENCED_COLUMN_NAME'])}) "
            f"ON DELETE SET NULL ON UPDATE {update_rule}"
        )
    if changes:
        # MySQL 8 applies the DDL atomically, including replacing the legacy FK.
        await connection.execute_script("ALTER TABLE `comments` " + ", ".join(changes))


async def upgrade_site_content_schema() -> None:
    """Create missing tables and upgrade legacy columns without replacing data.

    ``generate_schemas(safe=True)`` creates the AboutPage, DonationSettings and
    ApiRequestLog tables, but does not alter an existing categories table. Check MySQL metadata
    before adding category weights, guest comment metadata, and rejection flags.
    Existing approvals remain intact; unapproved comments start as pending.
    Historical comments receive an empty User-Agent; only new submissions record it.
    Comment authors become nullable, retaining their FK with ON DELETE SET NULL.
    """
    connection = connections.get("default")
    if connection.capabilities.dialect != "mysql":
        raise RuntimeError("站点内容升级脚本仅支持 MySQL")

    await Tortoise.generate_schemas(safe=True)
    columns = await connection.execute_query_dict(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() "
        "AND TABLE_NAME = 'categories' AND COLUMN_NAME = 'weight'"
    )
    if not columns:
        await connection.execute_script(
            "ALTER TABLE `categories` ADD COLUMN `weight` INT NOT NULL DEFAULT 0 "
            "COMMENT '排序权重，越大越靠前'"
        )
    await _upgrade_guest_comments(connection)
