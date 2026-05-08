"""Worker entry point: `python -m app.worker.run`.

Connects to Redis and runs an RQ worker that drains the configured queue.
This process is independent of the FastAPI server; you can run multiple
workers for parallelism. Each worker handles one job at a time.

Example:
    PDVE_QUEUE_ENABLED=true python -m app.worker.run
"""

from __future__ import annotations

import sys

import redis
from rq import Queue, Worker

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)


def main() -> int:
    log.info("Worker starting: redis=%s queue=%s", settings.redis_url, settings.queue_name)
    try:
        conn = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=5)
        conn.ping()
    except Exception as e:
        log.error("Worker: cannot reach Redis at %s: %s", settings.redis_url, e)
        return 2

    queue = Queue(settings.queue_name, connection=conn)
    worker = Worker([queue], connection=conn)
    worker.work(with_scheduler=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
