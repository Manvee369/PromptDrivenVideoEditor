"""Tests for image clip support — DSL, ffmpeg builder, editing agent."""

from pathlib import Path

import pytest

from app.dsl.schema import ClipRef, FormatSpec, MusicTrack, Timeline
from app.render.ffmpeg_builder import FFmpegCommandBuilder
from app.storage.storage_manager import StorageManager


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    sm = StorageManager(job_id="job-1", base_path=str(tmp_path))
    sm.ensure_dirs()
    return sm


def _img_clip(**overrides) -> ClipRef:
    base = {
        "source": "title.jpg", "start": 0.0, "end": 3.0,
        "clip_type": "image", "zoom": 1.15,
    }
    base.update(overrides)
    return ClipRef(**base)


def _vid_clip(**overrides) -> ClipRef:
    base = {"source": "a.mp4", "start": 0.0, "end": 5.0}
    base.update(overrides)
    return ClipRef(**base)


# --- DSL ------------------------------------------------------------------


class TestDSLClipType:
    def test_default_clip_type_is_video(self):
        c = ClipRef(source="a.mp4", start=0, end=5)
        assert c.clip_type == "video"

    def test_image_clip_type_persists_through_serialization(self):
        c = _img_clip()
        data = c.model_dump()
        assert data["clip_type"] == "image"
        # Roundtrip through Pydantic
        c2 = ClipRef(**data)
        assert c2.clip_type == "image"


# --- FFmpeg builder -------------------------------------------------------


class TestImageInputs:
    def test_image_clip_uses_loop_pre_args(self, storage):
        t = Timeline(format=FormatSpec(), clips=[_img_clip()])
        cmd = FFmpegCommandBuilder(t, storage).build()
        # Find the -i flag for title.jpg and verify -loop / -framerate / -t precede it.
        i_idx = next(i for i, a in enumerate(cmd) if a == "-i" and "title.jpg" in cmd[i + 1])
        # Walk backwards: -t <dur> -framerate <fps> -loop 1
        pre = cmd[:i_idx]
        assert "-loop" in pre
        assert "1" == pre[pre.index("-loop") + 1]
        assert "-framerate" in pre
        assert "-t" in pre

    def test_image_clip_emits_zoompan_with_animated_z(self, storage):
        t = Timeline(format=FormatSpec(), clips=[_img_clip(zoom=1.3)])
        cmd_str = " ".join(FFmpegCommandBuilder(t, storage).build())
        # Animated zoompan uses min(zoom+step,target). Static video zoom would
        # just say z=1.3 — image clips use the animated form.
        assert "min(zoom+" in cmd_str
        assert "zoompan=" in cmd_str

    def test_image_clip_synthesizes_silent_audio(self, storage):
        t = Timeline(format=FormatSpec(), clips=[_img_clip()])
        cmd_str = " ".join(FFmpegCommandBuilder(t, storage).build())
        assert "anullsrc=channel_layout=stereo" in cmd_str
        # Silent track is labeled like a regular audio chain so concat works
        assert "[a0]" in cmd_str

    def test_image_clips_are_NOT_deduplicated(self, storage):
        # Two image clips referring to the same file must each get their own
        # -i input, because their durations differ per clip.
        t = Timeline(
            format=FormatSpec(),
            clips=[
                _img_clip(end=2.0),
                _img_clip(end=5.0),
            ],
        )
        cmd = FFmpegCommandBuilder(t, storage).build()
        i_indices = [i for i, a in enumerate(cmd) if a == "-i"]
        sources_after_i = [cmd[i + 1] for i in i_indices]
        assert sum("title.jpg" in s for s in sources_after_i) == 2

    def test_video_clips_still_dedupe(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                _vid_clip(start=0, end=2),
                _vid_clip(start=3, end=5),
            ],
        )
        cmd = FFmpegCommandBuilder(t, storage).build()
        i_indices = [i for i, a in enumerate(cmd) if a == "-i"]
        sources_after_i = [cmd[i + 1] for i in i_indices]
        assert sum("a.mp4" in s for s in sources_after_i) == 1

    def test_mixed_image_and_video_timeline(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                _img_clip(transition_in="fade", transition_duration=0.4),
                _vid_clip(),
            ],
        )
        cmd_str = " ".join(FFmpegCommandBuilder(t, storage).build())
        # First clip: image (anullsrc, animated zoompan)
        assert "anullsrc" in cmd_str
        # Second clip: regular video (atrim from real audio stream)
        assert "atrim=0.0:5.0" in cmd_str
        # Two inputs in total
        cmd_list = cmd_str.split()
        assert cmd_list.count("-i") == 2

    def test_image_clip_skips_video_trim(self, storage):
        # Image clips don't have a `trim=...` because the input is already
        # truncated to the clip's duration via -t.
        t = Timeline(format=FormatSpec(), clips=[_img_clip(end=3.0)])
        cmd_str = " ".join(FFmpegCommandBuilder(t, storage).build())
        # No trim filter for the image
        assert "trim=0:3" not in cmd_str
        assert "trim=0.0:3.0" not in cmd_str


