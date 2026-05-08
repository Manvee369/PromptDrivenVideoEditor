"""Tests for multi-track audio role tagging — storage roles, FFmpeg builder
voiceover mixing, editing agent role-aware selection."""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.jobs_db import JobsDB
from app.dsl.schema import (
    ClipRef,
    FormatSpec,
    MusicTrack,
    Timeline,
    VoiceoverTrack,
)
from app.render.ffmpeg_builder import FFmpegCommandBuilder
from app.storage.storage_manager import StorageManager


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    sm = StorageManager(job_id="job-1", base_path=str(tmp_path))
    sm.ensure_dirs()
    return sm


# --- Storage role API ------------------------------------------------------


class TestStorageRoles:
    def test_role_inferred_from_extension(self, storage):
        assert storage.role_of("clip.mp4") == "video"
        assert storage.role_of("song.mp3") == "music"
        assert storage.role_of("photo.jpg") == "image"
        assert storage.role_of("README") == "unknown"

    def test_save_and_load_roles(self, storage):
        storage.save_roles({"a.mp4": "video", "b.mp3": "voiceover"})
        assert storage.load_roles() == {"a.mp4": "video", "b.mp3": "voiceover"}

    def test_explicit_role_overrides_inference(self, storage):
        # song.mp3 would default to "music" — but if user uploaded it under
        # voiceover_files[], the explicit role wins.
        storage.save_roles({"song.mp3": "voiceover"})
        assert storage.role_of("song.mp3") == "voiceover"

    def test_raw_files_by_role(self, storage):
        (storage.stage_dir("raw") / "a.mp4").write_bytes(b"")
        (storage.stage_dir("raw") / "music.mp3").write_bytes(b"")
        (storage.stage_dir("raw") / "narration.mp3").write_bytes(b"")
        storage.save_roles({
            "a.mp4": "video",
            "music.mp3": "music",
            "narration.mp3": "voiceover",
        })

        assert {f.name for f in storage.raw_files_by_role("music")} == {"music.mp3"}
        assert {f.name for f in storage.raw_files_by_role("voiceover")} == {"narration.mp3"}
        assert {f.name for f in storage.raw_files_by_role("video")} == {"a.mp4"}

    def test_roles_sidecar_excluded_from_raw_files(self, storage):
        # save_roles writes _roles.json into raw/ — it must not appear as media.
        (storage.stage_dir("raw") / "a.mp4").write_bytes(b"")
        storage.save_roles({"a.mp4": "video"})
        names = [f.name for f in storage.raw_files()]
        assert names == ["a.mp4"]


# --- FFmpeg builder voiceover ---------------------------------------------


class TestFFmpegVoiceoverMix:
    def test_voiceover_added_as_input(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
            voiceover=VoiceoverTrack(source="narration.wav"),
        )
        cmd = FFmpegCommandBuilder(t, storage).build()
        i_positions = [i for i, arg in enumerate(cmd) if arg == "-i"]
        sources = [cmd[i + 1] for i in i_positions]
        assert any("narration.wav" in s for s in sources)

    def test_voiceover_chain_emits_volume_and_label(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
            voiceover=VoiceoverTrack(source="narration.wav", volume=0.8),
        )
        cmd_str = " ".join(FFmpegCommandBuilder(t, storage).build())
        assert "[voice]" in cmd_str
        assert "volume=0.8" in cmd_str

    def test_three_way_mix_when_music_and_voiceover(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
            music=MusicTrack(source="bg.mp3"),
            voiceover=VoiceoverTrack(source="narration.wav"),
        )
        cmd_str = " ".join(FFmpegCommandBuilder(t, storage).build())
        # 3 inputs into amix: outa + music + voice
        assert "[outa][music][voice]amix=inputs=3:duration=first[mixed]" in cmd_str

    def test_no_voice_label_when_voiceover_none(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
            music=MusicTrack(source="bg.mp3"),
        )
        cmd_str = " ".join(FFmpegCommandBuilder(t, storage).build())
        # Music-only: 2-way mix
        assert "[outa][music]amix=inputs=2:duration=first[mixed]" in cmd_str
        assert "[voice]" not in cmd_str

    def test_voiceover_offset_emits_adelay(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
            voiceover=VoiceoverTrack(source="narration.wav", offset=2.5),
        )
        cmd_str = " ".join(FFmpegCommandBuilder(t, storage).build())
        assert "adelay=2500|2500" in cmd_str


