"""Audio analysis: silence detection and energy curves."""

import re
import subprocess

import librosa
import numpy as np

from app.core.config import settings
from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


def detect_silence(storage: StorageManager) -> dict:
    """
    Use FFmpeg silencedetect to find silent regions in each audio file.

    Output saved to signals/silence.json:
    {
      "tracks": [
        {
          "source": "clip1.mp4",
          "duration": 60.0,
          "silent_regions": [{"start": 5.2, "end": 6.8, "duration": 1.6}],
          "speech_regions": [{"start": 0.0, "end": 5.2}, {"start": 6.8, "end": 60.0}]
        }
      ]
    }
    """
    manifest = storage.load_signal("media_manifest")
    tracks = []

    for file_info in manifest["files"]:
        audio_path = file_info["audio_path"]
        if not audio_path:
            continue

        duration = file_info["duration"]
        log.info("Detecting silence: %s", file_info["filename"])

        threshold = f"{settings.silence_threshold_db}dB"
        min_dur = str(settings.silence_min_duration)

        result = subprocess.run(
            [
                settings.ffmpeg_path, "-i", audio_path,
                "-af", f"silencedetect=noise={threshold}:d={min_dur}",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=120,
        )

        # Parse silence_start / silence_end from stderr
        silent_regions = []
        starts = re.findall(r"silence_start:\s*([\d.]+)", result.stderr)
        ends = re.findall(r"silence_end:\s*([\d.]+)", result.stderr)

        for i, start_str in enumerate(starts):
            start = round(float(start_str), 3)
            end = round(float(ends[i]), 3) if i < len(ends) else round(duration, 3)
            silent_regions.append({
                "start": start,
                "end": end,
                "duration": round(end - start, 3),
            })

        # Derive speech regions (inverse of silence)
        speech_regions = _invert_regions(silent_regions, duration)

        tracks.append({
            "source": file_info["filename"],
            "duration": duration,
            "silent_regions": silent_regions,
            "speech_regions": speech_regions,
        })

    silence_data = {"tracks": tracks}
    storage.save_signal("silence", silence_data)
    log.info("Silence detection complete: %d tracks", len(tracks))
    return silence_data


def _invert_regions(silent_regions: list[dict], duration: float) -> list[dict]:
    """Convert silent regions to speech regions."""
    if not silent_regions:
        return [{"start": 0.0, "end": round(duration, 3)}]

    speech = []
    cursor = 0.0
    for region in sorted(silent_regions, key=lambda r: r["start"]):
        if region["start"] > cursor + 0.01:
            speech.append({"start": round(cursor, 3), "end": round(region["start"], 3)})
        cursor = region["end"]

    if cursor < duration - 0.01:
        speech.append({"start": round(cursor, 3), "end": round(duration, 3)})

    return speech


def compute_audio_energy(storage: StorageManager) -> dict:
    """
    Compute RMS energy curve and detect peaks using librosa.

    Output saved to signals/audio_energy.json:
    {
      "tracks": [
        {
          "source": "clip1.mp4",
          "sample_rate": 16000,
          "hop_length": 512,
          "rms": [0.01, 0.02, ...],
          "peaks": [{"time": 3.5, "energy": 0.95}]
        }
      ]
    }
    """
    manifest = storage.load_signal("media_manifest")
    tracks = []

    for file_info in manifest["files"]:
        audio_path = file_info["audio_path"]
        if not audio_path:
            continue

        log.info("Computing audio energy: %s", file_info["filename"])

        y, sr = librosa.load(audio_path, sr=settings.audio_sample_rate, mono=True)
        hop_length = 512
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]

        # Normalize to 0-1
        rms_max = float(np.max(rms)) if np.max(rms) > 0 else 1.0
        rms_normalized = (rms / rms_max).tolist()

        # Find peaks (local maxima above 70th percentile)
        threshold = float(np.percentile(rms_normalized, 70))
        peaks = []
        times = librosa.frames_to_time(range(len(rms_normalized)), sr=sr, hop_length=hop_length)

        for i in range(1, len(rms_normalized) - 1):
            val = rms_normalized[i]
            if val > threshold and val > rms_normalized[i - 1] and val > rms_normalized[i + 1]:
                peaks.append({
                    "time": round(float(times[i]), 3),
                    "energy": round(val, 4),
                })

        tracks.append({
            "source": file_info["filename"],
            "sample_rate": sr,
            "hop_length": hop_length,
            "rms": [round(v, 4) for v in rms_normalized],
            "peaks": peaks,
        })

    energy_data = {"tracks": tracks}
    storage.save_signal("audio_energy", energy_data)
    log.info("Audio energy analysis complete: %d tracks", len(tracks))
    return energy_data
