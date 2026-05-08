"""Tests for JobsDB restart-recovery behavior — non-terminal jobs are
marked INTERRUPTED on load."""
import json
from pathlib import Path

import pytest

from app.db.jobs_db import TERMINAL_STATUSES, JobRecord, JobsDB, JobStatus


def _seed_db_file(tmp_path: Path, records: list[dict]) -> Path:
    """Write a jobs DB JSON file directly to the tmp dir."""
    db_path = tmp_path / "_jobs.json"
    db_path.write_text(json.dumps(records, default=str), encoding="utf-8")
    return db_path


@pytest.fixture
def db_factory(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app.db.jobs_db.settings.storage_base", str(tmp_path))

    def _make() -> JobsDB:
        return JobsDB()

    return _make


class TestRestartRecovery:
    @pytest.mark.parametrize("status", [
        JobStatus.CREATED,
        JobStatus.PREPROCESSING,
        JobStatus.INTELLIGENCE,
        JobStatus.PLANNING,
        JobStatus.RENDERING,
    ])
    def test_non_terminal_jobs_marked_interrupted(self, tmp_path, db_factory, status):
        _seed_db_file(tmp_path, [
            {
                "job_id": "j1",
                "prompt": "p",
                "status": status.value,
                "created_at": "2026-05-07T00:00:00+00:00",
                "updated_at": "2026-05-07T00:00:00+00:00",
                "progress": 0.4,
            }
        ])
        db = db_factory()
        rec = db.get("j1")
        assert rec is not None
        assert rec.status == JobStatus.INTERRUPTED
        assert rec.error is not None
        assert "rerun" in rec.error.lower()

    @pytest.mark.parametrize("status", list(TERMINAL_STATUSES))
    def test_terminal_jobs_left_alone(self, tmp_path, db_factory, status):
        _seed_db_file(tmp_path, [
            {
                "job_id": "j1",
                "prompt": "p",
                "status": status.value,
                "created_at": "2026-05-07T00:00:00+00:00",
                "updated_at": "2026-05-07T00:00:00+00:00",
                "progress": 1.0,
            }
        ])
        db = db_factory()
        assert db.get("j1").status == status

    def test_interrupted_status_persisted(self, tmp_path, db_factory):
        # Seed with a running job, load (which marks INTERRUPTED), then
        # load again with a fresh DB instance — the status must stick.
        _seed_db_file(tmp_path, [
            {
                "job_id": "j1",
                "prompt": "p",
                "status": "rendering",
                "created_at": "2026-05-07T00:00:00+00:00",
                "updated_at": "2026-05-07T00:00:00+00:00",
                "progress": 0.7,
            }
        ])
        db_factory()  # first load — should write back INTERRUPTED
        db2 = db_factory()
        assert db2.get("j1").status == JobStatus.INTERRUPTED

    def test_malformed_record_skipped_not_fatal(self, tmp_path, db_factory):
        _seed_db_file(tmp_path, [
            {"job_id": "good", "prompt": "p", "status": "completed",
             "created_at": "2026-05-07T00:00:00+00:00",
             "updated_at": "2026-05-07T00:00:00+00:00", "progress": 1.0},
            {"this_is": "garbage"},
        ])
        db = db_factory()
        # Good record loaded, bad one ignored
        assert db.get("good") is not None
        assert len(db.list_jobs()) == 1
