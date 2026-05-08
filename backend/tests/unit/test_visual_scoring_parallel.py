"""Tests for parallel keyframe extraction in visual_scoring."""

import threading
import time

import numpy as np
import pytest


def _import_extractor():
    from app.intelligence.visual_scoring import _extract_keyframes_parallel
    return _extract_keyframes_parallel


class TestExtractKeyframesParallel:
    def test_preserves_input_order(self, mocker):
        _extract_keyframes_parallel = _import_extractor()
        times = [1.0, 2.5, 3.7, 4.0]

        def fake_extract(path, t):
            return np.full((10, 10, 3), int(t * 10), dtype=np.uint8)

        mocker.patch("app.intelligence.visual_scoring._extract_keyframe",
                     side_effect=fake_extract)

        result = _extract_keyframes_parallel("dummy.mp4", times)
        assert [r[0] for r in result] == times
        # Each frame's content encodes its time → verify ordering is correct
        for t, frame in result:
            assert frame[0, 0, 0] == int(t * 10)

    def test_runs_in_parallel(self, mocker):
        """Verify multiple extractions overlap in time using a barrier."""
        _extract_keyframes_parallel = _import_extractor()
        times = [1.0, 2.0, 3.0, 4.0]
        barrier = threading.Barrier(parties=4, timeout=5)

        def gated_extract(path, t):
            barrier.wait()  # all 4 must arrive concurrently
            return np.zeros((10, 10, 3), dtype=np.uint8)

        mocker.patch("app.intelligence.visual_scoring._extract_keyframe",
                     side_effect=gated_extract)

        # Would deadlock + timeout if serial.
        result = _extract_keyframes_parallel("dummy.mp4", times)
        assert len(result) == 4

    def test_handles_decode_failures(self, mocker):
        _extract_keyframes_parallel = _import_extractor()
        times = [1.0, 2.0, 3.0]

        def fake_extract(path, t):
            return None if t == 2.0 else np.zeros((1, 1, 3), dtype=np.uint8)

        mocker.patch("app.intelligence.visual_scoring._extract_keyframe",
                     side_effect=fake_extract)

        result = _extract_keyframes_parallel("dummy.mp4", times)
        assert result[0][1] is not None
        assert result[1][1] is None  # decode failure preserved
        assert result[2][1] is not None

    def test_empty_times_returns_empty(self):
        _extract_keyframes_parallel = _import_extractor()
        assert _extract_keyframes_parallel("dummy.mp4", []) == []
