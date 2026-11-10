"""Upgrade control flow without connecting to an actual MySQL database."""
import importlib
import importlib.util
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

os.environ["PYTHON_DOTENV_DISABLED"] = "1"


class SiteContentUpgradeTests(unittest.IsolatedAsyncioTestCase):
    def upgrade_module(self):
        path = "app.core.schema"
        self.assertIsNotNone(importlib.util.find_spec(path), "Site content upgrade helper is missing")
        return importlib.import_module(path)

    async def test_upgrade_adds_weight_once_and_keeps_existing_weight_on_rerun(self):
        schema = self.upgrade_module()
        connection = SimpleNamespace(
            capabilities=SimpleNamespace(dialect="mysql"),
            execute_query_dict=AsyncMock(side_effect=[[], [{"COLUMN_NAME": "weight"}]]),
            execute_script=AsyncMock(),
        )
        with (
            patch.object(schema, "connections", SimpleNamespace(get=Mock(return_value=connection))),
            patch.object(schema.Tortoise, "generate_schemas", new_callable=AsyncMock) as generate,
        ):
            await schema.upgrade_site_content_schema()
            await schema.upgrade_site_content_schema()
        self.assertEqual(generate.await_count, 2)
        for call in generate.await_args_list:
            self.assertEqual(call.kwargs, {"safe": True})
        self.assertEqual(connection.execute_script.await_count, 1)
        sql = connection.execute_script.await_args.args[0].upper()
        self.assertIn("ALTER TABLE `CATEGORIES` ADD COLUMN `WEIGHT` INT NOT NULL DEFAULT 0", sql)
        self.assertNotIn("DROP", sql)
        self.assertNotIn("UPDATE", sql)

    async def test_upgrade_rejects_non_mysql_before_changing_schema(self):
        schema = self.upgrade_module()
        connection = SimpleNamespace(capabilities=SimpleNamespace(dialect="sqlite"))
        with (
            patch.object(schema, "connections", SimpleNamespace(get=Mock(return_value=connection))),
            patch.object(schema.Tortoise, "generate_schemas", new_callable=AsyncMock) as generate,
        ):
            with self.assertRaisesRegex(RuntimeError, "MySQL"):
                await schema.upgrade_site_content_schema()
        generate.assert_not_awaited()

    async def test_upgrade_propagates_failure_instead_of_reporting_success(self):
        schema = self.upgrade_module()
        connection = SimpleNamespace(
            capabilities=SimpleNamespace(dialect="mysql"),
            execute_query_dict=AsyncMock(return_value=[]),
            execute_script=AsyncMock(side_effect=RuntimeError("no ALTER privilege")),
        )
        with (
            patch.object(schema, "connections", SimpleNamespace(get=Mock(return_value=connection))),
            patch.object(schema.Tortoise, "generate_schemas", new_callable=AsyncMock),
        ):
            with self.assertRaisesRegex(RuntimeError, "no ALTER privilege"):
                await schema.upgrade_site_content_schema()


if __name__ == "__main__":
    unittest.main()
