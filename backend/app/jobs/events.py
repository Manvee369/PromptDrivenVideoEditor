"""Per-job event sidecar — high-frequency progress updates.

Why a separate file from jobs_db?
  jobs_db is cross-process safe via filelock, but acquiring that lock for every
  per-second ffmpeg progress update would create contention. Sub-stage progress
  is best-effort (slightly stale data is fine for a progress bar), so we use a
  lock-free atomic-rename file for it.

The pipeline writes coarse stage updates to jobs_db (status + progress 0-1).
The renderer writes fine-grained ffmpeg progress to progress.json. The SSE
endpoint reads both and streams a merged view to the client.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

PROGRESS_FILENAME = "progress.json"


class JobEvents:
    """High-frequency progress sidecar for one job.

    Methods are best-effort: a corrupt/missing file returns empty state
    rather than raising, because progress display must never crash the
    render pipeline.
    """

    def __init__(self, storage: StorageManager):
        self._path = storage.job_dir() / PROGRESS_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def emit(self, **fields: Any) -> None:
        """Merge `fields` into the current state and atomically rewrite."""
        state = self.read()
        state.update(fields)
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(state), encoding="utf-8")
            tmp.replace(self._path)
        except Exception as e:
            # Progress emission must not break the pipeline.
            log.debug("emit() suppressed error: %s", e)

    def read(self) -> dict[str, Any]:
        """Return current state, or {} if the file is missing/corrupt."""
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def clear(self) -> None:
        """Remove the progress file (e.g., at the start of a fresh run)."""
        try:
            self._path.unlink(missing_ok=True)
        except Exception:
            pass
