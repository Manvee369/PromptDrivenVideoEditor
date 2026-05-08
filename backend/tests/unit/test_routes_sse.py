"""Smoke test for the SSE events endpoint — verifies wiring without depending
on long-running streaming."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.jobs_db import JobsDB, JobStatus


@pytest.fixture
def client(tmp_path: Path, monkeypatch, mocker):
    monkeypatch.setattr("app.core.config.settings.storage_base", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.download_token_required", False)

    fresh = JobsDB()
    fresh._db_path = tmp_path / "_jobs.json"
    fresh._jobs.clear()
    monkeypatch.setattr("app.api.routes_jobs.jobs_db", fresh)
    monkeypatch.setattr("app.db.jobs_db.jobs_db", fresh)

    mocker.patch("app.api.routes_jobs.run_pipeline")
    mocker.patch("app.api.routes_jobs.rerender_only")
    from app.main import app
    return TestClient(app)


class TestSSEEndpoint:
    def test_404_for_unknown_job(self, client: TestClient):
        r = client.get("/jobs/does-not-exist/events")
        assert r.status_code == 404

    def test_streams_initial_state_for_terminal_job(self, client: TestClient):
        # A terminal job should emit one snapshot then close.
        from app.api.routes_jobs import jobs_db
        rec = jobs_db.create("done-job", "p")
        jobs_db.update_status("done-job", JobStatus.COMPLETED, progress=1.0,
                              output_file="/x.mp4")

        # Read the stream — it should close quickly because status is COMPLETED.
        with client.stream("GET", f"/jobs/{rec.job_id}/events") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")

            chunks = []
            for line in resp.iter_lines():
                chunks.append(line)
                if "event: done" in line:
                    break

        # We expect at least one data line + the done event marker.
        joined = "\n".join(chunks)
        assert "data:" in joined
        assert "completed" in joined
        assert "event: done" in joined

    def test_emits_substage_progress(self, client: TestClient, tmp_path):
        from app.api.routes_jobs import jobs_db
        from app.jobs.events import JobEvents
        from app.storage.storage_manager import StorageManager

        rec = jobs_db.create("rendering-job", "p")
        jobs_db.update_status("rendering-job", JobStatus.COMPLETED, progress=1.0)

        # Pre-populate progress.json sidecar
        sm = StorageManager(rec.job_id)
        sm.ensure_dirs()
        JobEvents(sm).emit(substage="render", progress=0.42, frame=100, fps=30.0)

        with client.stream("GET", f"/jobs/{rec.job_id}/events") as resp:
            assert resp.status_code == 200
            collected = []
            for line in resp.iter_lines():
                collected.append(line)
                if "event: done" in line:
                    break

        # Find the JSON data line and parse it
        data_line = next(
            (l for l in collected if l.startswith("data:") and "{" in l),
            None,
        )
        assert data_line is not None
        payload = json.loads(data_line[len("data:"):].strip())
        assert payload["substage"] == "render"
        assert payload["substage_progress"] == 0.42
        assert payload["frame"] == 100
