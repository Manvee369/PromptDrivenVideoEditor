"""Stage 1: Media preprocessing — extract audio, create proxy videos."""

from pathlib import Path

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager
from app.utils.ffmpeg_utils import extract_audio, create_proxy, probe_media, get_duration

log = get_logger(__name__)


def preprocess_media(storage: StorageManager) -> dict:
    """
    For each video in raw/:
      1. Probe it (ffprobe) for metadata
      2. Extract audio to prep/{stem}_audio.wav (16kHz mono)
      3. Create proxy video to prep/{stem}_proxy.mp4

    Returns manifest dict saved to signals/media_manifest.json.
    """
    storage.ensure_dirs()
    videos = storage.raw_video_files()

    if not videos:
        raise FileNotFoundError(f"No video files found in {storage.stage_dir('raw')}")

    manifest = {"files": []}

    for video_path in videos:
        stem = video_path.stem
        log.info("Preprocessing: %s", video_path.name)

        # Probe metadata
        info = probe_media(video_path)
        duration = float(info["format"]["duration"])
        width, height = 0, 0
        for stream in info.get("streams", []):
            if stream["codec_type"] == "video":
                width = int(stream["width"])
                height = int(stream["height"])
                break

        # Extract audio
        audio_path = storage.prep_path(f"{stem}_audio.wav")
        extract_audio(video_path, audio_path)
        log.info("Extracted audio: %s", audio_path.name)

        # Create proxy
        proxy_path = storage.prep_path(f"{stem}_proxy.mp4")
        create_proxy(video_path, proxy_path)
        log.info("Created proxy: %s", proxy_path.name)

        manifest["files"].append({
            "filename": video_path.name,
            "stem": stem,
            "duration": duration,
            "width": width,
            "height": height,
            "audio_path": str(audio_path),
            "proxy_path": str(proxy_path),
            "raw_path": str(video_path),
        })

    # Also list any standalone audio files (music, voiceover)
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
