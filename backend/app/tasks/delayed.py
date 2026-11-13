"""延迟一次任务的同步执行包装器；发现任务时不建立 Redis/ORM 资源。"""
from __future__ import annotations

from uuid import uuid4

from app.celery_app import celery_app

_CLAIM_EXECUTION = """
local state = redis.call('GET', KEYS[1])
if state == 'done' then return -2 end
if state ~= 'pending' then return -1 end
if not redis.call('SET', KEYS[2], ARGV[1], 'NX', 'EX', ARGV[2]) then
    return 0
end
return 1
"""
_FINISH_EXECUTION = """
if redis.call('GET', KEYS[2]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], 'done', 'EX', 86400)
if redis.call('GET', KEYS[3]) == ARGV[2] then redis.call('DEL', KEYS[3]) end
redis.call('DEL', KEYS[2])
return 1
"""
_RELEASE_LOCK = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""
_ABANDON_WINDOW = """
if redis.call('EXISTS', KEYS[3]) == 0 and redis.call('GET', KEYS[1]) == ARGV[1] then
    redis.call('DEL', KEYS[1], KEYS[2])
    return 1
end
return 0
"""


def _redis_client():
    from redis import Redis
    from app.core.config import settings
    return Redis.from_url(
        settings.REDIS_URL, decode_responses=True, socket_connect_timeout=5, socket_timeout=5,
    )


class _ExecutionLocked(Exception):
    def __init__(self, delay):
        self.delay = delay


@celery_app.task(
    name="app.tasks.delayed.execute_once", bind=True, max_retries=5,
    acks_late=True, acks_on_timeout=False, reject_on_worker_lost=True,
)
def execute_once(
    self, token, window_key, task_name, args=(), kwargs=None,
    execution_timeout=300, failure_count=0,
):
    """执行首次参数；等待、执行和重试期间持续保留同一业务窗口。"""
    client = None
    owner = uuid4().hex
    state_key = "delayed:job:" + token
    lock_key = "delayed:lock:" + token
    try:
        client = _redis_client()
        claimed = client.eval(_CLAIM_EXECUTION, 2, state_key, lock_key, owner, execution_timeout + 60)
        if claimed == -2:
            return {"status": "duplicate"}
        if claimed == -1:
            return {"status": "expired"}
        if claimed == 0:
            # Wait out the lease rather than exhausting retries while another worker
            # still runs, or before a crashed worker's lease can expire.
            raise _ExecutionLocked(max(5, client.ttl(lock_key) + 1))
        # No event loop is running here: targets may own asyncio.run/ORM lifecycles.
        celery_app.tasks[task_name].run(*args, **(kwargs or {}))
        completed = client.eval(_FINISH_EXECUTION, 3, state_key, lock_key, window_key, owner, token)
        if not completed:
            raise RuntimeError("delayed task execution lease expired")
        return {"status": "completed"}
    except _ExecutionLocked as exc:
        raise self.retry(
            exc=RuntimeError("delayed task is already executing"), countdown=exc.delay,
            kwargs={
                "token": token, "window_key": window_key, "task_name": task_name,
                "args": args, "kwargs": kwargs, "execution_timeout": execution_timeout,
                "failure_count": failure_count,
            },
            # Lock contention is a delivery condition, independent of the
            # target's bounded failure budget; allow it to outlive a lease.
            max_retries=2**31 - 1,
        ) from None
    except Exception:
        if client is not None:
            try:
                client.eval(_RELEASE_LOCK, 1, lock_key, owner)
                if failure_count >= self.max_retries:
                    client.eval(_ABANDON_WINDOW, 3, window_key, state_key, lock_key, token)
            except Exception:
                pass
        if failure_count >= self.max_retries:
            raise RuntimeError("delayed task execution failed") from None
        # Avoid copying task arguments, connection URLs or exception secrets into retry logs.
        raise self.retry(
            exc=RuntimeError("delayed task execution failed"),
            countdown=min(60, 5 * (2 ** min(failure_count, 4))),
            kwargs={
                "token": token, "window_key": window_key, "task_name": task_name,
                "args": args, "kwargs": kwargs, "execution_timeout": execution_timeout,
                "failure_count": failure_count + 1,
            },
            # The explicit failure_count controls the target budget; Celery's
            # delivery retry counter also includes lock/redelivery attempts.
            max_retries=2**31 - 1,
        ) from None
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
