"""Persistent job store backed by a JSON file. Thread-safe."""

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock

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


class JobRecord(BaseModel):
    job_id: str
    prompt: str
    status: JobStatus = JobStatus.CREATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None
    progress: float = 0.0
    output_file: str | None = None


class JobsDB:
    """Thread-safe job store persisted to a JSON file."""

    def __init__(self):
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()
        self._db_path = Path(settings.storage_base) / "_jobs.json"
        self._load()

    def _load(self):
        """Load jobs from disk on startup."""
        if not self._db_path.exists():
            return
        try:
            data = json.loads(self._db_path.read_text(encoding="utf-8"))
            for record_data in data:
                record = JobRecord(**record_data)
                self._jobs[record.job_id] = record
        except Exception:
            pass  # corrupt file — start fresh

    def _persist(self):
        """Write all jobs to disk. Must be called with lock held."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        data = [
            json.loads(record.model_dump_json())
            for record in self._jobs.values()
        ]
        self._db_path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )

    def create(self, job_id: str, prompt: str) -> JobRecord:
        record = JobRecord(job_id=job_id, prompt=prompt)
        with self._lock:
            self._jobs[job_id] = record
            self._persist()
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: float | None = None,
        error: str | None = None,
        output_file: str | None = None,
    ) -> JobRecord:
        with self._lock:
            record = self._jobs[job_id]
            record.status = status
            record.updated_at = datetime.now(timezone.utc)
            if progress is not None:
                record.progress = progress
            if error is not None:
                record.error = error
            if output_file is not None:
                record.output_file = output_file
            self._persist()
            return record

    def list_jobs(self) -> list[JobRecord]:
        with self._lock:
            return list(self._jobs.values())


jobs_db = JobsDB()
