"""Explicit, additive upgrades for databases created before site-content management."""
from tortoise import Tortoise, connections


async def upgrade_site_content_schema() -> None:
    """Create missing tables and add category weights without replacing existing data.

    ``generate_schemas(safe=True)`` creates the new AboutPage table, but does not
    alter an existing categories table. Check MySQL metadata before adding its
    weight column so this command is safe to run again after an interrupted run.
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
