"""Convenience entry-point for the RQ pipeline worker.

Run from the project root (where ``backend/`` lives):

    cd backend
    PDVE_QUEUE_ENABLED=true python ../worker/worker.py

Or, equivalently, using the module flag:

    cd backend
    PDVE_QUEUE_ENABLED=true python -m app.worker.run

Both forms start an RQ worker that drains the configured queue (default:
``pipeline``) against the Redis instance at PDVE_REDIS_URL (default:
``redis://localhost:6379/0``).

If Redis is not reachable the worker exits with code 2 and logs the error.

Production tip
--------------
Use a process supervisor (systemd, supervisord, Docker restart policy) to
keep the worker alive. Multiple worker processes may run in parallel — each
one handles one pipeline job at a time, so horizontal scaling is trivially:

    for _ in range(NUM_WORKERS):
        start_process("python worker/worker.py")
"""

import sys
from pathlib import Path

# Ensure the backend package is importable when this script is invoked
# directly (i.e. ``python worker/worker.py`` from the repo root).
# ``backend/`` must be on sys.path so ``import app.*`` works.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.worker.run import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
