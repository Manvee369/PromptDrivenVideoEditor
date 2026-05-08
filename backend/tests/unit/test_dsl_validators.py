"""Tests for app/dsl/validators.py — every error path."""
import pytest

from app.dsl.schema import CaptionEntry, ClipRef, FormatSpec, MusicTrack, Timeline
from app.dsl.validators import validate_timeline
from app.storage.storage_manager import StorageManager


def _clip(**overrides) -> ClipRef:
    base = {"source": "a.mp4", "start": 0.0, "end": 5.0}
    base.update(overrides)
    return ClipRef(**base)


def _timeline(clips, **kwargs) -> Timeline:
    return Timeline(format=FormatSpec(), clips=clips, **kwargs)


def _touch(storage: StorageManager, *names: str) -> None:
    for n in names:
        (storage.stage_dir("raw") / n).write_bytes(b"")


class TestValidateTimeline:
    def test_passes_for_valid_timeline(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        assert validate_timeline(_timeline([_clip()]), storage) == []

    def test_flags_missing_source_file(self, storage: StorageManager):
        errors = validate_timeline(_timeline([_clip()]), storage)
        assert any("Source file not found: a.mp4" in e for e in errors)

    def test_flags_negative_start(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        t = _timeline([_clip(start=-1.0, end=1.0)])
        errors = validate_timeline(t, storage)
        assert any("negative start time" in e for e in errors)

    def test_flags_end_le_start(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        t = _timeline([_clip(start=5.0, end=3.0)])
        errors = validate_timeline(t, storage)
        assert any("end (3.0) must be > start (5.0)" in e for e in errors)

    def test_flags_zero_speed(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        t = _timeline([_clip(speed=0.0)])
        errors = validate_timeline(t, storage)
        assert any("speed must be positive" in e for e in errors)

    def test_flags_negative_transition_duration(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        t = _timeline([_clip(transition_duration=-0.1)])
        errors = validate_timeline(t, storage)
        assert any("negative transition duration" in e for e in errors)

    def test_flags_transition_exceeds_clip_duration(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        t = _timeline([_clip(start=0.0, end=1.0, transition_duration=2.0)])
        errors = validate_timeline(t, storage)
        assert any("transition duration exceeds clip duration" in e for e in errors)

    def test_flags_caption_negative_start(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        t = Timeline(
            format=FormatSpec(),
            clips=[_clip()],
            captions=[CaptionEntry(start=-0.5, end=1.0, text="x")],
        )
        errors = validate_timeline(t, storage)
        assert any("Caption 0: negative start time" in e for e in errors)

    def test_flags_caption_end_le_start(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        t = Timeline(
            format=FormatSpec(),
            clips=[_clip()],
            captions=[CaptionEntry(start=2.0, end=2.0, text="x")],
        )
        errors = validate_timeline(t, storage)
        assert any("Caption 0: end must be > start" in e for e in errors)

    def test_flags_invalid_dimensions(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        t = Timeline(
            format=FormatSpec(width=0, height=1080, fps=30),
            clips=[_clip()],
        )
        errors = validate_timeline(t, storage)
        assert any("width and height must be positive" in e for e in errors)

    def test_flags_invalid_fps(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        t = Timeline(
            format=FormatSpec(width=1920, height=1080, fps=0),
            clips=[_clip()],
        )
        errors = validate_timeline(t, storage)
        assert any("fps must be positive" in e for e in errors)

    def test_flags_missing_music_source(self, storage: StorageManager):
        _touch(storage, "a.mp4")
        t = Timeline(
            format=FormatSpec(),
            clips=[_clip()],
            music=MusicTrack(source="bg.mp3"),
        )
        errors = validate_timeline(t, storage)
        assert any("Source file not found: bg.mp3" in e for e in errors)

    def test_collects_multiple_errors(self, storage: StorageManager):
        # Missing file + negative start + bad fps — all should appear.
        t = Timeline(
            format=FormatSpec(width=1920, height=1080, fps=0),
            clips=[_clip(start=-1.0, end=1.0)],
        )
        errors = validate_timeline(t, storage)
        assert len(errors) >= 3
