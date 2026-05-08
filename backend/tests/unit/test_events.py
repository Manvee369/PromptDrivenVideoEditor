"""Tests for the per-job event sidecar."""
import json
from pathlib import Path

import pytest

from app.jobs.events import JobEvents
from app.storage.storage_manager import StorageManager


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    sm = StorageManager(job_id="job-1", base_path=str(tmp_path))
    sm.ensure_dirs()
    return sm


class TestJobEvents:
    def test_read_empty_when_no_file(self, storage):
        ev = JobEvents(storage)
        assert ev.read() == {}

    def test_emit_writes_fields(self, storage):
        ev = JobEvents(storage)
        ev.emit(substage="encoding", progress=0.42)
        state = ev.read()
        assert state["substage"] == "encoding"
        assert state["progress"] == 0.42
        assert "updated_at" in state

    def test_emit_merges_with_existing(self, storage):
        ev = JobEvents(storage)
        ev.emit(substage="encoding", progress=0.1)
        ev.emit(progress=0.5, message="halfway")  # update progress, add message
        state = ev.read()
        assert state["substage"] == "encoding"   # preserved
        assert state["progress"] == 0.5          # updated
        assert state["message"] == "halfway"     # new

    def test_clear_removes_file(self, storage):
        ev = JobEvents(storage)
        ev.emit(progress=0.3)
        assert ev.path.exists()
        ev.clear()
        assert not ev.path.exists()
        assert ev.read() == {}

    def test_corrupt_file_returns_empty(self, storage):
        ev = JobEvents(storage)
        ev.path.write_text("not valid json", encoding="utf-8")
        # Should NOT raise — best-effort behavior
        assert ev.read() == {}

    def test_emit_updates_timestamp(self, storage):
        ev = JobEvents(storage)
        ev.emit(progress=0.1)
        first_ts = ev.read()["updated_at"]
        # Brief wait to ensure timestamp changes — datetime.now precision is fine here
        import time
        time.sleep(0.001)
        ev.emit(progress=0.2)
        second_ts = ev.read()["updated_at"]
        assert first_ts != second_ts
