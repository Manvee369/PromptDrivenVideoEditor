"""Music Agent — beat detection and clip-to-beat alignment."""

import librosa
import numpy as np

from app.core.config import settings
from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


def analyze_music(storage: StorageManager) -> dict | None:
    """
    If a music track exists in raw/, analyze its beats and tempo.

    Output saved to signals/music_analysis.json:
    {
      "source": "track.mp3",
      "tempo": 128.0,
      "beats": [0.5, 0.97, 1.44, ...],
      "beat_interval": 0.469,
      "downbeats": [0.5, 2.37, ...]
    }
    """
    audio_files = storage.raw_audio_files()
    if not audio_files:
        log.info("No music files found, skipping music analysis")
        return None

    music_path = audio_files[0]
    log.info("Analyzing music: %s", music_path.name)

    y, sr = librosa.load(str(music_path), sr=settings.audio_sample_rate, mono=True)

    # Tempo and beat detection
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

    # Compute beat interval
    beat_interval = 0.0
    if len(beat_times) > 1:
        intervals = np.diff(beat_times)
        beat_interval = float(np.median(intervals))

    # Downbeats (every 4th beat for 4/4 time)
    downbeats = [beat_times[i] for i in range(0, len(beat_times), 4)]

    analysis = {
        "source": music_path.name,
        "tempo": round(float(tempo) if np.isscalar(tempo) else float(tempo[0]), 2),
        "beats": [round(b, 3) for b in beat_times],
        "beat_interval": round(beat_interval, 4),
        "downbeats": [round(d, 3) for d in downbeats],
    }

    storage.save_signal("music_analysis", analysis)
    log.info("Music analysis complete: tempo=%.1f BPM, %d beats",
             analysis["tempo"], len(beat_times))
    return analysis


def align_cuts_to_beats(
    clips: list[dict], beats: list[float], tolerance: float = 0.15
) -> list[dict]:
    """
    Snap clip cut points to the nearest beat within tolerance.

    Args:
        clips: List of clip dicts with "start" and "end"
        beats: List of beat timestamps in seconds
        tolerance: Max seconds to shift a cut point

    Returns:
        Adjusted clips with cuts aligned to beats.
    """
    if not beats or not clips:
        return clips

    beats_arr = np.array(beats)
    adjusted = []

    for clip in clips:
        new_clip = dict(clip)

        # Snap start to nearest beat
        nearest_start = _nearest_beat(clip["start"], beats_arr)
        if abs(nearest_start - clip["start"]) <= tolerance:
            new_clip["start"] = round(nearest_start, 3)

        # Snap end to nearest beat
        nearest_end = _nearest_beat(clip["end"], beats_arr)
        if abs(nearest_end - clip["end"]) <= tolerance:
            new_clip["end"] = round(nearest_end, 3)

        # Ensure start < end
        if new_clip["end"] <= new_clip["start"]:
            new_clip = dict(clip)  # revert

        new_clip["duration"] = round(new_clip["end"] - new_clip["start"], 3)
        adjusted.append(new_clip)

    return adjusted


def _nearest_beat(time: float, beats: np.ndarray) -> float:
    """Find the nearest beat to a given time."""
    idx = np.argmin(np.abs(beats - time))
    return float(beats[idx])