# --- DSL validation --------------------------------------------------------


class TestDSLVoiceoverValidation:
    def test_validate_sources_flags_missing_voiceover(self):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=1)],
            voiceover=VoiceoverTrack(source="missing.wav"),
        )
        missing = t.validate_sources(["a.mp4"])
        assert "missing.wav" in missing


# --- Editing agent role-aware selection ------------------------------------


class TestEditingRoleAwareAudio:
    def test_picks_music_role(self, storage):
        # Build the bare minimum signals/manifest the editing agent needs.
        from app.agents.editing import build_timeline

        (storage.stage_dir("raw") / "v.mp4").write_bytes(b"")
        (storage.stage_dir("raw") / "song.mp3").write_bytes(b"")
        (storage.stage_dir("raw") / "narration.mp3").write_bytes(b"")
        storage.save_roles({
            "v.mp4": "video",
            "song.mp3": "music",
            "narration.mp3": "voiceover",
        })

        plan = {"style": {"width": 1920, "height": 1080, "aspect": "16:9", "energy": "medium"},
                "operations": []}
        signals = {
            "media_manifest": {
                "files": [{"filename": "v.mp4", "duration": 10.0,
                           "width": 1920, "height": 1080}],
            },
        }

        tl = build_timeline(plan, signals, storage)
        assert tl.music is not None
        assert tl.music.source == "song.mp3"
        assert tl.voiceover is not None
        assert tl.voiceover.source == "narration.mp3"

    def test_ducks_music_volume_when_voiceover_present(self, storage):
        from app.agents.editing import build_timeline

        (storage.stage_dir("raw") / "v.mp4").write_bytes(b"")
        (storage.stage_dir("raw") / "song.mp3").write_bytes(b"")
        (storage.stage_dir("raw") / "narration.mp3").write_bytes(b"")
        storage.save_roles({
            "v.mp4": "video",
            "song.mp3": "music",
            "narration.mp3": "voiceover",
        })

        plan = {"style": {"width": 1920, "height": 1080, "aspect": "16:9", "energy": "medium"},
                "operations": []}
        signals = {
            "media_manifest": {
                "files": [{"filename": "v.mp4", "duration": 10.0,
                           "width": 1920, "height": 1080}],
            },
        }

        tl = build_timeline(plan, signals, storage)
        # Default music volume (0.3) should be ducked to 0.15 or less when VO is present.
        assert tl.music.volume <= 0.15


# --- Routes form-field handling -------------------------------------------


@pytest.fixture
def client(tmp_path: Path, monkeypatch, mocker):
    monkeypatch.setattr("app.core.config.settings.storage_base", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.download_token_required", False)
    monkeypatch.setattr("app.core.config.settings.max_upload_bytes", 10_000)
    monkeypatch.setattr("app.core.config.settings.max_files_per_job", 10)

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


class TestRoleFormFields:
    def test_music_files_get_role_tag(self, client: TestClient, tmp_path):
        r = client.post(
            "/jobs/",
            data={"prompt": "p"},
            files=[
                ("files", ("clip.mp4", io.BytesIO(b"\x00" * 50), "video/mp4")),
                ("music_files", ("song.mp3", io.BytesIO(b"\x00" * 50), "audio/mpeg")),
            ],
        )
        assert r.status_code == 200
        job_id = r.json()["job_id"]
        sm = StorageManager(job_id, base_path=str(tmp_path))
        roles = sm.load_roles()
        assert roles["clip.mp4"] == "video"
        assert roles["song.mp3"] == "music"

    def test_voiceover_files_get_role_tag(self, client: TestClient, tmp_path):
        r = client.post(
            "/jobs/",
            data={"prompt": "p"},
            files=[
                ("files", ("clip.mp4", io.BytesIO(b"\x00" * 50), "video/mp4")),
                ("voiceover_files", ("narr.mp3", io.BytesIO(b"\x00" * 50), "audio/mpeg")),
            ],
        )
        assert r.status_code == 200
        job_id = r.json()["job_id"]
        sm = StorageManager(job_id, base_path=str(tmp_path))
        roles = sm.load_roles()
        assert roles["narr.mp3"] == "voiceover"
