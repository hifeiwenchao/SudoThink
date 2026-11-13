"""Celery worker process resource lifecycle tests."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from app.celery_runtime import WorkerRuntime


class WorkerRuntimeTests(unittest.TestCase):
    def test_run_reuses_one_loop_and_shutdown_closes_resources_once(self):
        runtime = WorkerRuntime()
        initialized = 0
        closed = 0

        async def initialize():
            nonlocal initialized
            initialized += 1
            runtime.redis = object()

        async def close():
            nonlocal closed
            closed += 1

        with patch.object(runtime, "_initialize_async", new=initialize), patch.object(
            runtime, "_close_async", new=close
        ):
            self.assertEqual(runtime.run(lambda _: asyncio.sleep(0, result="first")), "first")
            loop = runtime.loop
            self.assertEqual(runtime.run(lambda _: asyncio.sleep(0, result="second")), "second")
            self.assertIs(runtime.loop, loop)
            self.assertEqual(initialized, 1)
            runtime.shutdown()
            runtime.shutdown()

        self.assertEqual(closed, 1)
        self.assertIsNone(runtime.loop)

    def test_worker_lifecycle_hooks_delegate_to_the_process_runtime(self):
        import app.celery_app as celery_module

        with patch.object(celery_module, "initialize_worker_resources") as initialize, patch.object(
            celery_module, "shutdown_worker_resources"
        ) as shutdown:
            celery_module.initialize_worker_process()
            celery_module.shutdown_worker_process()

        initialize.assert_called_once_with()
        shutdown.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
