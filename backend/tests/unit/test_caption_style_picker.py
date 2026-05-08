"""Tests for the user-selected caption style preset."""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.captions import STYLE_PRESETS, STYLES
from app.db.jobs_db import JobsDB


@pytest.fixture
def client(tmp_path: Path, monkeypatch, mocker):
    monkeypatch.setattr("app.core.config.settings.storage_base", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.download_token_required", False)
    monkeypatch.setattr("app.core.config.settings.max_upload_bytes", 10_000)

    fresh = JobsDB()
    fresh._db_path = tmp_path / "_jobs.json"
    fresh._jobs.clear()
    monkeypatch.setattr("app.api.routes_jobs.jobs_db", fresh)
    monkeypatch.setattr("app.db.jobs_db.jobs_db", fresh)

    mocker.patch("app.api.routes_jobs.run_pipeline")
    mocker.patch(
        "app.api.routes_jobs.probe_media",
        return_value={"format": {"duration": "10.0"}, "streams": []},
    )

    from app.main import app
    return TestClient(app)


class TestCaptionStylePresets:
    def test_all_presets_have_a_style_def(self):
        # If we exposed a name in STYLE_PRESETS, it must exist in STYLES.
        for name in STYLE_PRESETS:
            assert name in STYLES, f"preset '{name}' missing from STYLES"

    def test_preset_list_is_stable(self):
        # Documented contract: these are the supported values today.
        assert "default" in STYLE_PRESETS
        assert "tiktok_bold" in STYLE_PRESETS


class TestCreateJobWithCaptionStyle:
    def _post(self, client, **extra):
        return client.post(
            "/jobs/",
            data={"prompt": "p", **extra},
            files=[("files", ("clip.mp4", io.BytesIO(b"\x00" * 50), "video/mp4"))],
        )

    def test_accepts_valid_preset(self, client: TestClient):
        r = self._post(client, caption_style="minimal")
        assert r.status_code == 200

    def test_rejects_unknown_preset(self, client: TestClient):
        r = self._post(client, caption_style="comic_sans_extreme")
        assert r.status_code == 400
        assert "Invalid caption_style" in r.json()["detail"]

    def test_persists_preset_on_record(self, client: TestClient):
        from app.api.routes_jobs import jobs_db
        r = self._post(client, caption_style="dramatic")
        assert r.status_code == 200
        rec = jobs_db.get(r.json()["job_id"])
        assert rec.caption_style == "dramatic"

    def test_no_preset_means_none_on_record(self, client: TestClient):
        from app.api.routes_jobs import jobs_db
        r = self._post(client)  # no caption_style field
        assert r.status_code == 200
        rec = jobs_db.get(r.json()["job_id"])
        assert rec.caption_style is None
