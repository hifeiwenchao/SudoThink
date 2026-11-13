"""Reusable delayed-once scheduling; live Redis tests use an explicit QA endpoint."""
import asyncio
import importlib
import importlib.util
import os
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

from celery.exceptions import Retry
from redis import Redis
from redis.asyncio import Redis as AsyncRedis

REDIS_URL = os.environ.get("SUDOTHINK_TEST_REDIS_URL")


def feature(test, name):
    test.assertIsNotNone(importlib.util.find_spec(name), f"Missing delayed-once feature: {name}")
    return importlib.import_module(name)


class DelayedValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_parameters_are_rejected_before_any_external_effect(self):
        scheduler = feature(self, "app.core.delayed_tasks")

        class NoRedis:
            async def eval(self, *_):
                raise AssertionError("invalid input must not reach Redis")

        valid = {"task_name": "app.tasks.example", "dedupe_key": "business-key", "delay_seconds": 120}
        for invalid in (
            {"task_name": ""}, {"task_name": "invalid task"}, {"task_name": None},
            {"dedupe_key": ""}, {"dedupe_key": 1},
            {"delay_seconds": 0}, {"delay_seconds": True}, {"delay_seconds": 86401},
            {"execution_timeout": 29}, {"execution_timeout": True}, {"execution_timeout": 86401},
            {"args": "not-list"}, {"args": [object()]}, {"kwargs": []},
            {"kwargs": {1: "invalid keyword"}}, {"kwargs": {"value": float("nan")}},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                await scheduler.schedule_task_once(**{**valid, **invalid}, redis_client=NoRedis())


@unittest.skipUnless(REDIS_URL, "set SUDOTHINK_TEST_REDIS_URL for isolated live Redis tests")
class DelayedTaskRedisTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.scheduler = feature(self, "app.core.delayed_tasks")
        self.wrapper = feature(self, "app.tasks.delayed")
        self.client = AsyncRedis.from_url(REDIS_URL, decode_responses=True)
        await self.client.ping()
        self.sync_client = Redis.from_url(REDIS_URL, decode_responses=True)
        self.published = []
        self.called = []
        self.unique = uuid4().hex
        self.target_name = "test.delayed." + self.unique
        self.keys = set()

        def publish(name, *, kwargs, **options):
            # Real sync broker I/O must be moved off the Sanic event loop.
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                raise AssertionError("broker publishing ran on the event loop")
            self.published.append({"name": name, "kwargs": kwargs, **options})
            self.track(kwargs)

        self.publish = publish
        self.publish_patch = patch.object(self.scheduler.celery_app, "send_task", side_effect=publish)
        self.publish_patch.start()
        self.redis_patch = patch.object(self.wrapper, "_redis_client", side_effect=lambda: Redis.from_url(
            REDIS_URL, decode_responses=True,
        ))
        self.redis_patch.start()

        @self.wrapper.celery_app.task(name=self.target_name, lazy=False)
        def target(value=None, **kwargs):
            async def actual():
                self.called.append((value, kwargs))
            # This is the same lifecycle pattern used by synchronous ORM tasks.
            asyncio.run(actual())

        self.target = target

    def track(self, kwargs):
        self.keys.update((kwargs["window_key"], "delayed:job:" + kwargs["token"],
                          "delayed:lock:" + kwargs["token"]))

    async def asyncTearDown(self):
        self.publish_patch.stop()
        self.redis_patch.stop()
        self.wrapper.celery_app.tasks.pop(self.target_name, None)
        if self.keys:
            await self.client.delete(*self.keys)
        await self.client.aclose()
        self.sync_client.close()

    async def schedule(self, key="article-1", **kwargs):
        return await self.scheduler.schedule_task_once(
            self.target_name, self.unique + key, 120, redis_client=self.client, **kwargs,
        )

    def invoke(self, payload, retries=0):
        task = self.wrapper.execute_once
        task.push_request(id=uuid4().hex, retries=retries, called_directly=False, is_eager=True, kwargs=payload)
        try:
            return task.run(**payload)
        finally:
            task.pop_request()

    async def test_concurrent_triggers_publish_one_fixed_window_with_first_payload(self):
        self.assertTrue(await self.schedule(args=["first"], kwargs={"version": 1}))
        first = self.published[0]
        await self.client.expire(first["kwargs"]["window_key"], 20)
        result = await asyncio.gather(*(self.schedule(args=["later"], kwargs={"version": 2}) for _ in range(40)))
        self.assertEqual(result, [False] * 40)
        self.assertEqual(len(self.published), 1)
        self.assertLessEqual(await self.client.ttl(first["kwargs"]["window_key"]), 20)
        await asyncio.to_thread(self.invoke, first["kwargs"])
        self.assertEqual(self.called, [("first", {"version": 1})])
        self.assertEqual(first["name"], "app.tasks.delayed.execute_once")
        self.assertEqual((first["countdown"], first["time_limit"], first["soft_time_limit"]), (120, 300, 290))

    async def test_a_simultaneous_first_claim_has_one_winner_and_keys_are_independent(self):
        result = await asyncio.gather(*(self.schedule() for _ in range(40)))
        self.assertEqual(sum(result), 1)
        self.assertEqual(len(self.published), 1)
        self.assertTrue(await self.schedule(key="article-2"))
        self.assertEqual(len(self.published), 2)
        other_name = "test.other." + self.unique
        self.assertTrue(await self.scheduler.schedule_task_once(
            other_name, self.unique + "article-1", 120, redis_client=self.client,
        ))
        self.assertEqual(len({entry["kwargs"]["window_key"] for entry in self.published}), 3)
        self.assertTrue(all(self.unique not in key for key in self.keys))
        state = "delayed:job:" + self.published[0]["kwargs"]["token"]
        self.assertEqual(await self.client.get(state), "pending")
        self.assertGreater(await self.client.ttl(state), 7 * 86400)

    async def test_first_payload_is_a_json_snapshot_of_the_callers_mutable_values(self):
        arguments = ["first"]
        keywords = {"nested": {"revision": 1}}
        self.assertTrue(await self.schedule(args=arguments, kwargs=keywords))
        arguments[0] = "mutated"
        keywords["nested"]["revision"] = 2
        await asyncio.to_thread(self.invoke, self.published[0]["kwargs"])
        self.assertEqual(self.called, [("first", {"nested": {"revision": 1}})])

    async def test_publish_failure_removes_only_its_gate_and_allows_rescheduling(self):
        def fail(name, **options):
            self.publish(name, **options)
            raise RuntimeError("synthetic broker failure")

        with patch.object(self.scheduler.celery_app, "send_task", side_effect=fail):
            with self.assertRaises(RuntimeError):
                await self.schedule(args=["first"])
        first = self.published[0]["kwargs"]
        self.assertIsNone(await self.client.get(first["window_key"]))
        self.assertIsNone(await self.client.get("delayed:job:" + first["token"]))
        self.assertTrue(await self.schedule(args=["retry"]))
        await asyncio.to_thread(self.invoke, self.published[1]["kwargs"])
        self.assertEqual(self.called, [("retry", {})])

    async def test_publish_failure_does_not_delete_a_replacement_window(self):
        def replaced_then_failed(name, **options):
            self.publish(name, **options)
            self.sync_client.set(options["kwargs"]["window_key"], "replacement-owner", ex=120)
            raise RuntimeError("synthetic broker failure")

        with patch.object(self.scheduler.celery_app, "send_task", side_effect=replaced_then_failed):
            with self.assertRaises(RuntimeError):
                await self.schedule()
        first = self.published[0]["kwargs"]
        self.assertEqual(await self.client.get(first["window_key"]), "replacement-owner")

    async def test_caller_cancellation_still_rolls_back_later_publish_failure(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        payloads = []

        def blocked_publish(payload, *_):
            payloads.append(payload)
            self.track(payload)
            entered.set()
            try:
                if not release.wait(5):
                    raise AssertionError("publisher did not receive release")
                raise OSError("synthetic publish failure after request cancellation")
            finally:
                finished.set()

        with patch.object(self.scheduler, "_publish", side_effect=blocked_publish):
            request = asyncio.create_task(self.schedule())
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            request.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await request
            self.assertFalse(finished.is_set())
            release.set()
            self.assertTrue(await asyncio.to_thread(finished.wait, 5))
            # Give the background publisher its Redis rollback turn after the
            # thread ends; no synchronous wait can block the running event loop.
            for _ in range(100):
                if await self.client.get(payloads[0]["window_key"]) is None:
                    break
                await asyncio.sleep(0.01)
        self.assertIsNone(await self.client.get(payloads[0]["window_key"]))
        self.assertIsNone(await self.client.get("delayed:job:" + payloads[0]["token"]))
        self.assertTrue(await self.schedule())

    async def test_caller_cancellation_preserves_later_successful_publication(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        payloads = []

        def blocked_publish(payload, *_):
            payloads.append(payload)
            self.track(payload)
            entered.set()
            if not release.wait(5):
                raise AssertionError("publisher did not receive release")
            finished.set()

        with patch.object(self.scheduler, "_publish", side_effect=blocked_publish):
            request = asyncio.create_task(self.schedule(args=["published"]))
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            request.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await request
            release.set()
            self.assertTrue(await asyncio.to_thread(finished.wait, 5))
        self.assertEqual(await self.client.get(payloads[0]["window_key"]), payloads[0]["token"])
        self.assertFalse(await self.schedule())
        await asyncio.to_thread(self.invoke, payloads[0])
        self.assertEqual(self.called, [("published", {})])

    async def test_successful_execution_suppresses_duplicate_and_retains_done_state(self):
        await self.schedule(args=["one"])
        payload = self.published[0]["kwargs"]
        await asyncio.to_thread(self.invoke, payload)
        await asyncio.to_thread(self.invoke, payload)
        self.assertEqual(self.called, [("one", {})])
        self.assertEqual(await self.client.get("delayed:job:" + payload["token"]), "done")
        self.assertGreater(await self.client.ttl("delayed:job:" + payload["token"]), 86390)
        self.assertIsNone(await self.client.get(payload["window_key"]))
        self.assertIsNone(await self.client.get("delayed:lock:" + payload["token"]))

    async def test_success_never_deletes_a_window_owned_by_a_different_token(self):
        await self.schedule(args=["one"])
        payload = self.published[0]["kwargs"]

        def replace_window(value):
            self.sync_client.set(payload["window_key"], "replacement-owner", ex=120)
            self.called.append((value, {}))

        with patch.object(self.target, "run", side_effect=replace_window):
            await asyncio.to_thread(self.invoke, payload)
        self.assertEqual(self.called, [("one", {})])
        self.assertEqual(await self.client.get(payload["window_key"]), "replacement-owner")
        self.assertEqual(await self.client.get("delayed:job:" + payload["token"]), "done")

    async def test_running_task_drops_triggers_and_only_completion_releases_window(self):
        entered, release = threading.Event(), threading.Event()

        def target(value):
            entered.set()
            if not release.wait(5):
                raise AssertionError("target did not receive release")
            self.called.append((value, {}))

        with patch.object(self.target, "run", side_effect=target):
            await self.schedule(args=["first"])
            first = self.published[0]["kwargs"]
            running = asyncio.create_task(asyncio.to_thread(self.invoke, first))
            self.assertTrue(await asyncio.to_thread(entered.wait, 5))
            try:
                self.assertFalse(await self.schedule(args=["dropped"]))
                self.assertEqual(len(self.published), 1)
                self.assertEqual(await self.client.get(first["window_key"]), first["token"])
            finally:
                release.set()
            await running
        self.assertEqual(self.called, [("first", {})])
        self.assertIsNone(await self.client.get(first["window_key"]))
        self.assertTrue(await self.schedule(args=["second"]))
        second = self.published[1]["kwargs"]
        self.assertEqual(await self.client.get(second["window_key"]), second["token"])
        await asyncio.to_thread(self.invoke, second)
        self.assertEqual(self.called, [("first", {}), ("second", {})])

    async def test_target_failure_releases_lock_keeps_pending_state_and_retries(self):
        await self.schedule(args=["one"])
        payload = self.published[0]["kwargs"]
        with patch.object(self.target, "run", side_effect=RuntimeError("synthetic target secret")):
            with self.assertRaises(Retry) as retry:
                await asyncio.to_thread(self.invoke, payload)
        self.assertNotIn("synthetic target secret", str(retry.exception))
        self.assertEqual(await self.client.get("delayed:job:" + payload["token"]), "pending")
        self.assertIsNone(await self.client.get("delayed:lock:" + payload["token"]))
        self.assertEqual(await self.client.get(payload["window_key"]), payload["token"])
        self.assertFalse(await self.schedule(args=["dropped during retry"]))
        await asyncio.to_thread(self.invoke, payload, 1)
        self.assertEqual(self.called, [("one", {})])

    async def test_exhausted_retries_release_window_for_a_future_independent_trigger(self):
        await self.schedule(args=["failed"])
        payload = self.published[0]["kwargs"]
        payload["failure_count"] = 5
        with patch.object(self.target, "run", side_effect=RuntimeError("synthetic target failure")):
            with self.assertRaises(RuntimeError):
                await asyncio.to_thread(self.invoke, payload, 5)
        self.assertIsNone(await self.client.get(payload["window_key"]))
        self.assertIsNone(await self.client.get("delayed:lock:" + payload["token"]))
        self.assertTrue(await self.schedule(args=["independent"]))
        await asyncio.to_thread(self.invoke, self.published[1]["kwargs"])
        self.assertEqual(self.called, [("independent", {})])

    async def test_locked_delivery_retries_after_lease_without_releasing_another_owner(self):
        await self.schedule(args=["one"])
        payload = self.published[0]["kwargs"]
        lock = "delayed:lock:" + payload["token"]
        await self.client.set(lock, "other-owner", ex=360)
        with self.assertRaises(Retry) as retry:
            await asyncio.to_thread(self.invoke, payload)
        self.assertGreaterEqual(retry.exception.when, 350)
        self.assertEqual(self.called, [])
        self.assertEqual(await self.client.get(lock), "other-owner")
        self.assertEqual(await self.client.get(payload["window_key"]), payload["token"])
        await self.client.delete(lock)
        await asyncio.to_thread(self.invoke, payload, 1)
        self.assertEqual(self.called, [("one", {})])

    async def test_lock_contention_does_not_exhaust_the_actual_target_failure_budget(self):
        await self.schedule(args=["one"])
        payload = self.published[0]["kwargs"]
        lock = "delayed:lock:" + payload["token"]
        await self.client.set(lock, "crashed-owner", ex=60)
        with self.assertRaises(Retry):
            await asyncio.to_thread(self.invoke, payload, 20)
        self.assertEqual(await self.client.get(payload["window_key"]), payload["token"])
        await self.client.delete(lock)
        with patch.object(self.target, "run", side_effect=RuntimeError("first target failure")):
            with self.assertRaises(Retry) as retry:
                await asyncio.to_thread(self.invoke, payload, 21)
        self.assertEqual(retry.exception.sig.kwargs["failure_count"], 1)
        self.assertEqual(await self.client.get(payload["window_key"]), payload["token"])
        await asyncio.to_thread(self.invoke, retry.exception.sig.kwargs, 22)
        self.assertEqual(self.called, [("one", {})])

    async def test_missing_state_does_not_execute_an_expired_job(self):
        await self.schedule(args=["expired"])
        payload = self.published[0]["kwargs"]
        await self.client.delete("delayed:job:" + payload["token"])
        await asyncio.to_thread(self.invoke, payload)
        self.assertEqual(self.called, [])

    async def test_redis_outage_retries_without_running_target_or_exposing_connection_errors(self):
        await self.schedule(args=["one"])
        payload = self.published[0]["kwargs"]
        with patch.object(self.wrapper, "_redis_client", side_effect=RuntimeError("synthetic redis secret")):
            with self.assertRaises(Retry) as retry:
                await asyncio.to_thread(self.invoke, payload)
        self.assertNotIn("synthetic redis secret", str(retry.exception))
        self.assertEqual(self.called, [])
        self.assertEqual(await self.client.get(payload["window_key"]), payload["token"])


if __name__ == "__main__":
    unittest.main()
