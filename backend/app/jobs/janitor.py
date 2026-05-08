"""Disk-usage janitor — clean up intermediate artifacts from old completed jobs.

Each job's directory accumulates several GB of artifacts: extracted audio,
proxy videos (`prep/`), and rendering scratch (`render/`). The user only needs
the final outputs (`outputs/`) and possibly the DSL (`dsl/`) once a job is done.

This module provides:
  - cleanup_intermediates(): per-job, deletes prep/render/signals while keeping
    raw/, dsl/, outputs/, plans/. Reversible by re-running the pipeline.
  - sweep_old_jobs(): scans jobs_db, applies cleanup to COMPLETED jobs older
    than the configured age threshold.
  - start_periodic_sweep(): runs sweep_old_jobs() on a configurable interval
    inside the FastAPI event loop. Wired up in main.py via the lifespan hook.
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.core.logger import get_logger
from app.db.jobs_db import JobStatus, jobs_db
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# Stages that hold intermediate work and are safe to discard once the job is
# done. We keep raw/ (so re-runs don't need re-uploading), dsl/, outputs/, and
# plans/ (small JSON files, useful for debugging and rerender).
INTERMEDIATE_STAGES: tuple[str, ...] = ("prep", "render", "signals")


def cleanup_intermediates(storage: StorageManager) -> dict:
    """Delete this job's intermediate stage directories.

    Returns a small report dict for logging:
        {"removed_stages": ["prep", "render", "signals"], "bytes_freed": 1234567}
    """
    bytes_freed = 0
    removed = []
    for stage in INTERMEDIATE_STAGES:
        d = storage.stage_dir(stage)
        if not d.exists():
            continue
        bytes_freed += _dir_size(d)
        shutil.rmtree(d, ignore_errors=True)
        removed.append(stage)

    log.info(
        "[%s] Janitor: removed %s, freed %.1f MB",
        storage.job_id, removed, bytes_freed / 1024 / 1024,
    )
    return {"removed_stages": removed, "bytes_freed": bytes_freed}


def sweep_old_jobs(max_age_hours: float | None = None) -> dict:
    """Walk jobs_db and clean up intermediates for completed jobs aged beyond
    the threshold. Returns a summary report."""
    threshold = max_age_hours if max_age_hours is not None else settings.janitor_max_age_hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=threshold)

    cleaned = 0
    total_freed = 0
    for record in jobs_db.list_jobs():
        if record.status != JobStatus.COMPLETED:
            continue
        if record.updated_at > cutoff:
            continue

        storage = StorageManager(record.job_id)
        if not storage.job_dir().exists():
            continue
        # Skip if the intermediate dirs are already gone.
        if not any(storage.stage_dir(s).exists() for s in INTERMEDIATE_STAGES):
            continue

        report = cleanup_intermediates(storage)
        cleaned += 1
        total_freed += report["bytes_freed"]

    if cleaned > 0:
        log.info("Janitor sweep: cleaned %d jobs, freed %.1f MB",
                 cleaned, total_freed / 1024 / 1024)
    return {"jobs_cleaned": cleaned, "bytes_freed": total_freed}


async def start_periodic_sweep() -> asyncio.Task | None:
    """Spawn a background task that runs the sweep on a fixed interval.

    Returns the asyncio.Task so the caller can cancel it on shutdown. Returns
    None if the janitor is disabled in settings.
    """
    if not settings.janitor_enabled:
        log.info("Janitor: disabled in settings")
        return None

    interval_seconds = settings.janitor_interval_minutes * 60

    async def _loop():
        log.info(
            "Janitor: sweeping every %d min (max_age=%d h)",
            settings.janitor_interval_minutes,
            settings.janitor_max_age_hours,
        )
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                # Run synchronously in a thread so we don't block the loop on disk I/O.
                await asyncio.to_thread(sweep_old_jobs)
            except asyncio.CancelledError:
                log.info("Janitor: sweep cancelled")
                raise
            except Exception as e:
                log.warning("Janitor sweep error (continuing): %s", e)

    return asyncio.create_task(_loop(), name="disk-janitor")


def _dir_size(path: Path) -> int:
    """Sum file sizes recursively. Tolerates missing files (already-deleted entries)."""
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total
