"""Persistent job store backed by a JSON file.

Thread-safe (in-process Lock) and cross-process-safe (file lock). The file
lock matters because the FastAPI server and one or more RQ workers may all
read/update jobs concurrently — without it, two writers will overwrite each
other's status updates.
"""

import json
import secrets
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock

from filelock import FileLock
from pydantic import BaseModel, Field

from app.core.config import settings


class JobStatus(str, Enum):
    CREATED = "created"
    PREPROCESSING = "preprocessing"
    INTELLIGENCE = "intelligence"
    PLANNING = "planning"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"
    # Set automatically on JobsDB load when a record is in a non-terminal state,
    # which means a server restart killed the worker mid-pipeline. The user can
    # resume via POST /jobs/{id}/rerun (cached stages are skipped).
    INTERRUPTED = "interrupted"


# Statuses that mean the job is no longer running (no worker owns it).
TERMINAL_STATUSES = frozenset({
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.INTERRUPTED,
})


class JobRecord(BaseModel):
    job_id: str
    prompt: str
    status: JobStatus = JobStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None
    progress: float = 0.0
    output_file: str | None = None
    # Opaque per-job token; required as ?token= on /download and /thumbnail
    # when settings.download_token_required is True. Old records loaded from
    # disk that lack this field get a fresh token via the default factory.
    download_token: str = Field(default_factory=lambda: secrets.token_urlsafe(32))

    # User-selected caption style preset (None = let the strategy router
    # decide based on classification). Accepted values are defined in
    # app.agents.captions.STYLE_PRESETS.
    caption_style: str | None = None
    # User-selected color grade preset applied across all clips. None = no
    # grade. Accepted values defined in app.render.color_grading.
    color_grade: str | None = None


class JobsDB:
    """Thread-safe + cross-process-safe job store persisted to a JSON file.

    Concurrency model:
      - In-process: `_lock` (threading.Lock) protects the in-memory cache.
      - Cross-process: `_file_lock` (filelock.FileLock) protects the JSON file.
        Workers running in separate processes acquire it around read/write.

    Reads always re-load from disk under the file lock so workers see updates
    made by the API process, and vice versa.
    """

    def __init__(self):
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()
        self._db_path = Path(settings.storage_base) / "_jobs.json"
        # FileLock companion file; survives process death, auto-released by OS.
        self._file_lock = FileLock(str(self._db_path) + ".lock", timeout=30)
        self._load()

    def _load(self):
        """Initial load from disk on construction.

        Any record in a non-terminal status is marked INTERRUPTED — the worker
        that owned it died with the previous process, so it can never finish
        on its own. The user can call POST /jobs/{id}/rerun to resume.
        """
        with self._file_lock:
            interrupted_any = self._reload_no_lock(promote_to_interrupted=True)
            if interrupted_any:
                self._persist_no_lock()

    def _reload_no_lock(self, promote_to_interrupted: bool = False) -> bool:
        """Refresh self._jobs from disk. Caller must hold self._file_lock.

        With promote_to_interrupted=True, any non-terminal record is marked
        INTERRUPTED; returns True if any record was promoted.
        """
        self._jobs = {}
        if not self._db_path.exists():
            return False
        try:
            data = json.loads(self._db_path.read_text(encoding="utf-8"))
        except Exception:
            return False  # corrupt file — start fresh

        promoted = False
        for record_data in data:
            try:
                record = JobRecord(**record_data)
            except Exception:
                continue
            if promote_to_interrupted and record.status not in TERMINAL_STATUSES:
                record.status = JobStatus.INTERRUPTED
                record.error = (
                    f"Server restarted while job was {record_data.get('status', 'running')}. "
                    f"POST /jobs/{record.job_id}/rerun to resume."
                )
                promoted = True
            self._jobs[record.job_id] = record
        return promoted

    def _persist_no_lock(self):
        """Write all jobs to disk atomically. Caller must hold self._file_lock."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        data = [json.loads(record.model_dump_json()) for record in self._jobs.values()]
        # Write to a temp file then rename — atomic on POSIX, near-atomic on Windows.
        tmp_path = self._db_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp_path.replace(self._db_path)

    def create(
        self,
        job_id: str,
        prompt: str,
        caption_style: str | None = None,
        color_grade: str | None = None,
    ) -> JobRecord:
        record = JobRecord(
            job_id=job_id,
            prompt=prompt,
            caption_style=caption_style,
            color_grade=color_grade,
        )
        with self._file_lock, self._lock:
            self._reload_no_lock()
            self._jobs[job_id] = record
            self._persist_no_lock()
        return record

    def get(self, job_id: str) -> JobRecord | None:
        # Reads also re-sync so the API sees fresh status updates from the worker.
        with self._file_lock, self._lock:
            self._reload_no_lock()
            return self._jobs.get(job_id)

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: float | None = None,
        error: str | None = None,
        output_file: str | None = None,
    ) -> JobRecord:
        with self._file_lock, self._lock:
            self._reload_no_lock()
            record = self._jobs[job_id]
            record.status = status
            record.updated_at = datetime.now(timezone.utc)
            if progress is not None:
                record.progress = progress
            if error is not None:
                record.error = error
            if output_file is not None:
                record.output_file = output_file
            self._persist_no_lock()
            return record

    def list_jobs(self) -> list[JobRecord]:
        with self._file_lock, self._lock:
            self._reload_no_lock()
            return list(self._jobs.values())


jobs_db = JobsDB()
