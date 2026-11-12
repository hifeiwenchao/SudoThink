"""Upgrade control flow without connecting to an actual MySQL database."""
import importlib
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"


class MySQLMetadata:
    """Small metadata fixture that applies only the expected additive DDL effects."""
    def __init__(self, upgraded=False):
        self.capabilities = SimpleNamespace(dialect="mysql")
        self.weight = upgraded
        self.columns = {"author_id": {"COLUMN_NAME": "author_id", "IS_NULLABLE": "YES" if upgraded else "NO", "COLUMN_TYPE": "int"}}
        if upgraded:
            self.columns.update({name: {"COLUMN_NAME": name, "IS_NULLABLE": "NO", "COLUMN_TYPE": "varchar"} for name in ("nickname", "email", "ip_address", "location", "is_rejected", "user_agent")})
        self.foreign_keys = [{"CONSTRAINT_NAME": "legacy_comment_author_fk", "REFERENCED_TABLE_NAME": "users", "REFERENCED_COLUMN_NAME": "id", "DELETE_RULE": "SET NULL" if upgraded else "CASCADE", "UPDATE_RULE": "RESTRICT"}]
        self.records = [{"id": 7, "author_id": 13, "content": "Existing comment"}]
        self.scripts = []

    async def execute_query_dict(self, sql):
        if "TABLE_NAME = 'categories'" in sql:
            return [{"COLUMN_NAME": "weight"}] if self.weight else []
        if "KEY_COLUMN_USAGE" in sql:
            return self.foreign_keys
        if "TABLE_NAME = 'comments'" in sql:
            return list(self.columns.values())
        raise AssertionError(f"Unexpected metadata query: {sql}")

    async def execute_script(self, sql):
        self.scripts.append(sql)
        if "`categories`" in sql:
            self.weight = True
            return
        for name in ("nickname", "email", "ip_address", "location"):
            if f"ADD COLUMN `{name}`" in sql:
                self.columns[name] = {"COLUMN_NAME": name, "IS_NULLABLE": "NO", "COLUMN_TYPE": "varchar"}
        if "ADD COLUMN `is_rejected`" in sql:
            self.columns["is_rejected"] = {
                "COLUMN_NAME": "is_rejected", "IS_NULLABLE": "NO", "COLUMN_TYPE": "tinyint(1)",
            }
            for record in self.records:
                record["is_rejected"] = False
        if "ADD COLUMN `user_agent`" in sql:
            self.columns["user_agent"] = {
                "COLUMN_NAME": "user_agent", "IS_NULLABLE": "NO", "COLUMN_TYPE": "varchar(1024)",
            }
            for record in self.records:
                record["user_agent"] = ""
        if "MODIFY COLUMN `author_id`" in sql:
            self.columns["author_id"]["IS_NULLABLE"] = "YES"
        if "ON DELETE SET NULL" in sql:
            self.foreign_keys[0]["DELETE_RULE"] = "SET NULL"


