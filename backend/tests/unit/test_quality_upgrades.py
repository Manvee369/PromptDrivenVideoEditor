"""Tests for the quality upgrade batch (#1, #2, #3, #4, #5, #7, #8)."""

from pathlib import Path

import pytest

from app.agents.captions import (
    STYLE_PRESETS,
    _generate_karaoke_lines,
    generate_ass_file,
)
from app.dsl.schema import (
    CaptionEntry,
    ClipRef,
    FormatSpec,
    MusicTrack,
    Timeline,
)
from app.render.color_grading import (
    COLOR_GRADE_PRESET_NAMES,
    filter_for_preset,
)
from app.render.ffmpeg_builder import FFmpegCommandBuilder
from app.storage.storage_manager import StorageManager


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    sm = StorageManager(job_id="job-1", base_path=str(tmp_path))
    sm.ensure_dirs()
    return sm


def _cmd_str(timeline: Timeline, storage: StorageManager) -> str:
    return " ".join(FFmpegCommandBuilder(timeline, storage).build())


# --- #1 Audio loudness normalization --------------------------------------


class TestLoudnorm:
    def test_loudnorm_in_filtergraph(self, storage):
        t = Timeline(format=FormatSpec(), clips=[ClipRef(source="a.mp4", start=0, end=5)])
        s = _cmd_str(t, storage)
        assert "loudnorm=I=-14.0" in s
        assert "[normalized]" in s

    def test_loudnorm_can_be_disabled(self, storage, monkeypatch):
        monkeypatch.setattr("app.core.config.settings.loudnorm_target_lufs", 0)
        t = Timeline(format=FormatSpec(), clips=[ClipRef(source="a.mp4", start=0, end=5)])
        s = _cmd_str(t, storage)
        # Use "loudnorm=" (with equals) since the test name "loudnorm" can
        # appear in the pytest temp path.
        assert "loudnorm=" not in s


# --- #5 Color grading -----------------------------------------------------


class TestColorGrade:
    def test_preset_filter_lookup(self):
        assert filter_for_preset("cinematic") != ""
        assert filter_for_preset("none") == ""
        assert filter_for_preset(None) == ""
        assert filter_for_preset("nonexistent") == ""

    def test_clip_color_grade_appears_in_chain(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5, color_grade="cinematic")],
        )
        s = _cmd_str(t, storage)
        assert "colorbalance=" in s

    def test_timeline_default_grade_applied_to_all_clips(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0, end=5),
                ClipRef(source="a.mp4", start=10, end=15),
            ],
            color_grade="warm",
        )
        s = _cmd_str(t, storage)
        # Warm preset uses colorbalance — should appear at least twice (one per clip)
        assert s.count("colorbalance=rh=0.12") >= 2

    def test_clip_grade_overrides_timeline_grade(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5, color_grade="bw")],
            color_grade="cinematic",
        )
        s = _cmd_str(t, storage)
        # B&W preset has colorchannelmixer; cinematic doesn't.
        assert "colorchannelmixer" in s

    def test_all_presets_are_buildable(self):
        # Sanity: every advertised preset name resolves to either "" or a string
        for name in COLOR_GRADE_PRESET_NAMES:
            assert filter_for_preset(name) is not None


# --- #2 Smart crop --------------------------------------------------------


