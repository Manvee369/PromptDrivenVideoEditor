"""Tests for pipeline cache helpers — signals/plans loaded from disk
when present (skipping the compute), recomputed when absent or force=True.

We test the helpers directly to avoid importing the full pipeline module,
which transitively pulls in Whisper, Torch, etc.
"""
import pytest

from app.storage.storage_manager import StorageManager


def _import_helpers():
    """Import inside a function to defer the heavy pipeline import until
    tests actually run, and so any import failure surfaces cleanly."""
    from app.jobs.pipeline import _cached_plan, _cached_signal
    return _cached_signal, _cached_plan


class TestCachedSignal:
    def test_calls_compute_when_not_cached(self, storage: StorageManager):
        _cached_signal, _ = _import_helpers()
        called = {"n": 0}

        def compute():
            called["n"] += 1
            return {"hello": "world"}

        result = _cached_signal(storage, "job-1", "shots", compute, force=False)
        assert called["n"] == 1
        assert result == {"hello": "world"}

    def test_loads_from_disk_when_cached(self, storage: StorageManager):
        _cached_signal, _ = _import_helpers()
        # Pre-populate the cached file
        storage.save_signal("shots", {"cached": True, "tracks": []})

        called = {"n": 0}

        def compute():
            called["n"] += 1
            return {"cached": False}

        result = _cached_signal(storage, "job-1", "shots", compute, force=False)
        assert called["n"] == 0  # compute NOT called
        assert result == {"cached": True, "tracks": []}

    def test_force_recomputes_even_when_cached(self, storage: StorageManager):
        _cached_signal, _ = _import_helpers()
        storage.save_signal("shots", {"old": True})

        called = {"n": 0}

        def compute():
            called["n"] += 1
            return {"fresh": True}

        result = _cached_signal(storage, "job-1", "shots", compute, force=True)
        assert called["n"] == 1
        assert result == {"fresh": True}


class TestCachedPlan:
    def test_calls_compute_when_not_cached(self, storage: StorageManager):
        _, _cached_plan = _import_helpers()
        called = {"n": 0}

        def compute():
            called["n"] += 1
            return {"plan": "v1"}

        result = _cached_plan(storage, "job-1", "highlights", compute, force=False)
        assert called["n"] == 1
        assert result == {"plan": "v1"}

    def test_loads_from_disk_when_cached(self, storage: StorageManager):
        _, _cached_plan = _import_helpers()
        storage.save_plan("highlights", {"cached_plan": True})

        called = {"n": 0}

        def compute():
            called["n"] += 1
            return {"cached_plan": False}

        result = _cached_plan(storage, "job-1", "highlights", compute, force=False)
        assert called["n"] == 0
        assert result == {"cached_plan": True}

    def test_force_recomputes(self, storage: StorageManager):
        _, _cached_plan = _import_helpers()
        storage.save_plan("highlights", {"v": 1})

        called = {"n": 0}

        def compute():
            called["n"] += 1
            return {"v": 2}

        result = _cached_plan(storage, "job-1", "highlights", compute, force=True)
        assert called["n"] == 1
        assert result == {"v": 2}
