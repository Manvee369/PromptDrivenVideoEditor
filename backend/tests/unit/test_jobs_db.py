"""Tests for app/db/jobs_db.py — persistent job state."""
from pathlib import Path

import pytest

from app.db.jobs_db import JobsDB, JobStatus


@pytest.fixture
def db_factory(tmp_path: Path, monkeypatch):
    """Build a JobsDB rooted at tmp_path. Returns a callable so tests can build
    multiple instances backed by the same on-disk file (for reload testing)."""
    monkeypatch.setattr("app.db.jobs_db.settings.storage_base", str(tmp_path))

    def _make() -> JobsDB:
        return JobsDB()

    return _make


@pytest.fixture
def db(db_factory) -> JobsDB:
    return db_factory()


class TestJobsDB:
    def test_create_returns_record_with_status_created(self, db: JobsDB):
        rec = db.create("job-1", "make a montage")
        assert rec.job_id == "job-1"
        assert rec.status == JobStatus.CREATED
        assert rec.prompt == "make a montage"
        assert rec.progress == 0.0
        assert rec.error is None
        assert rec.output_file is None

    def test_get_returns_existing_record(self, db: JobsDB):
        db.create("job-1", "p")
        assert db.get("job-1") is not None

    def test_get_returns_none_for_unknown(self, db: JobsDB):
        assert db.get("nope") is None

    def test_update_status_changes_state_and_progress(self, db: JobsDB):
        db.create("job-1", "p")
        db.update_status("job-1", JobStatus.RENDERING, progress=0.7)
        rec = db.get("job-1")
        assert rec.status == JobStatus.RENDERING
        assert rec.progress == 0.7

    def test_update_status_stores_error(self, db: JobsDB):
        db.create("job-1", "p")
        db.update_status("job-1", JobStatus.FAILED, error="ffmpeg crashed")
        assert db.get("job-1").error == "ffmpeg crashed"

    def test_update_status_stores_output_file(self, db: JobsDB):
        db.create("job-1", "p")
        db.update_status("job-1", JobStatus.COMPLETED, output_file="/path/final.mp4")
        assert db.get("job-1").output_file == "/path/final.mp4"

    def test_list_jobs_returns_all(self, db: JobsDB):
        db.create("job-1", "p1")
        db.create("job-2", "p2")
        ids = {j.job_id for j in db.list_jobs()}
        assert ids == {"job-1", "job-2"}

    def test_persists_across_reload(self, db_factory):
        db1 = db_factory()
        db1.create("job-1", "saved")
        db1.update_status("job-1", JobStatus.COMPLETED, output_file="final.mp4")

        db2 = db_factory()
        rec = db2.get("job-1")
        assert rec is not None
        assert rec.status == JobStatus.COMPLETED
        assert rec.output_file == "final.mp4"

    def test_corrupt_file_starts_fresh(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.db.jobs_db.settings.storage_base", str(tmp_path))
        db_path = tmp_path / "_jobs.json"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_text("not valid json", encoding="utf-8")
        # Should not raise on load
        db = JobsDB()
        assert db.list_jobs() == []
