"""Tests for routes_jobs.py — Phase 2 ingress hardening.

Covers: upload size cap, extension whitelist, file count cap, ffprobe rejection,
and download_token enforcement on /download and /thumbnail.
"""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.jobs_db import JobsDB, JobRecord, JobStatus


def _fake_video_bytes(size: int) -> bytes:
    """Generate `size` bytes of dummy data."""
    return b"\x00" * size


@pytest.fixture
def client(tmp_path: Path, monkeypatch, mocker):
    """A FastAPI TestClient with isolated storage and tight limits."""
    # Tight limits make size-cap test cheap to exercise.
    monkeypatch.setattr("app.core.config.settings.storage_base", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.max_upload_bytes", 100)
    monkeypatch.setattr("app.core.config.settings.max_files_per_job", 3)
    monkeypatch.setattr("app.core.config.settings.download_token_required", True)

    # Replace the module-level jobs_db with a fresh instance writing to tmp_path.
    fresh = JobsDB()
    fresh._db_path = tmp_path / "_jobs.json"
    fresh._jobs.clear()
    monkeypatch.setattr("app.api.routes_jobs.jobs_db", fresh)
    monkeypatch.setattr("app.db.jobs_db.jobs_db", fresh)

    # Pipeline is fired via BackgroundTasks; stub it so we don't actually
    # try to run Whisper/SigLIP for upload-validation tests.
    mocker.patch("app.api.routes_jobs.run_pipeline", return_value="/fake/output.mp4")

    # Stub ffprobe — uploads in tests are not real media files.
    mocker.patch(
        "app.api.routes_jobs.probe_media",
        return_value={"format": {"duration": "10.0"}, "streams": []},
    )

    from app.main import app
    return TestClient(app)


@pytest.fixture
def client_no_token(client, monkeypatch):
    """Client with token enforcement disabled."""
    monkeypatch.setattr("app.core.config.settings.download_token_required", False)
    return client


def _post_create(client: TestClient, files: list[tuple[str, bytes]], prompt: str = "p"):
    """Helper to POST to /jobs/ with multipart files."""
    return client.post(
        "/jobs/",
        data={"prompt": prompt},
        files=[("files", (name, io.BytesIO(data), "video/mp4")) for name, data in files],
    )


# --- Upload validation -----------------------------------------------------


class TestExtensionWhitelist:
    def test_rejects_unknown_extension(self, client: TestClient):
        r = _post_create(client, [("malware.exe", b"x")])
        assert r.status_code == 400
        assert "not allowed" in r.json()["detail"]

    def test_accepts_known_video_extension(self, client: TestClient):
        r = _post_create(client, [("clip.mp4", _fake_video_bytes(50))])
        assert r.status_code == 200
        assert r.json()["status"] == "created"

    def test_accepts_known_audio_extension(self, client: TestClient):
        r = _post_create(client, [("song.mp3", _fake_video_bytes(50))])
        assert r.status_code == 200


class TestSizeCap:
    def test_rejects_file_above_limit(self, client: TestClient):
        # limit was set to 100 bytes in the fixture
        r = _post_create(client, [("big.mp4", _fake_video_bytes(500))])
        assert r.status_code == 413
        assert "limit" in r.json()["detail"].lower()

    def test_accepts_file_at_limit(self, client: TestClient):
        r = _post_create(client, [("ok.mp4", _fake_video_bytes(100))])
        assert r.status_code == 200


class TestFileCountCap:
    def test_rejects_more_than_max(self, client: TestClient):
        # limit is 3 in the fixture
        r = _post_create(client, [(f"f{i}.mp4", b"x") for i in range(5)])
        assert r.status_code == 400
        assert "Too many files" in r.json()["detail"]

    def test_rejects_zero_files(self, client: TestClient):
        r = client.post("/jobs/", data={"prompt": "p"})
        assert r.status_code == 400


class TestProbeRejection:
    def test_rejects_zero_duration_file(self, client: TestClient, mocker):
        mocker.patch(
            "app.api.routes_jobs.probe_media",
            return_value={"format": {"duration": "0"}},
        )
        r = _post_create(client, [("empty.mp4", b"x")])
        assert r.status_code == 400
        assert "zero duration" in r.json()["detail"]

    def test_rejects_unprobeable_file(self, client: TestClient, mocker):
        from app.utils.ffmpeg_utils import FFmpegError
        mocker.patch(
            "app.api.routes_jobs.probe_media",
            side_effect=FFmpegError("not a media file"),
        )
        r = _post_create(client, [("garbage.mp4", b"x")])
        assert r.status_code == 400
        assert "valid media" in r.json()["detail"]


class TestRollback:
    def test_partial_uploads_cleaned_up_on_failure(self, client: TestClient, tmp_path):
        # 2nd file has a bad extension — first should be rolled back.
        r = client.post(
            "/jobs/",
            data={"prompt": "p"},
            files=[
                ("files", ("good.mp4", io.BytesIO(b"x"), "video/mp4")),
                ("files", ("bad.exe", io.BytesIO(b"x"), "application/octet-stream")),
            ],
        )
        assert r.status_code == 400
        # The job dir was created — verify it was torn down.
        # Walk every job dir under storage; none should contain "good.mp4"
        for path in tmp_path.rglob("good.mp4"):
            pytest.fail(f"Orphan upload not cleaned up: {path}")


# --- Download token enforcement -------------------------------------------


def _seed_job(client: TestClient, status: JobStatus = JobStatus.COMPLETED) -> JobRecord:
    """Bypass the upload pipeline by inserting a job directly into jobs_db,
    then fabricate the output files so /download succeeds."""
    from app.api.routes_jobs import jobs_db
    from app.storage.storage_manager import StorageManager

    rec = jobs_db.create("test-job", "p")
    jobs_db.update_status(rec.job_id, status)

    storage = StorageManager(rec.job_id)
    storage.ensure_dirs()
    # Fake the output file so FileResponse doesn't 404.
    storage.output_path("final.mp4").write_bytes(b"FAKEMP4")
    storage.output_path("thumbnail.png").write_bytes(b"FAKEPNG")
    return rec


class TestDownloadToken:
    def test_download_requires_token_when_enforced(self, client: TestClient):
        rec = _seed_job(client)
        r = client.get(f"/jobs/{rec.job_id}/download")
        assert r.status_code == 403

    def test_download_rejects_wrong_token(self, client: TestClient):
        rec = _seed_job(client)
        r = client.get(f"/jobs/{rec.job_id}/download?token=bogus")
        assert r.status_code == 403

    def test_download_accepts_correct_token(self, client: TestClient):
        rec = _seed_job(client)
        r = client.get(f"/jobs/{rec.job_id}/download?token={rec.download_token}")
        assert r.status_code == 200
        assert r.content == b"FAKEMP4"

    def test_thumbnail_requires_token(self, client: TestClient):
        rec = _seed_job(client)
        r = client.get(f"/jobs/{rec.job_id}/thumbnail")
        assert r.status_code == 403

    def test_thumbnail_accepts_correct_token(self, client: TestClient):
        rec = _seed_job(client)
        r = client.get(f"/jobs/{rec.job_id}/thumbnail?token={rec.download_token}")
        assert r.status_code == 200

    def test_download_disabled_when_setting_off(self, client_no_token: TestClient):
        rec = _seed_job(client_no_token)
        r = client_no_token.get(f"/jobs/{rec.job_id}/download")
        assert r.status_code == 200


class TestCreateResponse:
    def test_returns_download_token(self, client: TestClient):
        r = _post_create(client, [("ok.mp4", _fake_video_bytes(50))])
        body = r.json()
        assert "download_token" in body
        assert len(body["download_token"]) >= 16  # token_urlsafe(32) → ~43 chars


class TestSettings:
    def test_allowed_origins_parses_csv(self):
        from app.core.config import Settings
        s = Settings(allowed_origins_csv="https://a.com, https://b.com,  https://c.com  ")
        assert s.allowed_origins == ["https://a.com", "https://b.com", "https://c.com"]

    def test_allowed_origins_empty_entries_dropped(self):
        from app.core.config import Settings
        s = Settings(allowed_origins_csv="https://a.com,, ,https://b.com")
        assert s.allowed_origins == ["https://a.com", "https://b.com"]
