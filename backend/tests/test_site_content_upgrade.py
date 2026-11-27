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
        self.article_deleted_at = upgraded
        self.article_deleted_at_index = upgraded
        self.weight = upgraded
        self.columns = {"author_id": {"COLUMN_NAME": "author_id", "IS_NULLABLE": "YES" if upgraded else "NO", "COLUMN_TYPE": "int"}}
        self.todo_columns = {name: {"COLUMN_NAME": name} for name in (
            "reminder_email", "reminder_repeat", "reminder_timezone", "reminder_next_run_at", "reminder_cron",
        )} if upgraded else {}
        self.todo_records = []
        self.about_columns = {name: {"COLUMN_NAME": name} for name in (
            "github_url", "email", "x_url", "facebook_url", "instagram_url", "featured_article_ids", "current_projects",
        )} if upgraded else {}
        self.about_records = [{"id": 1, "title": "Author", "content": "Existing biography"}]
        if upgraded:
            self.columns.update({name: {"COLUMN_NAME": name, "IS_NULLABLE": "NO", "COLUMN_TYPE": "varchar"} for name in ("nickname", "email", "ip_address", "location", "is_rejected", "user_agent")})
        self.foreign_keys = [{"CONSTRAINT_NAME": "legacy_comment_author_fk", "REFERENCED_TABLE_NAME": "users", "REFERENCED_COLUMN_NAME": "id", "DELETE_RULE": "SET NULL" if upgraded else "CASCADE", "UPDATE_RULE": "RESTRICT"}]
        self.records = [{"id": 7, "author_id": 13, "content": "Existing comment"}]
        self.scripts = []
        self.backfills = []

    async def execute_query(self, sql):
        if not sql.startswith("UPDATE `todos`"):
            raise AssertionError(f"Unexpected data query: {sql}")
        self.backfills.append(sql)
        for record in self.todo_records:
            if (record.get("reminder_next_run_at") is None and record["reminder_enabled"]
                    and not record["is_completed"] and record["reminder_status"] in {"pending", "sending", "failed"}
                    and record["due_at"] is not None):
                record["reminder_next_run_at"] = record["due_at"]
        return (0, [])

    async def execute_query_dict(self, sql):
        if "TABLE_NAME = 'about_pages'" in sql:
            return list(self.about_columns.values())
        if "TABLE_NAME = 'articles'" in sql:
            exists = self.article_deleted_at_index if "STATISTICS" in sql else self.article_deleted_at
            return [{"COLUMN_NAME": "deleted_at"}] if exists else []
        if "TABLE_NAME = 'categories'" in sql:
            return [{"COLUMN_NAME": "weight"}] if self.weight else []
        if "KEY_COLUMN_USAGE" in sql:
            return self.foreign_keys
        if "TABLE_NAME = 'comments'" in sql:
            return list(self.columns.values())
        if "TABLE_NAME = 'todos'" in sql:
            return list(self.todo_columns.values())
        raise AssertionError(f"Unexpected metadata query: {sql}")

    async def execute_script(self, sql):
        self.scripts.append(sql)
        if "`about_pages`" in sql:
            for name in ("github_url", "email", "x_url", "facebook_url", "instagram_url"):
                if f"ADD COLUMN `{name}`" in sql:
                    self.about_columns[name] = {"COLUMN_NAME": name}
                    for record in self.about_records:
                        record[name] = ""
            for name in ("featured_article_ids", "current_projects"):
                if f"ADD COLUMN `{name}`" in sql:
                    self.about_columns[name] = {"COLUMN_NAME": name}
                    for record in self.about_records:
                        record[name] = None
            return
        if "`articles`" in sql:
            if "ADD COLUMN" in sql:
                self.article_deleted_at = True
            if "ADD INDEX" in sql:
                self.article_deleted_at_index = True
            return
        if "`categories`" in sql:
            self.weight = True
            return
        if "`todos`" in sql:
            for name in ("reminder_email", "reminder_repeat", "reminder_timezone", "reminder_next_run_at", "reminder_cron"):
                if f"ADD COLUMN `{name}`" in sql:
                    self.todo_columns[name] = {"COLUMN_NAME": name}
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
    async def test_discovery_upgrade_preserves_content_and_is_idempotent(self):
        connection = MySQLMetadata(upgraded=True)
        del connection.about_columns["featured_article_ids"]
        del connection.about_columns["current_projects"]
        original = [dict(row) for row in connection.about_records]
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        for name in ("featured_article_ids", "current_projects"):
            self.assertIn(f"ADD COLUMN `{name}` JSON NULL", connection.scripts[0])
        self.assertEqual(connection.about_records[0]["content"], original[0]["content"])
        connection.about_records[0]["current_projects"] = [{"name": "Saved"}]
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        self.assertEqual(connection.about_records[0]["current_projects"], [{"name": "Saved"}])

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
        self.assertEqual(len(connection.scripts), 5)
        comment_sql = connection.scripts[1]
        self.assertIn("DROP FOREIGN KEY `legacy_comment_author_fk`", comment_sql)
        self.assertNotIn("ADD CONSTRAINT `legacy_comment_author_fk`", comment_sql)
        self.assertRegex(comment_sql, r"ADD CONSTRAINT `fk_comments_guest_[0-9a-f]{16}`")
        self.assertIn("ON DELETE SET NULL ON UPDATE RESTRICT", comment_sql)
        self.assertIn("ADD COLUMN `reminder_email` VARCHAR(254) NOT NULL DEFAULT ''", connection.scripts[2])
        for unsafe in ("DROP TABLE", "DELETE FROM", "TRUNCATE", "UPDATE `"):
            self.assertNotIn(unsafe, comment_sql.upper())
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 5)

    async def test_about_contacts_upgrade_preserves_biography_and_is_idempotent(self):
        connection = MySQLMetadata(upgraded=True)
        connection.about_columns = {"github_url": {"COLUMN_NAME": "github_url"}}
        connection.about_records[0]["github_url"] = "https://github.com/saved"
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        sql = connection.scripts[0]
        self.assertIn("ALTER TABLE `about_pages`", sql)
        self.assertIn("ADD COLUMN `email` VARCHAR(254) NOT NULL DEFAULT ''", sql)
        self.assertNotIn("ADD COLUMN `github_url`", sql)
        for name in ("x_url", "facebook_url", "instagram_url"):
            self.assertIn(f"ADD COLUMN `{name}` VARCHAR(512) NOT NULL DEFAULT ''", sql)
        self.assertEqual(connection.about_records, [{
            "id": 1, "title": "Author", "content": "Existing biography",
            "github_url": "https://github.com/saved", "email": "", "x_url": "",
            "facebook_url": "", "instagram_url": "", "featured_article_ids": None, "current_projects": None,
        }])
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)

    async def test_partially_upgraded_table_only_receives_missing_columns(self):
        connection = MySQLMetadata(upgraded=True)
        del connection.columns["location"]
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        self.assertIn("ADD COLUMN `location`", connection.scripts[0])
        self.assertNotIn("DROP FOREIGN KEY", connection.scripts[0])
        self.assertNotIn("MODIFY COLUMN", connection.scripts[0])

    async def test_reminder_upgrade_adds_calendar_fields_and_backfills_only_active_occurrences(self):
        connection = MySQLMetadata(upgraded=True)
        for name in ("reminder_repeat", "reminder_timezone", "reminder_next_run_at"):
            del connection.todo_columns[name]
        date = "2026-11-17 08:00:00"
        for state in ("pending", "sending", "failed", "sent", "disabled"):
            connection.todo_records.append({
                "reminder_enabled": state != "disabled", "is_completed": False,
                "reminder_status": state, "due_at": date,
            })
        connection.todo_records.append({
            "reminder_enabled": True, "is_completed": True, "reminder_status": "pending", "due_at": date,
        })
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        self.assertIn("ADD COLUMN `reminder_repeat` VARCHAR(16) NOT NULL DEFAULT 'once'", connection.scripts[0])
        self.assertIn("ADD COLUMN `reminder_timezone` VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai'", connection.scripts[0])
        self.assertIn("ADD COLUMN `reminder_next_run_at` DATETIME(6) NULL", connection.scripts[0])
        self.assertNotIn("ADD COLUMN `reminder_email`", connection.scripts[0])
        self.assertEqual([row.get("reminder_next_run_at") for row in connection.todo_records], [date, date, date, None, None, None])
        connection.todo_records[0]["reminder_next_run_at"] = "2026-11-18 08:00:00"
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        self.assertEqual(connection.todo_records[0]["reminder_next_run_at"], "2026-11-18 08:00:00")

    async def test_reminder_backfill_recovers_upgrade_interrupted_after_columns_were_added(self):
        connection = MySQLMetadata(upgraded=True)
        connection.todo_records = [{
            "reminder_enabled": True, "is_completed": False, "reminder_status": "pending",
            "due_at": "2026-11-17 08:00:00", "reminder_next_run_at": None,
        }]
        await self.upgrade_with(connection)
        self.assertEqual(connection.scripts, [])
        self.assertEqual(connection.todo_records[0]["reminder_next_run_at"], "2026-11-17 08:00:00")

    async def test_cron_upgrade_adds_only_expression_and_preserves_existing_schedules(self):
        connection = MySQLMetadata(upgraded=True)
        del connection.todo_columns["reminder_cron"]
        connection.todo_records = [{
            "reminder_enabled": True, "is_completed": False, "reminder_status": "pending",
            "due_at": "2026-11-01 09:00:00", "reminder_repeat": "monthly",
            "reminder_next_run_at": "2026-12-01 09:00:00",
        }]
        original = [dict(row) for row in connection.todo_records]
        await self.upgrade_with(connection)
        self.assertIn("reminder_cron", connection.todo_columns)
        self.assertEqual(connection.todo_records, original)
        self.assertEqual(len(connection.scripts), 1)
        self.assertIn("ADD COLUMN `reminder_cron` VARCHAR(128) NOT NULL DEFAULT ''", connection.scripts[0])
        self.assertNotIn("MODIFY COLUMN", connection.scripts[0])
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        self.assertEqual(connection.todo_records, original)

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

    async def test_deleted_at_upgrade_preserves_data_and_adds_index_idempotently(self):
        connection = MySQLMetadata(upgraded=True)
        connection.article_deleted_at = False
        connection.article_deleted_at_index = False
        await self.upgrade_with(connection)
        self.assertTrue(connection.article_deleted_at)
        self.assertTrue(connection.article_deleted_at_index)
        self.assertEqual(len(connection.scripts), 1)
        self.assertIn("ADD COLUMN `deleted_at` DATETIME(6) NULL", connection.scripts[0])
        self.assertIn("ADD INDEX", connection.scripts[0])
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)

    async def test_interrupted_upgrade_adds_missing_index_only(self):
        connection = MySQLMetadata(upgraded=True)
        connection.article_deleted_at_index = False
        await self.upgrade_with(connection)
        self.assertEqual(len(connection.scripts), 1)
        self.assertNotIn("ADD COLUMN", connection.scripts[0])
        self.assertIn("ADD INDEX", connection.scripts[0])
