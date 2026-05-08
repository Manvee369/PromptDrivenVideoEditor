"""Tests for app/agents/editing.py — Timeline construction helpers."""
import pytest

from app.agents.editing import (
    _apply_transitions,
    _beat_sync_clips,
    _trim_to_duration,
)
from app.dsl.schema import ClipRef


def _clip(start=0.0, end=5.0, **kwargs) -> ClipRef:
    return ClipRef(source="a.mp4", start=start, end=end, **kwargs)


class TestTrimToDuration:
    def test_returns_unchanged_when_under_target(self):
        clips = [_clip(0, 5), _clip(0, 5)]
        result = _trim_to_duration(clips, target=20.0)
        assert len(result) == 2
        assert sum(c.effective_duration for c in result) == 10.0

    def test_drops_clips_that_dont_fit(self):
        clips = [_clip(0, 5), _clip(0, 5), _clip(0, 5)]
        result = _trim_to_duration(clips, target=8.0)
        assert len(result) == 2
        assert result[0].effective_duration == 5.0
        assert result[1].effective_duration == pytest.approx(3.0)

    def test_partially_trims_last_clip(self):
        clips = [_clip(0, 5), _clip(2, 12)]
        result = _trim_to_duration(clips, target=8.0)
        assert sum(c.effective_duration for c in result) == pytest.approx(8.0)

    def test_empty_clips_list(self):
        assert _trim_to_duration([], target=10.0) == []


class TestApplyTransitions:
    def test_returns_unchanged_for_single_clip(self):
        clips = [_clip(0, 5)]
        plan = {"style": {"energy": "medium"}}
        assert _apply_transitions(clips, plan) == clips

    def test_first_clip_gets_fade_in(self):
        clips = [_clip(0, 5), _clip(0, 5)]
        plan = {"style": {"energy": "medium"}}
        result = _apply_transitions(clips, plan)
        assert result[0].transition_in == "fade"
        assert result[0].transition_duration == 0.5

    def test_low_energy_uses_long_crossfade(self):
        clips = [_clip(0, 5), _clip(0, 5), _clip(0, 5)]
        plan = {"style": {"energy": "low"}}
        result = _apply_transitions(clips, plan)
        assert result[1].transition_in == "crossfade"
        assert result[1].transition_duration == 0.8

    def test_medium_energy_uses_standard_crossfade(self):
        clips = [_clip(0, 5), _clip(0, 5)]
        plan = {"style": {"energy": "medium"}}
        result = _apply_transitions(clips, plan)
        assert result[1].transition_in == "crossfade"
        assert result[1].transition_duration == 0.5

    def test_high_energy_alternates_flash_and_crossfade(self):
        clips = [_clip(0, 5) for _ in range(8)]
        plan = {"style": {"energy": "high"}}
        result = _apply_transitions(clips, plan)
        # i=4 hits the i % 4 == 0 branch (and i > 0)
        assert result[4].transition_in == "flash"
        # Other non-first positions are crossfades
        assert result[1].transition_in == "crossfade"
        assert result[2].transition_in == "crossfade"

    def test_none_style_skips_transitions(self):
        clips = [_clip(0, 5), _clip(0, 5)]
        plan = {"style": {"energy": "high", "transitions": "none"}}
        result = _apply_transitions(clips, plan)
        for c in result:
            assert c.transition_in is None


class TestBeatSyncClips:
    def test_snaps_clip_to_nearby_beat(self):
        # clip ends at 5.0; beat at 4.9 is within the 0.25s adjust window
        clips = [_clip(0.0, 5.0)]
        beats = [4.9, 9.8]
        result = _beat_sync_clips(clips, beats)
        assert result[0].end == pytest.approx(4.9, abs=0.001)

    def test_leaves_clip_alone_when_no_beat_in_window(self):
        # nearest beat to 5.0 is 3.0 (2s away) — outside the 0.25s window
        clips = [_clip(0.0, 5.0)]
        beats = [3.0, 8.0]
        result = _beat_sync_clips(clips, beats)
        assert result[0].end == 5.0

    def test_skips_when_adjusted_duration_too_small(self):
        # nearest beat would shift duration to 0.2s — below 0.5s minimum
        clips = [_clip(0.0, 1.0)]
        beats = [0.2, 5.0]
        result = _beat_sync_clips(clips, beats)
        assert result[0].end == 1.0

    def test_preserves_clip_attributes_when_adjusting(self):
        clips = [_clip(0.0, 5.0, speed=2.0, volume=0.7)]
        beats = [2.45]  # would map output 5.0 → beat at 2.45 → too far, unchanged
        result = _beat_sync_clips(clips, beats)
        # Clip is unchanged; speed/volume preserved
        assert result[0].speed == 2.0
        assert result[0].volume == 0.7
