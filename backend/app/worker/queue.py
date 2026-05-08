"""Job queue glue — enqueue pipeline runs on RQ when Redis is reachable,
fall back to FastAPI BackgroundTasks otherwise.

The fallback keeps local development frictionless: a fresh checkout works
with `uvicorn app.main:app --reload` and no Redis. Enable the queue by
setting PDVE_QUEUE_ENABLED=true and starting `python -m app.worker.run`.
"""

from __future__ import annotations

from typing import Callable

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)

# Lazy/cached connection — building one is non-trivial, and the failure path
# (Redis down) should not be re-tried on every enqueue.
_redis_conn = None
_redis_probed = False
_redis_ok = False


def _get_redis():
    """Return a connected Redis client or None. Caches the result so we don't
    hammer a downed Redis on every request."""
    global _redis_conn, _redis_probed, _redis_ok
    if _redis_probed:
        return _redis_conn if _redis_ok else None

    _redis_probed = True
    try:
        import redis  # local import — keeps the dep optional at module-load time
        conn = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)
        conn.ping()
        _redis_conn = conn
        _redis_ok = True
        log.info("Queue: connected to Redis at %s", settings.redis_url)
        return conn
    except Exception as e:
        log.warning(
            "Queue: Redis unreachable at %s (%s) — falling back to BackgroundTasks",
            settings.redis_url, e,
        )
        return None


def reset_connection_cache() -> None:
    """Clear the cached Redis probe — useful in tests and after config changes."""
    global _redis_conn, _redis_probed, _redis_ok
    _redis_conn = None
    _redis_probed = False
    _redis_ok = False


def queue_available() -> bool:
    """True when the queue is enabled in settings AND Redis is reachable."""
    if not settings.queue_enabled:
        return False
    return _get_redis() is not None


def enqueue(target: Callable, *args, fallback_add_task: Callable | None = None,
            **kwargs) -> str:
    """Enqueue `target(*args, **kwargs)` for execution.

    If RQ is available, returns the RQ job id. Otherwise schedules via
    `fallback_add_task(target, *args, **kwargs)` (typically FastAPI's
    BackgroundTasks.add_task) and returns "inline".

    Falling back rather than raising is deliberate: the user experience must
    not break when Redis isn't deployed yet.
    """
    if queue_available():
        try:
            from rq import Queue
            q = Queue(settings.queue_name, connection=_get_redis())
            rq_job = q.enqueue(target, *args, job_timeout=settings.queue_job_timeout, **kwargs)
            log.info("Queue: enqueued %s as RQ job %s", target.__name__, rq_job.id)
            return rq_job.id
        except Exception as e:
            log.warning("Queue: enqueue failed (%s); falling back inline", e)

    if fallback_add_task is None:
        # Ultimate fallback: run inline. Used only by tests or non-FastAPI callers.
        target(*args, **kwargs)
        return "inline"

    fallback_add_task(target, *args, **kwargs)
    return "inline"
