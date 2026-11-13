"""首次触发后固定延迟一次；等待、执行及重试期间的重复触发直接丢弃。"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from uuid import uuid4

from app.celery_app import celery_app

_PENDING_GRACE_SECONDS = 7 * 86400
_WRAPPER_TASK = "app.tasks.delayed.execute_once"
_CLAIM_WINDOW = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 0
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
redis.call('SET', KEYS[2], 'pending', 'EX', ARGV[2])
return 1
"""
_CANCEL_WINDOW = """
if redis.call('GET', KEYS[1]) == ARGV[1] and redis.call('EXISTS', KEYS[3]) == 0 then
    redis.call('DEL', KEYS[1], KEYS[2])
    return 1
end
return 0
"""
_PUBLISH_OPERATIONS: set[asyncio.Task] = set()
_SHIELD_OPERATIONS: set[asyncio.Future] = set()


@dataclass
class _PublishFailure:
    error: Exception


def _consume_publish_operation(operation: asyncio.Task) -> None:
    _PUBLISH_OPERATIONS.discard(operation)


def _consume_shield_result(shielded: asyncio.Future) -> None:
    # When the request is cancelled, shield itself becomes cancelled while the
    # owned operation continues. Retrieve a later publish exception as well as
    # the inner task's exception to avoid asyncio's unhandled-future warning.
    try:
        shielded.exception()
    except BaseException:
        pass
    finally:
        _SHIELD_OPERATIONS.discard(shielded)


def _publish(payload, delay_seconds, execution_timeout):
    # Use a bounded, dedicated connection rather than waiting for a pooled
    # producer or retrying a broken broker while an HTTP request awaits us.
    with celery_app.connection_for_write(
        connect_timeout=5, transport_options={"read_timeout": 5, "write_timeout": 5},
    ) as connection:
        celery_app.send_task(
            _WRAPPER_TASK, kwargs=payload, connection=connection, retry=False,
            timeout=5, confirm_timeout=5, countdown=delay_seconds,
            time_limit=execution_timeout, soft_time_limit=max(1, execution_timeout - 10),
        )


def _validated_payload(task_name, dedupe_key, delay_seconds, args, kwargs, execution_timeout):
    if (not isinstance(task_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]{0,254}", task_name)):
        raise ValueError("task_name must be a valid task name")
    if not isinstance(dedupe_key, str) or not 1 <= len(dedupe_key) <= 1024:
        raise ValueError("dedupe_key must contain 1 to 1024 characters")
    if type(delay_seconds) is not int or not 1 <= delay_seconds <= 86400:
        raise ValueError("delay_seconds must be an integer from 1 to 86400")
    if type(execution_timeout) is not int or not 30 <= execution_timeout <= 86400:
        raise ValueError("execution_timeout must be an integer from 30 to 86400")
    if not isinstance(args, (list, tuple)):
        raise ValueError("args must be a list or tuple")
    if kwargs is not None and (not isinstance(kwargs, dict) or not all(isinstance(key, str) for key in kwargs)):
        raise ValueError("kwargs must be an object with string keys")
    try:
        # Snapshot before claiming: later mutation must not alter the first call's payload.
        payload = json.loads(json.dumps([args, kwargs or {}], allow_nan=False))
        digest = hashlib.sha256((task_name + "\0" + dedupe_key).encode("utf-8")).hexdigest()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError("task arguments and business key must be valid JSON/UTF-8 values") from None
    return payload[0], payload[1], "delayed:window:" + digest


async def schedule_task_once(
    task_name: str,
    dedupe_key: str,
    delay_seconds: int,
    args: list | tuple = (),
    kwargs: dict | None = None,
    *,
    redis_client=None,
    execution_timeout: int = 300,
) -> bool:
    """首次触发返回 True，现有窗口返回 False；不延长窗口、不替换参数。

    任务成功或耗尽重试后释放窗口。调用目标必须为同步、幂等的 Celery
    任务；任务失败和 worker 中断可能造成重试，不提供恰好一次副作用保证。
    Redis 或消息投递失败向调用方传播；投递失败会撤销尚未执行的本次窗口。
    """
    args, kwargs, window_key = _validated_payload(
        task_name, dedupe_key, delay_seconds, args, kwargs, execution_timeout,
    )
    if redis_client is None:
        from app.core.redis import get_redis
        redis_client = get_redis()
    token = uuid4().hex
    state_key = "delayed:job:" + token
    lock_key = "delayed:lock:" + token

    async def _claim_and_publish() -> bool | _PublishFailure:
        try:
            claimed = await redis_client.eval(
                _CLAIM_WINDOW, 2, window_key, state_key, token,
                delay_seconds + _PENDING_GRACE_SECONDS,
            )
            if not claimed:
                return False
            try:
                await asyncio.to_thread(
                    _publish,
                    {
                        "token": token, "window_key": window_key, "task_name": task_name,
                        "args": args, "kwargs": kwargs, "execution_timeout": execution_timeout,
                    },
                    delay_seconds,
                    execution_timeout,
                )
            except Exception as error:
                try:
                    # A broker error can be ambiguous: do not cancel a job already executing.
                    await redis_client.eval(_CANCEL_WINDOW, 3, window_key, state_key, lock_key, token)
                except Exception:
                    # Preserve the broker error; Redis TTL remains the fallback for cleanup.
                    pass
                return _PublishFailure(error)
            return True
        except Exception as error:
            # Return failures as values so a cancelled caller cannot leave an
            # exception-bearing shielded task for the event loop to report.
            return _PublishFailure(error)

    # Shield the operation so cancellation of the HTTP handler cannot strand a
    # seven-day gate while a broker publish is still in flight. Keep a strong
    # reference and retrieve its eventual exception after the caller is gone.
    operation = asyncio.create_task(_claim_and_publish())
    _PUBLISH_OPERATIONS.add(operation)
    operation.add_done_callback(_consume_publish_operation)
    shielded = asyncio.shield(operation)
    _SHIELD_OPERATIONS.add(shielded)
    shielded.add_done_callback(_consume_shield_result)
    result = await shielded
    if isinstance(result, _PublishFailure):
        raise result.error
    return result
