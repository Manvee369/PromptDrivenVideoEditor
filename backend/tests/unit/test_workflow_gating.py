"""Tests for workflow gating — which intelligence stages are required."""

from app.jobs.workflow import (
    SIMPLE_OPERATIONS,
    is_simple_workflow,
    required_signals,
)


class TestIsSimpleWorkflow:
    def test_remove_silence_only_is_simple(self):
        assert is_simple_workflow({"remove_silence"}) is True

    def test_captions_and_bw_is_simple(self):
        assert is_simple_workflow({"add_captions", "black_and_white"}) is True

    def test_highlight_select_is_not_simple(self):
        assert is_simple_workflow({"remove_silence", "highlight_select"}) is False

    def test_story_compose_is_not_simple(self):
        assert is_simple_workflow({"story_compose"}) is False

    def test_beat_sync_is_not_simple(self):
        # beat_sync needs music analysis — keep it on the full path.
        assert is_simple_workflow({"beat_sync"}) is False

    def test_empty_operations_is_not_simple(self):
        # No operations to perform — fast path doesn't apply.
        assert is_simple_workflow(set()) is False


class TestRequiredSignals:
    def test_minimum_set(self):
        # Even with no operations, we always run transcript + silence + manifest.
        needed = required_signals(set())
        assert {"media_manifest", "transcript", "silence"}.issubset(needed)

    def test_simple_prompt_skips_heavy_stages(self):
        # Just B&W — should NOT need motion, faces, shots, visual, diarization.
        needed = required_signals({"black_and_white"})
        assert "visual_scores" not in needed
        assert "motion" not in needed
        assert "faces" not in needed
        assert "shots" not in needed
        assert "diarization" not in needed
        assert "music_analysis" not in needed

    def test_highlight_select_pulls_in_full_intelligence(self):
        needed = required_signals({"highlight_select"})
        assert {"motion", "faces", "shots", "visual_scores", "audio_energy"}.issubset(needed)

    def test_story_compose_needs_shots(self):
        needed = required_signals({"story_compose"})
        assert "shots" in needed

    def test_beat_sync_needs_music_analysis(self):
        needed = required_signals({"beat_sync"})
        assert "music_analysis" in needed

    def test_captions_needs_diarization_for_speaker_tags(self):
        needed = required_signals({"add_captions"})
        assert "diarization" in needed

    def test_remove_silence_needs_audio_energy(self):
        needed = required_signals({"remove_silence"})
        assert "audio_energy" in needed

    def test_simple_operations_constant_is_frozen(self):
        # The operations classified as "simple" should be exactly the public set.
        # If someone adds a new transform, they must update SIMPLE_OPERATIONS.
        assert "remove_silence" in SIMPLE_OPERATIONS
        assert "highlight_select" not in SIMPLE_OPERATIONS
        assert isinstance(SIMPLE_OPERATIONS, frozenset)