class TestSmartCrop:
    def test_crop_box_emits_filter(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(
                source="a.mp4", start=0, end=5,
                crop_box={"w": 0.5625, "h": 1.0, "x": 0.2, "y": 0.0},
            )],
        )
        s = _cmd_str(t, storage)
        assert "crop=iw*0.5625:ih*1.0" in s
        assert "iw*0.2" in s

    def test_no_crop_when_unset(self, storage):
        t = Timeline(format=FormatSpec(), clips=[ClipRef(source="a.mp4", start=0, end=5)])
        s = _cmd_str(t, storage)
        # No crop= in filtergraph — pad-only path
        assert "crop=iw" not in s

    def test_editing_agent_centers_crop_on_face(self, storage):
        from app.agents.editing import build_timeline

        # 16:9 source, target 9:16 → smart crop should engage
        (storage.stage_dir("raw") / "v.mp4").write_bytes(b"")

        plan = {
            "style": {"width": 1080, "height": 1920, "aspect": "9:16", "energy": "medium"},
            "operations": [],
        }
        signals = {
            "media_manifest": {
                "files": [{"filename": "v.mp4", "duration": 10.0,
                           "width": 1920, "height": 1080}],
            },
            "faces": {
                "tracks": [{
                    "source": "v.mp4",
                    "detections": [
                        # Face at x=0.7 (right side of frame) for the whole clip
                        {"time": 1.0, "boxes": [{"x": 0.6, "y": 0.3, "w": 0.2, "h": 0.4}]},
                        {"time": 5.0, "boxes": [{"x": 0.6, "y": 0.3, "w": 0.2, "h": 0.4}]},
                    ],
                }],
            },
        }

        tl = build_timeline(plan, signals, storage)
        # Single clip from full source 0–10s
        assert len(tl.clips) == 1
        cb = tl.clips[0].crop_box
        assert cb is not None
        # Source 16:9, target 9:16. Crop width as fraction of source width =
        # target_aspect / source_aspect = (9/16) / (16/9) = 0.3164
        assert abs(cb["w"] - 0.3164) < 0.001
        assert cb["h"] == 1.0
        # Face center is at x=0.7 → crop should be shifted right
        assert cb["x"] > 0.4

    def test_editing_agent_skips_crop_for_image_clips(self, storage):
        from app.agents.editing import build_timeline

        (storage.stage_dir("raw") / "v.mp4").write_bytes(b"")
        (storage.stage_dir("raw") / "title.jpg").write_bytes(b"")

        plan = {
            "style": {"width": 1080, "height": 1920, "aspect": "9:16", "energy": "medium"},
            "operations": [],
        }
        signals = {
            "media_manifest": {
                "files": [{"filename": "v.mp4", "duration": 10.0,
                           "width": 1920, "height": 1080}],
            },
            "faces": {"tracks": []},
        }
        tl = build_timeline(plan, signals, storage)
        image_clip = next(c for c in tl.clips if c.clip_type == "image")
        assert image_clip.crop_box is None


# --- #7 New transition types ---------------------------------------------


class TestNewTransitions:
    def test_zoom_transition_uses_zoomin_xfade(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0, end=5),
                ClipRef(source="b.mp4", start=0, end=5,
                        transition_in="zoom", transition_duration=0.6),
            ],
        )
        s = _cmd_str(t, storage)
        assert "xfade=transition=zoomin:duration=0.6" in s

    def test_whip_transition_uses_slideleft(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0, end=5),
                ClipRef(source="b.mp4", start=0, end=5,
                        transition_in="whip", transition_duration=0.4),
            ],
        )
        s = _cmd_str(t, storage)
        assert "xfade=transition=slideleft:duration=0.4" in s

    def test_crossfade_still_uses_fade(self, storage):
        # Backward compat: crossfade → fade transition
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0, end=5),
                ClipRef(source="b.mp4", start=0, end=5,
                        transition_in="crossfade", transition_duration=0.5),
            ],
        )
        s = _cmd_str(t, storage)
        assert "xfade=transition=fade:duration=0.5" in s


# --- #8 Audio cut smoothing ----------------------------------------------


class TestAudioCutSmoothing:
    def test_smoothing_fade_in_on_non_first_clips(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0, end=5),
                ClipRef(source="a.mp4", start=10, end=15),  # hard cut, no transition
            ],
        )
        s = _cmd_str(t, storage)
        # 50ms tiny smoothing fade-in on the second clip
        assert "afade=t=in:d=0.05" in s

    def test_smoothing_fade_out_on_clip_end(self, storage):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
        )
        s = _cmd_str(t, storage)
        # afade=t=out near the end of the clip (5 - 0.05 = 4.95)
        assert "afade=t=out:st=4.95:d=0.05" in s

    def test_no_smoothing_fade_in_on_first_clip(self, storage):
        # First clip should not get a fade-in unless transition asks for it.
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
        )
        cmd = FFmpegCommandBuilder(t, storage).build()
        # The single clip's audio chain should not have afade=t=in (smoothing
        # is gated by i > 0). Find the [a0] chain and check.
        s = " ".join(cmd)
        # We can't easily isolate the first clip's a-chain from the joined
        # string, but for a one-clip timeline there's no fade-in by definition.
        # Just verify the start of the audio chain has no fade-in:
        assert "asetpts=PTS-STARTPTS,afade=t=in" not in s


