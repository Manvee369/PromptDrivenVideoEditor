"""Tests for PUT /jobs/{id}/timeline — Phase 3 timeline editing."""
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

    mocker.patch("app.api.routes_jobs.run_pipeline", return_value="/x.mp4")
    mocker.patch("app.api.routes_jobs.rerender_only", return_value="/x.mp4")

    from app.main import app
    return TestClient(app)


@pytest.fixture
def seeded_job(client: TestClient, tmp_path: Path):
    """Create a job with raw files and an initial DSL on disk."""
    from app.api.routes_jobs import jobs_db
    from app.storage.storage_manager import StorageManager

    rec = jobs_db.create("job-edit", "p")
    storage = StorageManager(rec.job_id)
    storage.ensure_dirs()
    # Provide source files so validate_sources passes
    (storage.stage_dir("raw") / "a.mp4").write_bytes(b"")
    (storage.stage_dir("raw") / "b.mp4").write_bytes(b"")

    # Save an initial timeline
    initial = {
        "version": "1.0",
        "format": {"width": 1920, "height": 1080, "fps": 30, "aspect": "16:9"},
        "clips": [
            {"source": "a.mp4", "start": 0.0, "end": 5.0,
             "speed": 1.0, "volume": 1.0, "transition_in": None,
             "transition_duration": 0.3, "zoom": 1.0, "filters": []},
        ],
        "captions": [],
        "music": None,
    }
    storage.save_dsl(initial)
    return rec


class TestUpdateTimeline:
    def test_updates_with_valid_timeline(self, client: TestClient, seeded_job):
        new_dsl = {
            "version": "1.0",
            "format": {"width": 1920, "height": 1080, "fps": 30, "aspect": "16:9"},
            "clips": [
                {"source": "a.mp4", "start": 0.0, "end": 3.0,
                 "speed": 1.0, "volume": 1.0, "transition_in": None,
                 "transition_duration": 0.3, "zoom": 1.0, "filters": []},
                {"source": "b.mp4", "start": 1.0, "end": 4.5,
                 "speed": 1.0, "volume": 1.0, "transition_in": "crossfade",
                 "transition_duration": 0.5, "zoom": 1.0, "filters": []},
            ],
            "captions": [],
            "music": None,
        }
        r = client.put(f"/jobs/{seeded_job.job_id}/timeline", json=new_dsl)
        assert r.status_code == 200
        body = r.json()
        assert len(body["clips"]) == 2
        assert body["clips"][1]["transition_in"] == "crossfade"

    def test_rejects_unknown_job(self, client: TestClient):
        r = client.put("/jobs/nonexistent/timeline", json={"clips": []})
        assert r.status_code == 404

    def test_rejects_invalid_schema(self, client: TestClient, seeded_job):
        # Missing required "clips" — Pydantic rejects.
        r = client.put(f"/jobs/{seeded_job.job_id}/timeline", json={"format": {}})
        assert r.status_code == 422

    def test_rejects_missing_source_file(self, client: TestClient, seeded_job):
        bad = {
            "version": "1.0",
            "format": {"width": 1920, "height": 1080, "fps": 30, "aspect": "16:9"},
            "clips": [
                {"source": "missing.mp4", "start": 0.0, "end": 1.0,
                 "speed": 1.0, "volume": 1.0, "transition_in": None,
                 "transition_duration": 0.3, "zoom": 1.0, "filters": []},
            ],
            "captions": [],
            "music": None,
        }
        r = client.put(f"/jobs/{seeded_job.job_id}/timeline", json=bad)
        assert r.status_code == 422
        # Detail is a dict with errors list
        assert "validation failed" in r.json()["detail"]["message"].lower()
        assert any("missing.mp4" in e for e in r.json()["detail"]["errors"])

    def test_rejects_negative_start(self, client: TestClient, seeded_job):
        bad = {
            "version": "1.0",
            "format": {"width": 1920, "height": 1080, "fps": 30, "aspect": "16:9"},
            "clips": [
                {"source": "a.mp4", "start": -1.0, "end": 1.0,
                 "speed": 1.0, "volume": 1.0, "transition_in": None,
                 "transition_duration": 0.3, "zoom": 1.0, "filters": []},
            ],
            "captions": [],
            "music": None,
        }
        r = client.put(f"/jobs/{seeded_job.job_id}/timeline", json=bad)
        assert r.status_code == 422
        assert any("negative start" in e for e in r.json()["detail"]["errors"])

    def test_persisted_to_disk(self, client: TestClient, seeded_job):
        from app.storage.storage_manager import StorageManager

        new_dsl = {
            "version": "1.0",
            "format": {"width": 1920, "height": 1080, "fps": 30, "aspect": "16:9"},
            "clips": [
                {"source": "a.mp4", "start": 2.0, "end": 7.5,
                 "speed": 2.0, "volume": 0.5, "transition_in": None,
                 "transition_duration": 0.3, "zoom": 1.5, "filters": []},
            ],
            "captions": [],
            "music": None,
        }
        client.put(f"/jobs/{seeded_job.job_id}/timeline", json=new_dsl)

        storage = StorageManager(seeded_job.job_id)
        on_disk = storage.load_dsl()
        assert on_disk["clips"][0]["start"] == 2.0
        assert on_disk["clips"][0]["end"] == 7.5
        assert on_disk["clips"][0]["speed"] == 2.0
        assert on_disk["clips"][0]["zoom"] == 1.5
