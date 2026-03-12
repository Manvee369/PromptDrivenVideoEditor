"""Low-level FFmpeg/FFprobe utilities."""

import json
import subprocess
from pathlib import Path

from app.core.config import settings
from app.core.logger import get_logger

log = get_logger(__name__)


class FFmpegError(Exception):
    """Raised when an FFmpeg command fails."""
    pass


def run_ffmpeg(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    """Execute an FFmpeg command. Raises FFmpegError on failure."""
    cmd = [settings.ffmpeg_path] + args
    log.info("FFmpeg: %s", " ".join(cmd))
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        log.error("FFmpeg stderr: %s", result.stderr[-2000:] if result.stderr else "")
        raise FFmpegError(f"FFmpeg failed (code {result.returncode}): {result.stderr[-500:]}")
    return result


def run_ffprobe(args: list[str]) -> subprocess.CompletedProcess:
    """Execute an FFprobe command."""
    cmd = [settings.ffprobe_path] + args
    log.debug("FFprobe: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise FFmpegError(f"FFprobe failed: {result.stderr[-500:]}")
    return result


def probe_media(filepath: str | Path) -> dict:
    """Run ffprobe and return parsed JSON with streams and format info."""
    result = run_ffprobe([
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(filepath),
    ])
    return json.loads(result.stdout)


def get_duration(filepath: str | Path) -> float:
    """Extract duration in seconds."""
    info = probe_media(filepath)
    return float(info["format"]["duration"])


def get_video_resolution(filepath: str | Path) -> tuple[int, int]:
    """Return (width, height) of the first video stream."""
    info = probe_media(filepath)
    for stream in info.get("streams", []):
        if stream["codec_type"] == "video":
            return int(stream["width"]), int(stream["height"])
    raise FFmpegError(f"No video stream found in {filepath}")


def extract_audio(
    video_path: Path, output_path: Path, sample_rate: int | None = None
) -> Path:
    """Extract audio as mono WAV at the given sample rate."""
    sr = sample_rate or settings.audio_sample_rate
    run_ffmpeg([
        "-i", str(video_path),
        "-ac", "1",
        "-ar", str(sr),
        "-vn",
        "-y",
        str(output_path),
    ])
    return output_path


def create_proxy(
    video_path: Path, output_path: Path,
    width: int | None = None, crf: int | None = None
) -> Path:
    """Create a lower-resolution proxy video for faster processing."""
    w = width or settings.proxy_resolution
    c = crf or settings.proxy_crf
    run_ffmpeg([
        "-i", str(video_path),
        "-vf", f"scale={w}:-2",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", str(c),
        "-y",
        str(output_path),
    ])
    return output_path
