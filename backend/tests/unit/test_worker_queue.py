"""Tests for the queue glue — RQ when reachable, BackgroundTasks fallback."""
import pytest

from app.worker import queue as queue_mod


@pytest.fixture(autouse=True)
def reset_queue_state():
    """Each test starts with a clean Redis-probe cache."""
    queue_mod.reset_connection_cache()
    yield
    queue_mod.reset_connection_cache()


def _noop(*args, **kwargs):
    pass


class TestQueueAvailable:
    def test_disabled_in_settings_returns_false(self, monkeypatch):
        monkeypatch.setattr("app.worker.queue.settings.queue_enabled", False)
        assert queue_mod.queue_available() is False

    def test_enabled_but_redis_unreachable_returns_false(self, monkeypatch, mocker):
        monkeypatch.setattr("app.worker.queue.settings.queue_enabled", True)
        # Force the redis client constructor to raise
        bad_client = mocker.MagicMock()
        bad_client.ping.side_effect = ConnectionError("nope")
        mocker.patch("redis.Redis.from_url", return_value=bad_client)
        assert queue_mod.queue_available() is False

    def test_enabled_and_redis_reachable_returns_true(self, monkeypatch, mocker):
        monkeypatch.setattr("app.worker.queue.settings.queue_enabled", True)
        good_client = mocker.MagicMock()
        good_client.ping.return_value = True
        mocker.patch("redis.Redis.from_url", return_value=good_client)
        assert queue_mod.queue_available() is True


class TestEnqueueFallback:
    def test_calls_fallback_when_queue_disabled(self, monkeypatch):
        monkeypatch.setattr("app.worker.queue.settings.queue_enabled", False)

        called = {"target": None, "args": None}
        def fallback(target, *args, **kwargs):
            called["target"] = target
            called["args"] = args

        result = queue_mod.enqueue(_noop, "a", "b", fallback_add_task=fallback)
        assert result == "inline"
        assert called["target"] is _noop
        assert called["args"] == ("a", "b")

    def test_runs_inline_when_no_fallback_provided(self, monkeypatch):
        monkeypatch.setattr("app.worker.queue.settings.queue_enabled", False)

        ran = {"n": 0}
        def target():
            ran["n"] += 1

        result = queue_mod.enqueue(target)
        assert result == "inline"
        assert ran["n"] == 1


class TestEnqueueRedis:
    def test_uses_rq_when_redis_reachable(self, monkeypatch, mocker):
        monkeypatch.setattr("app.worker.queue.settings.queue_enabled", True)

        # Reachable Redis stub
        good_client = mocker.MagicMock()
        good_client.ping.return_value = True
        mocker.patch("redis.Redis.from_url", return_value=good_client)

        # Stub RQ Queue — return a job with a known id
        fake_job = mocker.MagicMock(id="rq-job-123")
        fake_queue = mocker.MagicMock()
        fake_queue.enqueue.return_value = fake_job
        mocker.patch("rq.Queue", return_value=fake_queue)

        # Fallback should NOT be called when RQ is used
        called_fallback = {"n": 0}
        def fallback(*a, **k):
            called_fallback["n"] += 1

        result = queue_mod.enqueue(_noop, "x", fallback_add_task=fallback)
        assert result == "rq-job-123"
        fake_queue.enqueue.assert_called_once()
        assert called_fallback["n"] == 0

    def test_falls_back_when_rq_enqueue_raises(self, monkeypatch, mocker):
        monkeypatch.setattr("app.worker.queue.settings.queue_enabled", True)

        good_client = mocker.MagicMock()
        good_client.ping.return_value = True
        mocker.patch("redis.Redis.from_url", return_value=good_client)

        fake_queue = mocker.MagicMock()
        fake_queue.enqueue.side_effect = RuntimeError("rq blew up")
        mocker.patch("rq.Queue", return_value=fake_queue)

        called_fallback = {"n": 0}
        def fallback(*a, **k):
            called_fallback["n"] += 1

        result = queue_mod.enqueue(_noop, fallback_add_task=fallback)
        assert result == "inline"
        assert called_fallback["n"] == 1
