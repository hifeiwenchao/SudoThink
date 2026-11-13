"""Per-Celery-worker event loop and database/cache resource lifecycle."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, TypeVar


logger = logging.getLogger(__name__)
ResultT = TypeVar("ResultT")


class WorkerRuntime:
    """Own one event loop and its async ORM/Redis resources per worker process."""

    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.redis: Any = None
        self._tortoise_context: Any = None
        self._owns_tortoise = False

    async def _initialize_async(self) -> None:
        # Keep heavy imports inside the worker process. Importing the Celery
        # entrypoint must remain safe for discovery and beat processes.
        from redis.asyncio import from_url
        from tortoise import Tortoise

        from app.core.config import TORTOISE_ORM, settings

        if not Tortoise.is_inited():
            self._tortoise_context = await Tortoise.init(config=TORTOISE_ORM)
            self._owns_tortoise = True
        self.redis = from_url(settings.REDIS_URL, decode_responses=True)

    async def _close_async(self) -> None:
        redis, self.redis = self.redis, None
        if redis is not None:
            await redis.aclose()
        context, self._tortoise_context = self._tortoise_context, None
        if self._owns_tortoise and context is not None:
            # Tortoise 1.x stores its context in a ContextVar. Re-enter the
            # worker context for cleanup because each run_until_complete call
            # creates a fresh task context.
            with context:
                await context.close_connections()
                context._apps = None
                context._inited = False
        self._owns_tortoise = False

    def initialize(self) -> None:
        """Initialize resources once in the current worker process."""
        if self.loop is not None and not self.loop.is_closed():
            return
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._initialize_async())
        except BaseException:
            self.loop.close()
            self.loop = None
            raise

    def run(self, operation: Callable[[Any], Awaitable[ResultT]]) -> ResultT:
        """Run one task coroutine on the worker's long-lived event loop."""
        self.initialize()
        if self.loop is None or self.redis is None:
            raise RuntimeError("Celery worker resources are not initialized")
        async def execute() -> ResultT:
            if self._tortoise_context is None:
                return await operation(self.redis)
            with self._tortoise_context:
                return await operation(self.redis)

        return self.loop.run_until_complete(execute())

    def shutdown(self) -> None:
        """Close worker resources once, tolerating repeated shutdown signals."""
        if self.loop is None:
            return
        loop, self.loop = self.loop, None
        try:
            if not loop.is_closed():
                loop.run_until_complete(self._close_async())
        finally:
            if not loop.is_closed():
                loop.close()
            try:
                current_loop = asyncio.get_event_loop()
            except RuntimeError:
                current_loop = None
            if current_loop is loop:
                asyncio.set_event_loop(None)


_runtime = WorkerRuntime()


def get_worker_runtime() -> WorkerRuntime:
    return _runtime


def initialize_worker_resources() -> None:
    get_worker_runtime().initialize()


def shutdown_worker_resources() -> None:
    try:
        get_worker_runtime().shutdown()
    except Exception:
        logger.exception("Failed to close Celery worker resources")


def run_with_worker_resources(operation: Callable[[Any], Awaitable[ResultT]]) -> ResultT:
    """Run an async task using lifecycle resources, with solo/eager fallback."""
    return get_worker_runtime().run(operation)
