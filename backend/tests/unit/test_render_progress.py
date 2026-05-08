"""Tests for ffmpeg progress parsing in render/run_render.py."""
from io import StringIO
from pathlib import Path

import pytest

from app.jobs.events import JobEvents
from app.render.run_render import _stream_progress
from app.storage.storage_manager import StorageManager


@pytest.fixture
def events(tmp_path: Path) -> JobEvents:
    sm = StorageManager(job_id="job-1", base_path=str(tmp_path))
    sm.ensure_dirs()
    return JobEvents(sm)


def _ffmpeg_progress_output(blocks: list[dict[str, str]]) -> str:
    """Synthesize the line-stream ffmpeg emits for `-progress pipe:1`."""
    out = []
    for b in blocks:
        for k, v in b.items():
            out.append(f"{k}={v}")
        out.append("")  # blank line between blocks (ffmpeg-ish)
    return "\n".join(out)


class TestStreamProgress:
    def test_emits_on_each_progress_block(self, events: JobEvents):
        # Two complete progress blocks: 50% and 100%.
        # total_dur_us = 10s = 10_000_000 us.
        text = _ffmpeg_progress_output([
            {"frame": "30", "fps": "30.0", "out_time_ms": "5000000",
             "progress": "continue"},
            {"frame": "60", "fps": "30.0", "out_time_ms": "10000000",
             "progress": "end"},
        ])
        _stream_progress(StringIO(text), events, total_dur_us=10_000_000)

        state = events.read()
        # Final block (100%) overwrites; verify final state
        assert state["substage"] == "render"
        assert state["progress"] == 1.0
        assert state["frame"] == 60
        assert state["fps"] == 30.0

    def test_clamps_progress_to_one(self, events: JobEvents):
        # Encoder reports out_time slightly past total; pct must clamp.
        text = _ffmpeg_progress_output([
            {"out_time_ms": "11000000", "progress": "end"},
        ])
        _stream_progress(StringIO(text), events, total_dur_us=10_000_000)
        assert events.read()["progress"] == 1.0

    def test_handles_zero_total_duration(self, events: JobEvents):
        # Defensive: if total_dur_us is zero, we shouldn't crash.
        text = _ffmpeg_progress_output([
            {"out_time_ms": "1000000", "progress": "end"},
        ])
        # Caller passes 0 — function should tolerate it.
        _stream_progress(StringIO(text), events, total_dur_us=0)
        # Either no emission or progress=0; both are acceptable, but no crash.
        state = events.read()
        if state:
            assert state.get("progress", 0) == 0.0

    def test_ignores_malformed_lines(self, events: JobEvents):
        text = (
            "garbage\n"
            "no_equals_sign\n"
            "frame=10\n"
            "out_time_ms=1000000\n"
            "progress=end\n"
        )
        _stream_progress(StringIO(text), events, total_dur_us=10_000_000)
        assert events.read().get("frame") == 10

    def test_stops_at_progress_end(self, events: JobEvents):
        # After "progress=end" we shouldn't process further blocks.
        text = (
            "out_time_ms=5000000\n"
            "progress=end\n"
            "out_time_ms=99999999\n"  # would be after end — should be ignored
            "progress=continue\n"
        )
        _stream_progress(StringIO(text), events, total_dur_us=10_000_000)
        # Final progress should reflect the first (and only consumed) block, not the bogus extra
        assert events.read()["progress"] == 0.5
