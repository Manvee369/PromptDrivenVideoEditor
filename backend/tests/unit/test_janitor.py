"""Tests for the disk-usage janitor."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.db.jobs_db import JobsDB, JobStatus
from app.jobs.janitor import (
    INTERMEDIATE_STAGES,
    cleanup_intermediates,
    sweep_old_jobs,
)
from app.storage.storage_manager import StorageManager


def _backdate(db: JobsDB, job_id: str, hours: float) -> None:
    """Test helper: rewind a job's updated_at by `hours`.

    JobsDB now re-reads from disk on every operation (cross-process safety),
    so we have to mutate the in-memory dict AND persist under the lock.
    """
    with db._file_lock, db._lock:
        db._reload_no_lock()
        db._jobs[job_id].updated_at = datetime.now(timezone.utc) - timedelta(hours=hours)
        db._persist_no_lock()


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    sm = StorageManager(job_id="job-1", base_path=str(tmp_path))
    sm.ensure_dirs()
    # Drop a few files in each stage so we can verify cleanup.
    for stage in ("raw", "prep", "signals", "plans", "dsl", "render", "outputs"):
        (sm.stage_dir(stage) / f"{stage}_file.bin").write_bytes(b"x" * 1024)
    return sm


class TestCleanupIntermediates:
    def test_removes_intermediate_stages(self, storage: StorageManager):
        cleanup_intermediates(storage)
        for stage in INTERMEDIATE_STAGES:
            assert not storage.stage_dir(stage).exists()

    def test_preserves_raw_dsl_outputs_plans(self, storage: StorageManager):
        cleanup_intermediates(storage)
        assert storage.stage_dir("raw").exists()
        assert storage.stage_dir("dsl").exists()
        assert storage.stage_dir("outputs").exists()
        assert storage.stage_dir("plans").exists()

    def test_reports_bytes_freed(self, storage: StorageManager):
        report = cleanup_intermediates(storage)
        # 3 stages * 1KB seed file = at least 3072 bytes
        assert report["bytes_freed"] >= 3 * 1024
        assert set(report["removed_stages"]) == set(INTERMEDIATE_STAGES)

    def test_idempotent(self, storage: StorageManager):
        cleanup_intermediates(storage)
        # second call should be a no-op (no exceptions)
        report = cleanup_intermediates(storage)
        assert report["bytes_freed"] == 0


class TestSweepOldJobs:
    @pytest.fixture
    def fresh_db(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("app.db.jobs_db.settings.storage_base", str(tmp_path))
        monkeypatch.setattr("app.jobs.janitor.settings.janitor_max_age_hours", 24)

        db = JobsDB()
        # Replace the module global so janitor.sweep_old_jobs sees our DB.
        monkeypatch.setattr("app.jobs.janitor.jobs_db", db)
        return db

    def test_skips_recent_completed_jobs(self, fresh_db, tmp_path):
        rec = fresh_db.create("recent", "p")
        fresh_db.update_status("recent", JobStatus.COMPLETED)
        # Seed prep/ so we'd notice if it got cleaned.
        sm = StorageManager("recent", base_path=str(tmp_path))
        sm.ensure_dirs()
        (sm.stage_dir("prep") / "x.bin").write_bytes(b"x")

        report = sweep_old_jobs()
        assert report["jobs_cleaned"] == 0
        assert (sm.stage_dir("prep") / "x.bin").exists()

    def test_cleans_old_completed_jobs(self, fresh_db, tmp_path):
        fresh_db.create("old", "p")
        fresh_db.update_status("old", JobStatus.COMPLETED)
        _backdate(fresh_db, "old", hours=48)

        sm = StorageManager("old", base_path=str(tmp_path))
        sm.ensure_dirs()
        (sm.stage_dir("prep") / "x.bin").write_bytes(b"y" * 100)
        (sm.stage_dir("raw") / "kept.mp4").write_bytes(b"z")

        report = sweep_old_jobs()
        assert report["jobs_cleaned"] == 1
        assert not sm.stage_dir("prep").exists()
        assert (sm.stage_dir("raw") / "kept.mp4").exists()  # raw preserved

    def test_skips_failed_jobs(self, fresh_db, tmp_path):
        fresh_db.create("failed", "p")
        fresh_db.update_status("failed", JobStatus.FAILED)
        _backdate(fresh_db, "failed", hours=48)

        sm = StorageManager("failed", base_path=str(tmp_path))
        sm.ensure_dirs()
        (sm.stage_dir("prep") / "x.bin").write_bytes(b"x")

        report = sweep_old_jobs()
        assert report["jobs_cleaned"] == 0  # failed jobs left alone for postmortem

    def test_skips_jobs_already_cleaned(self, fresh_db, tmp_path):
        fresh_db.create("clean", "p")
        fresh_db.update_status("clean", JobStatus.COMPLETED)
        _backdate(fresh_db, "clean", hours=48)

        sm = StorageManager("clean", base_path=str(tmp_path))
        sm.ensure_dirs()
        # No intermediate stages — already cleaned.
        for stage in INTERMEDIATE_STAGES:
            import shutil
            shutil.rmtree(sm.stage_dir(stage), ignore_errors=True)

        report = sweep_old_jobs()
        assert report["jobs_cleaned"] == 0