class SiteContentUpgradeTests(unittest.IsolatedAsyncioTestCase):
    async def upgrade_with(self, connection):
        schema = importlib.import_module("app.core.schema")
        with (
            patch.object(schema, "connections", SimpleNamespace(get=Mock(return_value=connection))),
            patch.object(schema.Tortoise, "generate_schemas", new_callable=AsyncMock) as generate,
        ):
            await schema.upgrade_site_content_schema()
        generate.assert_awaited_once_with(safe=True)

    async def test_upgrade_adds_guest_fields_changes_author_fk_and_is_idempotent(self):
        connection = MySQLMetadata()
        await self.upgrade_with(connection)
        self.assertTrue(connection.weight)
        self.assertTrue({"nickname", "email", "ip_address", "location", "is_rejected", "user_agent"}.issubset(connection.columns))
        self.assertEqual(connection.columns["author_id"]["IS_NULLABLE"], "YES")
        self.assertEqual(connection.foreign_keys[0]["DELETE_RULE"], "SET NULL")
        self.assertEqual(connection.records, [{"id": 7, "author_id": 13, "content": "Existing comment", "is_rejected": False, "user_agent": ""}])
        self.assertEqual(len(connection.scripts), 2)
        comment_sql = connection.scripts[1]
        self.assertIn("DROP FOREIGN KEY `legacy_comment_author_fk`", comment_sql)
        self.assertNotIn("ADD CONSTRAINT `legacy_comment_author_fk`", comment_sql)
        self.assertRegex(comment_sql, r"ADD CONSTRAINT `fk_comments_guest_[0-9a-f]{16}`")
        self.assertIn("ON DELETE SET NULL ON UPDATE RESTRICT", comment_sql)
        for unsafe in ("DROP TABLE", "DELETE FROM", "TRUNCATE", "UPDATE `"):
            self.assertNotIn(unsafe, comment_sql.upper())
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 2)

    async def test_partially_upgraded_table_only_receives_missing_columns(self):
        connection = MySQLMetadata(upgraded=True)
        del connection.columns["location"]
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        self.assertIn("ADD COLUMN `location`", connection.scripts[0])
        self.assertNotIn("DROP FOREIGN KEY", connection.scripts[0])
        self.assertNotIn("MODIFY COLUMN", connection.scripts[0])

    async def test_review_upgrade_preserves_legacy_approvals_and_is_idempotent(self):
        connection = MySQLMetadata(upgraded=True)
        del connection.columns["is_rejected"]
        connection.records = [
            {"id": 7, "content": "Pending", "is_approved": False},
            {"id": 8, "content": "Approved", "is_approved": True},
        ]
        await self.upgrade_with(connection)
        self.assertIn("is_rejected", connection.columns)
        self.assertEqual(connection.records, [
            {"id": 7, "content": "Pending", "is_approved": False, "is_rejected": False},
            {"id": 8, "content": "Approved", "is_approved": True, "is_rejected": False},
        ])
        self.assertEqual(len(connection.scripts), 1)
        self.assertIn("ADD COLUMN `is_rejected` BOOL NOT NULL DEFAULT 0", connection.scripts[0])
        connection.records[0]["is_rejected"] = True
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        self.assertTrue(connection.records[0]["is_rejected"])
        self.assertTrue(connection.records[1]["is_approved"])

    async def test_fresh_schema_needs_no_alter_statements(self):
        connection = MySQLMetadata(upgraded=True)
        await self.upgrade_with(connection)
        self.assertEqual(connection.scripts, [])

    async def test_user_agent_upgrade_preserves_reviews_and_is_idempotent(self):
        connection = MySQLMetadata(upgraded=True)
        del connection.columns["user_agent"]
        connection.records = [
            {"id": 7, "is_approved": False, "is_rejected": True},
            {"id": 8, "is_approved": True, "is_rejected": False},
        ]
        await self.upgrade_with(connection)
        self.assertIn("user_agent", connection.columns)
        self.assertEqual(connection.records, [
            {"id": 7, "is_approved": False, "is_rejected": True, "user_agent": ""},
            {"id": 8, "is_approved": True, "is_rejected": False, "user_agent": ""},
        ])
        self.assertEqual(len(connection.scripts), 1)
        self.assertIn("ADD COLUMN `user_agent` VARCHAR(1024) NOT NULL DEFAULT ''", connection.scripts[0])
        connection.records[0]["user_agent"] = "SavedBrowser/1.0"
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        self.assertEqual(connection.records[0]["user_agent"], "SavedBrowser/1.0")

    async def test_upgrade_rejects_non_mysql_before_changing_schema(self):
        schema = importlib.import_module("app.core.schema")
        connection = SimpleNamespace(capabilities=SimpleNamespace(dialect="sqlite"))
        with (
            patch.object(schema, "connections", SimpleNamespace(get=Mock(return_value=connection))),
            patch.object(schema.Tortoise, "generate_schemas", new_callable=AsyncMock) as generate,
        ):
            with self.assertRaisesRegex(RuntimeError, "MySQL"):
                await schema.upgrade_site_content_schema()
        generate.assert_not_awaited()

    async def test_upgrade_propagates_failure_instead_of_reporting_success(self):
        connection = MySQLMetadata()
        connection.execute_script = AsyncMock(side_effect=RuntimeError("no ALTER privilege"))
        with self.assertRaisesRegex(RuntimeError, "no ALTER privilege"):
            await self.upgrade_with(connection)
