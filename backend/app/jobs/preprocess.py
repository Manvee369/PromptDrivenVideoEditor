"""Stage 1: Media preprocessing — extract audio, create proxy videos.

Files are processed concurrently via a thread pool. FFmpeg invocations release
the GIL while the subprocess runs, so true parallelism is achieved across
files. Within a single file, probe → audio extract → proxy run sequentially
because they're tiny coordination steps; the bulk of CPU is in the subprocess.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager
from app.utils.ffmpeg_utils import (
    create_proxy,
    extract_audio,
    get_duration,
    probe_media,
)

log = get_logger(__name__)


def _preprocess_one_video(video_path: Path, storage: StorageManager) -> dict:
    """Probe + audio-extract + proxy for a single video file.

    Returns the manifest entry (or raises). Designed to be safe to call from
    a worker thread.
    """
    stem = video_path.stem
    log.info("Preprocessing: %s", video_path.name)

    info = probe_media(video_path)
    duration = float(info["format"]["duration"])
    width, height = 0, 0
    for stream in info.get("streams", []):
        if stream["codec_type"] == "video":
            width = int(stream["width"])
            height = int(stream["height"])
            break

    audio_path = storage.prep_path(f"{stem}_audio.wav")
    extract_audio(video_path, audio_path)
    log.info("Extracted audio: %s", audio_path.name)

    proxy_path = storage.prep_path(f"{stem}_proxy.mp4")
    create_proxy(video_path, proxy_path)
    log.info("Created proxy: %s", proxy_path.name)

    return {
        "filename": video_path.name,
        "stem": stem,
        "duration": duration,
        "width": width,
        "height": height,
        "audio_path": str(audio_path),
        "proxy_path": str(proxy_path),
        "raw_path": str(video_path),
    }


def preprocess_media(storage: StorageManager) -> dict:
    """For each video in raw/, probe + extract audio + create proxy in parallel.

    Standalone audio files (music, voiceover) are added serially at the end;
    they don't need probing or proxy generation.

    Returns manifest dict saved to signals/media_manifest.json. The manifest
    preserves the original file order from raw/ even though processing is
    concurrent.
    """
    storage.ensure_dirs()
    videos = storage.raw_video_files()

    if not videos:
        raise FileNotFoundError(f"No video files found in {storage.stage_dir('raw')}")

    # Stable index → keeps manifest ordering deterministic regardless of
    # which thread finishes first.
    manifest_entries: list[dict | None] = [None] * len(videos)

    # Thread pool size: cap at len(videos), and at min(8, cores) to avoid
    # overwhelming I/O on machines with many cores. FFmpeg already uses
    # multiple threads internally per invocation.
    workers = min(len(videos), 8)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_idx = {
            pool.submit(_preprocess_one_video, v, storage): i
            for i, v in enumerate(videos)
        }
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                manifest_entries[idx] = fut.result()
            except Exception as e:
                log.error("Preprocess failed for %s: %s", videos[idx].name, e)
                raise

    manifest = {"files": [e for e in manifest_entries if e is not None]}

    # Standalone audio files (music, voiceover). These are small and serial
    # operations are fine; the heavy lifting was the videos above.
    for audio_path in storage.raw_audio_files():
        duration = get_duration(audio_path)
        manifest["files"].append({
            "filename": audio_path.name,
            "stem": audio_path.stem,
            "duration": duration,
            "width": 0,
            "height": 0,
            "audio_path": str(audio_path),
            "proxy_path": None,
            "raw_path": str(audio_path),
        })

    storage.save_signal("media_manifest", manifest)
    log.info("Preprocessing complete: %d files", len(manifest["files"]))
    return manifest
