"""Execute rendering from Timeline DSL to final output."""

import subprocess
from pathlib import Path

from app.core.logger import get_logger
from app.dsl.schema import Timeline
from app.dsl.validators import validate_timeline
from app.render.ffmpeg_builder import FFmpegCommandBuilder
from app.storage.storage_manager import StorageManager
from app.utils.ffmpeg_utils import FFmpegError

log = get_logger(__name__)


def render_timeline(storage: StorageManager) -> Path:
    """
    Load Timeline DSL, validate, build FFmpeg command, execute, return output path.
    """
    # Load timeline
    dsl_data = storage.load_dsl()
    timeline = Timeline(**dsl_data)

    # Validate
    errors = validate_timeline(timeline, storage)
    if errors:
        raise ValueError(f"Timeline validation failed: {'; '.join(errors)}")

    # Build FFmpeg command
    builder = FFmpegCommandBuilder(timeline, storage)
    cmd = builder.build()
    log.info("Render command: %s", " ".join(cmd))

    # Ensure output directory exists
    output_path = storage.output_path("final.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Execute
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=600
    )

    if result.returncode != 0:
        log.error("Render failed: %s", result.stderr[-2000:] if result.stderr else "")
        raise FFmpegError(f"Render failed: {result.stderr[-500:]}")

    if not output_path.exists():
        raise FFmpegError("Render completed but output file not found")

    log.info("Render complete: %s", output_path)
    return output_path
