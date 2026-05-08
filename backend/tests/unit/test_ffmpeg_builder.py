"""Tests for app/render/ffmpeg_builder.py — FFmpeg command generation.

These tests assert the structure of the emitted FFmpeg argv without ever
executing FFmpeg. They lock in the filtergraph contract so future refactors
can't silently break rendering.
"""
import pytest

from app.dsl.schema import CaptionEntry, ClipRef, FormatSpec, MusicTrack, Timeline
from app.render.ffmpeg_builder import FFmpegCommandBuilder
from app.storage.storage_manager import StorageManager


def _cmd_str(timeline: Timeline, storage: StorageManager) -> str:
    return " ".join(FFmpegCommandBuilder(timeline, storage).build())


def _cmd(timeline: Timeline, storage: StorageManager) -> list[str]:
    return FFmpegCommandBuilder(timeline, storage).build()


class TestErrors:
    def test_raises_on_empty_clip_list(self, storage: StorageManager):
        t = Timeline(format=FormatSpec(), clips=[])
        with pytest.raises(ValueError, match="no clips"):
            FFmpegCommandBuilder(t, storage).build()


class TestStructure:
    def test_starts_with_ffmpeg(self, storage: StorageManager):
        t = Timeline(format=FormatSpec(), clips=[ClipRef(source="a.mp4", start=0, end=5)])
        cmd = _cmd(t, storage)
        assert cmd[0] == "ffmpeg"

    def test_output_path_is_final_mp4(self, storage: StorageManager):
        t = Timeline(format=FormatSpec(), clips=[ClipRef(source="a.mp4", start=0, end=5)])
        cmd = _cmd(t, storage)
        assert cmd[-1].endswith("final.mp4")

    def test_video_encoding_uses_libx264_with_faststart(self, storage: StorageManager):
        t = Timeline(format=FormatSpec(), clips=[ClipRef(source="a.mp4", start=0, end=5)])
        s = _cmd_str(t, storage)
        assert "libx264" in s
        assert "+faststart" in s
        assert "aac" in s


class TestInputs:
    def test_dedupes_input_files(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0, end=5),
                ClipRef(source="a.mp4", start=10, end=15),
            ],
        )
        cmd = _cmd(t, storage)
        i_positions = [i for i, arg in enumerate(cmd) if arg == "-i"]
        sources = [cmd[i + 1] for i in i_positions]
        assert sum("a.mp4" in s for s in sources) == 1

    def test_emits_one_input_per_unique_source(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0, end=5),
                ClipRef(source="b.mp4", start=0, end=5),
            ],
        )
        cmd = _cmd(t, storage)
        i_positions = [i for i, arg in enumerate(cmd) if arg == "-i"]
        assert len(i_positions) == 2


class TestClipChains:
    def test_includes_trim_for_each_clip(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=2.5, end=7.0)],
        )
        s = _cmd_str(t, storage)
        assert "trim=2.5:7.0" in s
        assert "atrim=2.5:7.0" in s

    def test_speed_emits_setpts_and_atempo(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5, speed=2.0)],
        )
        s = _cmd_str(t, storage)
        assert "setpts=PTS/2.0" in s
        assert "atempo=2.0" in s

    def test_speed_one_omits_setpts_modifier(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5, speed=1.0)],
        )
        s = _cmd_str(t, storage)
        # The base setpts=PTS-STARTPTS still appears, but no PTS/{speed} modifier
        assert "setpts=PTS/" not in s
        assert "atempo" not in s

    def test_volume_emitted_when_non_default(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5, volume=0.5)],
        )
        assert "volume=0.5" in _cmd_str(t, storage)

    def test_zoom_emits_zoompan(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5, zoom=1.3)],
        )
        assert "zoompan=z=1.3" in _cmd_str(t, storage)

    def test_no_zoompan_when_zoom_is_one(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5, zoom=1.0)],
        )
        # Use "zoompan=" with equals sign — the bare word "zoompan"
        # may also appear in the test name embedded in the tmp path.
        assert "zoompan=" not in _cmd_str(t, storage)

    def test_custom_filters_appended(self, storage: StorageManager):
        bw = "colorchannelmixer=.3:.4:.3:0:.3:.4:.3:0:.3:.4:.3"
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5, filters=[bw])],
        )
        assert bw in _cmd_str(t, storage)


class TestConcatVsCrossfade:
    def test_uses_concat_when_no_crossfade(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0, end=5),
                ClipRef(source="a.mp4", start=10, end=15),
            ],
        )
        s = _cmd_str(t, storage)
        assert "concat=n=2:v=1:a=1" in s
        assert "xfade" not in s

    def test_uses_xfade_when_crossfade_requested(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0, end=5),
                ClipRef(
                    source="b.mp4", start=0, end=5,
                    transition_in="crossfade", transition_duration=0.5,
                ),
            ],
        )
        s = _cmd_str(t, storage)
        assert "xfade=transition=fade:duration=0.5" in s
        assert "acrossfade=d=0.5" in s

    def test_clamps_xfade_duration_to_half_clip(self, storage: StorageManager):
        # Both clips are 1.0s — transition_duration=2.0 must clamp to ~0.5.
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0, end=1.0),
                ClipRef(
                    source="b.mp4", start=0, end=1.0,
                    transition_in="crossfade", transition_duration=2.0,
                ),
            ],
        )
        assert "duration=0.5" in _cmd_str(t, storage)


class TestMusicMixing:
    def test_music_track_mixed_in(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
            music=MusicTrack(source="bg.mp3", volume=0.3, fade_in=0.5, fade_out=2.0),
        )
        s = _cmd_str(t, storage)
        assert "bg.mp3" in s
        assert "amix=inputs=2:duration=first[mixed]" in s
        assert "afade=t=in:d=0.5" in s

    def test_music_added_as_input(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
            music=MusicTrack(source="bg.mp3"),
        )
        cmd = _cmd(t, storage)
        # bg.mp3 must appear after a -i flag
        i_positions = [i for i, arg in enumerate(cmd) if arg == "-i"]
        sources = [cmd[i + 1] for i in i_positions]
        assert any("bg.mp3" in s for s in sources)

    def test_no_music_when_source_none(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
            music=MusicTrack(source=None),
        )
        s = _cmd_str(t, storage)
        assert "amix" not in s


class TestSubtitles:
    def test_subtitles_added_when_ass_file_exists(self, storage: StorageManager):
        ass_path = storage.render_path("captions.ass")
        ass_path.parent.mkdir(parents=True, exist_ok=True)
        ass_path.write_text("[Script Info]\n", encoding="utf-8")

        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
        )
        s = _cmd_str(t, storage)
        assert "ass='" in s
        assert "[subbed]" in s

    def test_no_subtitles_when_ass_file_missing(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
        )
        s = _cmd_str(t, storage)
        assert "ass=" not in s
        assert "[subbed]" not in s


class TestFormatHonored:
    def test_scale_uses_format_dimensions(self, storage: StorageManager):
        t = Timeline(
            format=FormatSpec(width=1080, height=1920, fps=60, aspect="9:16"),
            clips=[ClipRef(source="a.mp4", start=0, end=5)],
        )
        s = _cmd_str(t, storage)
        assert "scale=1080:1920" in s
        assert "fps=60" in s
