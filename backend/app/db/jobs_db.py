"""In-memory job store. Swap internals to SQLite/Postgres later."""

from datetime import datetime, timezone
from enum import Enum
from threading import Lock

from pydantic import BaseModel, Field


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
    """Thread-safe in-memory job store."""

    def __init__(self):
        self._jobs: dict[str, JobRecord] = {}
        self._lock = Lock()

    def create(self, job_id: str, prompt: str) -> JobRecord:
        record = JobRecord(job_id=job_id, prompt=prompt)
        with self._lock:
            self._jobs[job_id] = record
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
            return record

    def list_jobs(self) -> list[JobRecord]:
        with self._lock:
            return list(self._jobs.values())


jobs_db = JobsDB()