# --- #3 Karaoke captions --------------------------------------------------


class TestKaraokeCaptions:
    def test_karaoke_in_style_presets(self):
        assert "karaoke" in STYLE_PRESETS

    def test_karaoke_lines_use_word_data(self):
        cap = CaptionEntry(
            start=0.0, end=2.0,
            text="Hello world",
            words=[
                {"start": 0.0, "end": 0.5, "text": "Hello", "probability": 0.95},
                {"start": 0.6, "end": 1.4, "text": "world", "probability": 0.93},
            ],
        )
        lines = _generate_karaoke_lines([cap])
        assert len(lines) == 1
        # \k50 = 50 centiseconds for "Hello" (0.5s); \k80 = 80cs for "world" (0.8s)
        assert "\\k50" in lines[0]
        assert "\\k80" in lines[0]
        assert "Hello" in lines[0]
        assert "world" in lines[0]

    def test_karaoke_falls_back_to_even_split_without_words(self):
        cap = CaptionEntry(start=0.0, end=2.0, text="Hello world")
        lines = _generate_karaoke_lines([cap])
        # Fallback splits 2s evenly across 2 words → 1s each → \k100
        assert "\\k100" in lines[0]

    def test_karaoke_hype_words_get_color(self):
        cap = CaptionEntry(
            start=0.0, end=1.0,
            text="that's amazing",
            words=[
                {"start": 0.0, "end": 0.3, "text": "that's", "probability": 0.95},
                {"start": 0.4, "end": 0.9, "text": "amazing", "probability": 0.95},
            ],
        )
        lines = _generate_karaoke_lines([cap])
        # Yellow color override on hype word
        assert "\\c&H00FFFF&" in lines[0]


# --- #4 Beat-synced caption emphasis -------------------------------------


class TestBeatSyncCaptions:
    def test_word_on_beat_gets_scale_pulse(self):
        cap = CaptionEntry(
            start=0.0, end=2.0,
            text="hello world",
            words=[
                {"start": 0.5, "end": 1.0, "text": "hello", "probability": 0.95},
                {"start": 1.1, "end": 1.5, "text": "world", "probability": 0.95},
            ],
        )
        # Beat at 0.5 — exactly when "hello" starts
        lines = _generate_karaoke_lines([cap], beats=[0.5])
        assert "\\fscx120\\fscy120" in lines[0]

    def test_word_off_beat_unchanged(self):
        cap = CaptionEntry(
            start=0.0, end=2.0,
            text="hello",
            words=[
                {"start": 0.5, "end": 1.0, "text": "hello", "probability": 0.95},
            ],
        )
        # Beats far from any word
        lines = _generate_karaoke_lines([cap], beats=[5.0, 10.0])
        # No scale pulse
        assert "\\fscx120" not in lines[0]

    def test_hype_word_on_beat_gets_bigger_scale(self):
        cap = CaptionEntry(
            start=0.0, end=2.0,
            text="amazing",
            words=[
                {"start": 0.5, "end": 1.0, "text": "amazing", "probability": 0.95},
            ],
        )
        lines = _generate_karaoke_lines([cap], beats=[0.5])
        # Bigger scale for hype + beat combination
        assert "\\fscx135\\fscy135" in lines[0]


# --- generate_ass_file karaoke dispatch ---------------------------------


class TestGenerateAssKaraoke:
    def test_karaoke_style_dispatches_to_karaoke_generator(self, tmp_path):
        cap = CaptionEntry(
            start=0.0, end=2.0,
            text="hello world",
            words=[
                {"start": 0.0, "end": 0.5, "text": "hello", "probability": 0.95},
                {"start": 0.6, "end": 1.4, "text": "world", "probability": 0.95},
            ],
        )
        out = tmp_path / "captions.ass"
        generate_ass_file([cap], out, style_name="karaoke")
        text = out.read_text(encoding="utf-8")
        # \k tags only appear in karaoke output
        assert "\\k" in text
        # Karaoke style uses yellow secondary color
        assert "&H0000FFFF" in text
