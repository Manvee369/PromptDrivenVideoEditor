"""Tests for app/dsl/schema.py — Timeline, ClipRef, MusicTrack."""
import pytest

from app.dsl.schema import ClipRef, FormatSpec, MusicTrack, Timeline


class TestClipRef:
    def test_raw_duration(self):
        c = ClipRef(source="a.mp4", start=2.0, end=7.5)
        assert c.raw_duration == 5.5

    def test_effective_duration_normal_speed(self):
        c = ClipRef(source="a.mp4", start=0.0, end=10.0, speed=1.0)
        assert c.effective_duration == 10.0

    def test_effective_duration_double_speed(self):
        c = ClipRef(source="a.mp4", start=0.0, end=10.0, speed=2.0)
        assert c.effective_duration == 5.0

    def test_effective_duration_half_speed(self):
        c = ClipRef(source="a.mp4", start=0.0, end=10.0, speed=0.5)
        assert c.effective_duration == 20.0

    def test_effective_duration_zero_speed_falls_back(self):
        c = ClipRef(source="a.mp4", start=0.0, end=10.0, speed=0.0)
        assert c.effective_duration == 10.0


class TestTimelineDuration:
    def test_total_duration_simple_concat(self):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0.0, end=5.0),
                ClipRef(source="a.mp4", start=10.0, end=12.0),
            ],
        )
        assert t.total_duration() == 7.0

    def test_total_duration_with_crossfade_overlap(self):
        # Crossfade overlap shouldn't be double-counted in the total.
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0.0, end=5.0),
                ClipRef(
                    source="b.mp4",
                    start=0.0,
                    end=5.0,
                    transition_in="crossfade",
                    transition_duration=0.5,
                ),
            ],
        )
        assert t.total_duration() == pytest.approx(9.5)

    def test_total_duration_with_speed(self):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0.0, end=10.0, speed=2.0),  # 5s
                ClipRef(source="a.mp4", start=0.0, end=10.0, speed=0.5),  # 20s
            ],
        )
        assert t.total_duration() == pytest.approx(25.0)


class TestValidateSources:
    def test_returns_empty_when_all_present(self):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0.0, end=1.0)],
        )
        assert t.validate_sources(["a.mp4", "b.mp4"]) == []

    def test_returns_missing_clip_sources(self):
        t = Timeline(
            format=FormatSpec(),
            clips=[
                ClipRef(source="a.mp4", start=0.0, end=1.0),
                ClipRef(source="missing.mp4", start=0.0, end=1.0),
            ],
        )
        assert t.validate_sources(["a.mp4"]) == ["missing.mp4"]

    def test_returns_missing_music(self):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0.0, end=1.0)],
            music=MusicTrack(source="bg.mp3"),
        )
        assert t.validate_sources(["a.mp4"]) == ["bg.mp3"]

    def test_does_not_flag_music_when_source_none(self):
        t = Timeline(
            format=FormatSpec(),
            clips=[ClipRef(source="a.mp4", start=0.0, end=1.0)],
            music=MusicTrack(source=None),
        )
        assert t.validate_sources(["a.mp4"]) == []