# --- Editing agent ---------------------------------------------------------


class TestEditingAutoImageIntros:
    def test_uploaded_images_prepended_as_intros(self, storage):
        from app.agents.editing import build_timeline

        # Seed a video and two image files
        (storage.stage_dir("raw") / "v.mp4").write_bytes(b"")
        (storage.stage_dir("raw") / "00_title.jpg").write_bytes(b"")
        (storage.stage_dir("raw") / "01_subtitle.png").write_bytes(b"")

        plan = {"style": {"width": 1920, "height": 1080, "aspect": "16:9", "energy": "medium"},
                "operations": []}
        signals = {
            "media_manifest": {
                "files": [{"filename": "v.mp4", "duration": 10.0,
                           "width": 1920, "height": 1080}],
            },
        }

        tl = build_timeline(plan, signals, storage)
        # Two image intros + one video clip
        assert len(tl.clips) == 3
        # Image clips first, in filename order
        assert tl.clips[0].clip_type == "image"
        assert tl.clips[0].source == "00_title.jpg"
        assert tl.clips[1].clip_type == "image"
        assert tl.clips[1].source == "01_subtitle.png"
        # Video clip last
        assert tl.clips[2].clip_type == "video"
        assert tl.clips[2].source == "v.mp4"

    def test_image_intros_have_default_ken_burns_zoom(self, storage):
        from app.agents.editing import build_timeline

        (storage.stage_dir("raw") / "v.mp4").write_bytes(b"")
        (storage.stage_dir("raw") / "title.jpg").write_bytes(b"")

        plan = {"style": {"width": 1920, "height": 1080, "aspect": "16:9", "energy": "medium"},
                "operations": []}
        signals = {
            "media_manifest": {
                "files": [{"filename": "v.mp4", "duration": 10.0,
                           "width": 1920, "height": 1080}],
            },
        }

        tl = build_timeline(plan, signals, storage)
        img_clip = next(c for c in tl.clips if c.clip_type == "image")
        assert img_clip.zoom > 1.0


# --- DSL validators handle image clips ------------------------------------


class TestImageClipValidation:
    def test_validate_image_clip_with_valid_duration(self, storage):
        from app.dsl.validators import validate_timeline

        (storage.stage_dir("raw") / "title.jpg").write_bytes(b"")
        t = Timeline(format=FormatSpec(), clips=[_img_clip()])
        errors = validate_timeline(t, storage)
        assert errors == []

    def test_validate_image_clip_rejects_zero_duration(self, storage):
        from app.dsl.validators import validate_timeline

        (storage.stage_dir("raw") / "title.jpg").write_bytes(b"")
        t = Timeline(format=FormatSpec(), clips=[_img_clip(end=0.0)])
        errors = validate_timeline(t, storage)
        assert any("end" in e for e in errors)
