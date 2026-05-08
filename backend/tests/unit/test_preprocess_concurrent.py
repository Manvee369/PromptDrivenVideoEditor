"""Tests for concurrent media preprocessing — verify ordering and parallelism."""

from pathlib import Path
import threading
import time

import pytest

from app.jobs.preprocess import preprocess_media
from app.storage.storage_manager import StorageManager


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    sm = StorageManager(job_id="job-1", base_path=str(tmp_path))
    sm.ensure_dirs()
    return sm


def _seed_video(storage: StorageManager, name: str) -> None:
    (storage.stage_dir("raw") / name).write_bytes(b"\x00" * 16)


def _seed_audio(storage: StorageManager, name: str) -> None:
    (storage.stage_dir("raw") / name).write_bytes(b"\x00" * 16)


class TestPreprocessConcurrent:
    def test_processes_all_videos(self, storage, mocker):
        # Seed a handful of videos.
        for n in ["a.mp4", "b.mp4", "c.mp4"]:
            _seed_video(storage, n)

        mocker.patch(
            "app.jobs.preprocess.probe_media",
            return_value={"format": {"duration": "10.0"},
                          "streams": [{"codec_type": "video", "width": 1920, "height": 1080}]},
        )
        mocker.patch("app.jobs.preprocess.extract_audio")
        mocker.patch("app.jobs.preprocess.create_proxy")

        manifest = preprocess_media(storage)
        assert len(manifest["files"]) == 3
        names = [f["filename"] for f in manifest["files"]]
        assert set(names) == {"a.mp4", "b.mp4", "c.mp4"}

    def test_preserves_raw_order_in_manifest(self, storage, mocker):
        # Order in raw/ is alphabetical (sorted by storage_manager.raw_files).
        for n in ["a.mp4", "b.mp4", "c.mp4", "d.mp4"]:
            _seed_video(storage, n)

        # Make a-c slow, d fast — without index-tracking, d would land first.
        delays = {"a.mp4": 0.04, "b.mp4": 0.03, "c.mp4": 0.02, "d.mp4": 0.0}

        def slow_extract(src: Path, dst: Path):
            time.sleep(delays.get(Path(src).name, 0))
            Path(dst).write_bytes(b"")

        mocker.patch(
            "app.jobs.preprocess.probe_media",
            return_value={"format": {"duration": "5.0"},
                          "streams": [{"codec_type": "video", "width": 100, "height": 100}]},
        )
        mocker.patch("app.jobs.preprocess.extract_audio", side_effect=slow_extract)
        mocker.patch("app.jobs.preprocess.create_proxy", side_effect=lambda s, d: Path(d).write_bytes(b""))

        manifest = preprocess_media(storage)
        names = [f["filename"] for f in manifest["files"]]
        assert names == ["a.mp4", "b.mp4", "c.mp4", "d.mp4"]

    def test_runs_files_in_parallel(self, storage, mocker):
        """If processing N files takes ~N * unit_time, we're serial. With a
        thread pool, total time should be close to the slowest individual file."""
        for n in ["a.mp4", "b.mp4", "c.mp4", "d.mp4"]:
            _seed_video(storage, n)

        # Use a barrier to detect concurrent execution: all threads must
        # arrive at the barrier before any can proceed.
        barrier = threading.Barrier(parties=4, timeout=5)

        def gated_extract(src: Path, dst: Path):
            barrier.wait()  # blocks until 4 callers arrive concurrently
            Path(dst).write_bytes(b"")

        mocker.patch(
            "app.jobs.preprocess.probe_media",
            return_value={"format": {"duration": "5.0"},
                          "streams": [{"codec_type": "video", "width": 100, "height": 100}]},
        )
        mocker.patch("app.jobs.preprocess.extract_audio", side_effect=gated_extract)
        mocker.patch("app.jobs.preprocess.create_proxy", side_effect=lambda s, d: Path(d).write_bytes(b""))

        # If serial, the barrier would deadlock and the 5s timeout would fire.
        manifest = preprocess_media(storage)
        assert len(manifest["files"]) == 4

    def test_includes_standalone_audio(self, storage, mocker):
        _seed_video(storage, "v.mp4")
        _seed_audio(storage, "music.mp3")

        mocker.patch(
            "app.jobs.preprocess.probe_media",
            return_value={"format": {"duration": "10.0"},
                          "streams": [{"codec_type": "video", "width": 100, "height": 100}]},
        )
        mocker.patch("app.jobs.preprocess.extract_audio")
        mocker.patch("app.jobs.preprocess.create_proxy")
        mocker.patch("app.jobs.preprocess.get_duration", return_value=120.0)

        manifest = preprocess_media(storage)
        names = [f["filename"] for f in manifest["files"]]
        # Video first, then audio appended
        assert names == ["v.mp4", "music.mp3"]
        # Audio entry has no proxy
        assert manifest["files"][1]["proxy_path"] is None
        assert manifest["files"][1]["duration"] == 120.0

    def test_propagates_failure(self, storage, mocker):
        for n in ["a.mp4", "b.mp4"]:
            _seed_video(storage, n)

        mocker.patch(
            "app.jobs.preprocess.probe_media",
            side_effect=RuntimeError("ffprobe blew up"),
        )
        mocker.patch("app.jobs.preprocess.extract_audio")
        mocker.patch("app.jobs.preprocess.create_proxy")

        with pytest.raises(RuntimeError, match="ffprobe"):
            preprocess_media(storage)

    def test_raises_when_no_videos(self, storage):
        with pytest.raises(FileNotFoundError):
            preprocess_media(storage)
