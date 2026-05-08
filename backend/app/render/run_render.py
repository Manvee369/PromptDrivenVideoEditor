"""Execute rendering from Timeline DSL to final output, with live progress."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import IO

from app.core.logger import get_logger
from app.dsl.schema import Timeline
from app.dsl.validators import validate_timeline
from app.jobs.events import JobEvents
from app.render.ffmpeg_builder import FFmpegCommandBuilder
from app.storage.storage_manager import StorageManager
from app.utils.ffmpeg_utils import FFmpegError

log = get_logger(__name__)

# Hard ceiling on render time. Long-form content may need a higher cap; this
# default keeps a runaway ffmpeg from hanging the worker indefinitely.
RENDER_TIMEOUT_SECONDS = 1800  # 30 min


def render_timeline(storage: StorageManager) -> Path:
    """Load Timeline DSL, validate, build FFmpeg command, execute with live
    progress streaming, return output path."""
    dsl_data = storage.load_dsl()
    timeline = Timeline(**dsl_data)

    errors = validate_timeline(timeline, storage)
    if errors:
        raise ValueError(f"Timeline validation failed: {'; '.join(errors)}")

    builder = FFmpegCommandBuilder(timeline, storage)
    cmd = builder.build()

    # Inject `-progress pipe:1` immediately before the output path so ffmpeg
    # streams progress lines to stdout. The CommandBuilder always puts the
    # output path last, so this is safe.
    cmd = cmd[:-1] + ["-progress", "pipe:1", "-nostats", cmd[-1]]
    log.info("Render command: %s", " ".join(cmd))

    output_path = storage.output_path("final.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    events = JobEvents(storage)
    events.clear()
    events.emit(substage="render", progress=0.0)

    total_dur_us = int(timeline.total_duration() * 1_000_000) or 1

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # line-buffered
    )

    stderr_chunks: list[str] = []
    stdout_thread = threading.Thread(
        target=_stream_progress,
        args=(process.stdout, events, total_dur_us),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_stderr,
        args=(process.stderr, stderr_chunks),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    try:
        rc = process.wait(timeout=RENDER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
        events.emit(substage="render", error="render timed out")
        raise FFmpegError(f"Render timed out after {RENDER_TIMEOUT_SECONDS}s")

    # Drain readers so we don't lose tail output.
    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)

    stderr_text = "".join(stderr_chunks)

    if rc != 0:
        log.error("Render failed (rc=%d): %s", rc, stderr_text[-2000:])
        events.emit(substage="render", error=stderr_text[-500:] or f"rc={rc}")
        raise FFmpegError(f"Render failed: {stderr_text[-500:] or f'rc={rc}'}")

    if not output_path.exists():
        events.emit(substage="render", error="output file missing after render")
        raise FFmpegError("Render completed but output file not found")

    events.emit(substage="render", progress=1.0, message="render complete")
    log.info("Render complete: %s", output_path)
    return output_path


# --- Internal helpers --------------------------------------------------------


def _stream_progress(pipe: IO[str], events: JobEvents, total_dur_us: int) -> None:
    """Parse ffmpeg's `-progress pipe:1` output and emit substage events.

    Each block of key=value lines ends with `progress=continue` or
    `progress=end`. We accumulate keys then emit on the marker.
    """
    block: dict[str, str] = {}
    try:
        for raw in pipe:
            line = raw.strip()
            if not line or "=" not in line:
                continue
            k, _, v = line.partition("=")
            block[k] = v
            if k != "progress":
                continue

            # End of a progress block — emit the snapshot.
            try:
                out_time_us = int(block.get("out_time_ms", 0))
            except ValueError:
                out_time_us = 0

            pct = min(out_time_us / total_dur_us, 1.0) if total_dur_us > 0 else 0.0
            payload: dict = {
                "substage": "render",
                "progress": round(pct, 4),
            }
            if "frame" in block:
                try:
                    payload["frame"] = int(block["frame"])
                except ValueError:
                    pass
            if "fps" in block:
                try:
                    payload["fps"] = round(float(block["fps"]), 2)
                except ValueError:
                    pass
            if "speed" in block:
                payload["speed"] = block["speed"]
            events.emit(**payload)

            block = {}
            if v == "end":
                break
    except Exception as e:
        # Progress streaming must never crash the render. Log and bail.
        log.debug("Progress reader stopped: %s", e)
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def _drain_stderr(pipe: IO[str], chunks: list[str]) -> None:
    """Capture stderr for diagnostics. Read in small chunks so we don't block
    if ffmpeg is verbose."""
    try:
        for line in pipe:
            chunks.append(line)
    except Exception:
        pass
    finally:
        try:
            pipe.close()
        except Exception:
            pass
