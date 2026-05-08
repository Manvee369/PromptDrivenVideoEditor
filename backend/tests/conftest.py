"""Shared pytest fixtures for the backend test suite."""
from pathlib import Path

import pytest

from app.dsl.schema import ClipRef, FormatSpec, MusicTrack, Timeline
from app.storage.storage_manager import StorageManager


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    """A StorageManager rooted at tmp_path with all stage dirs created."""
    sm = StorageManager(job_id="test-job", base_path=str(tmp_path))
    sm.ensure_dirs()
    return sm


@pytest.fixture
def sample_format() -> FormatSpec:
    return FormatSpec(width=1920, height=1080, fps=30, aspect="16:9")


@pytest.fixture
def two_clip_timeline(sample_format: FormatSpec) -> Timeline:
    return Timeline(
        format=sample_format,
        clips=[
            ClipRef(source="a.mp4", start=0.0, end=5.0),
            ClipRef(source="a.mp4", start=10.0, end=15.0),
        ],
    )


@pytest.fixture
def crossfade_timeline(sample_format: FormatSpec) -> Timeline:
    return Timeline(
        format=sample_format,
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


@pytest.fixture
def music_timeline(sample_format: FormatSpec) -> Timeline:
    return Timeline(
        format=sample_format,
        clips=[ClipRef(source="a.mp4", start=0.0, end=5.0)],
        music=MusicTrack(source="bg.mp3", volume=0.3, fade_in=0.5, fade_out=2.0),
    )


def touch_raw(storage: StorageManager, *names: str) -> None:
    """Create empty raw files so validate_sources sees them."""
    for n in names:
        (storage.stage_dir("raw") / n).write_bytes(b"")
