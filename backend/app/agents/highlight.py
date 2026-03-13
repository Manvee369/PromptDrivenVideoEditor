"""Highlight Selection Agent — ranks and selects the best segments."""

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# Default scoring weights
DEFAULT_WEIGHTS = {
    "motion": 0.30,
    "audio_peak": 0.25,
    "speech": 0.15,
    "shot_variety": 0.15,
    "face": 0.15,
}


def select_highlights(
    plan: dict, signals: dict, storage: StorageManager
) -> list[dict]:
    """
    Rank candidate segments and return top highlights.

    Scoring formula:
        score = motion_w * motion + audio_w * audio_peak
              + speech_w * has_speech + variety_w * shot_variety

    Returns list of scored segments saved to plans/highlights.json:
    [
        {"source": "clip.mp4", "start": 3.0, "end": 8.0, "score": 0.85, "reasons": [...]}
    ]
    """
    weights = plan.get("priorities", DEFAULT_WEIGHTS)
    motion_w = weights.get("motion", DEFAULT_WEIGHTS["motion"])
    audio_w = weights.get("audio_peak", DEFAULT_WEIGHTS["audio_peak"])
    speech_w = weights.get("speech", DEFAULT_WEIGHTS["speech"])
    variety_w = weights.get("shot_variety", DEFAULT_WEIGHTS["shot_variety"])
    face_w = weights.get("face", DEFAULT_WEIGHTS["face"])

    manifest = signals.get("media_manifest", {})
    shots_data = signals.get("shots", {})
    motion_data = signals.get("motion", {})
    energy_data = signals.get("audio_energy", {})
    silence_data = signals.get("silence", {})
    faces_data = signals.get("faces", {})

    candidates = []

    for file_info in manifest.get("files", []):
        if file_info.get("width", 0) == 0:
            continue

        filename = file_info["filename"]
        duration = file_info["duration"]

        # Get shots for this file (or create windows)
        shots = _get_shots(shots_data, filename, duration)
        motion_scores = _get_motion_lookup(motion_data, filename)
        peaks = _get_peaks_lookup(energy_data, filename)
        speech_regions = _get_speech_regions(silence_data, filename)
        face_detections = _get_face_detections(faces_data, filename)

        for shot in shots:
            start, end = shot["start"], shot["end"]
            reasons = []

            # Motion score: average intensity in this window
            motion_score = _avg_motion_in_range(motion_scores, start, end)
            if motion_score > 0.3:
                reasons.append(f"high motion ({motion_score:.2f})")

            # Audio peak score: how many peaks fall in this window
            peak_score = _peak_density_in_range(peaks, start, end)
            if peak_score > 0.3:
                reasons.append(f"audio peak ({peak_score:.2f})")

            # Speech score: does this segment overlap with speech?
            speech_score = _speech_overlap(speech_regions, start, end)
            if speech_score > 0.5:
                reasons.append("has speech")

            # Face presence score
            face_score = _face_presence_in_range(face_detections, start, end)
            if face_score > 0.3:
                reasons.append(f"face detected ({face_score:.2f})")

            # Shot variety: shorter shots get a boost (more dynamic)
            shot_dur = end - start
            variety_score = min(1.0, 5.0 / max(shot_dur, 0.5))
            if variety_score > 0.5:
                reasons.append("dynamic pacing")

            total_score = (
                motion_w * motion_score
                + audio_w * peak_score
                + speech_w * speech_score
                + variety_w * variety_score
                + face_w * face_score
            )

            candidates.append({
                "source": filename,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "score": round(total_score, 4),
                "reasons": reasons,
                "breakdown": {
                    "motion": round(motion_score, 4),
                    "audio_peak": round(peak_score, 4),
                    "speech": round(speech_score, 4),
                    "shot_variety": round(variety_score, 4),
                    "face": round(face_score, 4),
                },
            })

    # Sort by score descending
    candidates.sort(key=lambda c: c["score"], reverse=True)

    storage.save_plan("highlights", candidates)
    log.info("Selected %d highlight candidates (top score: %.3f)",
             len(candidates), candidates[0]["score"] if candidates else 0)
    return candidates


def _get_shots(shots_data: dict, filename: str, duration: float) -> list[dict]:
    """Get shot list for a file. Falls back to fixed-length windows."""
    for track in shots_data.get("tracks", []):
        if track["source"] == filename:
            return track.get("shots", [])
    # Fallback: create 3-second windows
    windows = []
    t = 0.0
    i = 0
    while t < duration:
        end = min(t + 3.0, duration)
        windows.append({"start": t, "end": end, "index": i})
        t = end
        i += 1
    return windows


def _get_motion_lookup(motion_data: dict, filename: str) -> list[dict]:
    for track in motion_data.get("tracks", []):
        if track["source"] == filename:
            return track.get("scores", [])
    return []


def _get_peaks_lookup(energy_data: dict, filename: str) -> list[dict]:
    for track in energy_data.get("tracks", []):
        if track["source"] == filename:
            return track.get("peaks", [])
    return []


def _get_speech_regions(silence_data: dict, filename: str) -> list[dict]:
    for track in silence_data.get("tracks", []):
        if track["source"] == filename:
            return track.get("speech_regions", [])
    return []


def _get_face_detections(faces_data: dict, filename: str) -> list[dict]:
    for track in faces_data.get("tracks", []):
        if track["source"] == filename:
            return track.get("detections", [])
    return []


def _face_presence_in_range(detections: list[dict], start: float, end: float) -> float:
    """Average face confidence in the time range. 0 if no faces."""
    relevant = [d for d in detections if start <= d["time"] <= end and d["count"] > 0]
    if not relevant:
        return 0.0
    return sum(d["confidence"] for d in relevant) / len(relevant)


def _avg_motion_in_range(scores: list[dict], start: float, end: float) -> float:
    vals = [s["intensity"] for s in scores if start <= s["time"] <= end]
    return sum(vals) / len(vals) if vals else 0.0


def _peak_density_in_range(peaks: list[dict], start: float, end: float) -> float:
    duration = end - start
    if duration <= 0:
        return 0.0
    count = sum(1 for p in peaks if start <= p["time"] <= end)
    # Normalize: 1 peak per 2 seconds = score 1.0
    return min(1.0, count / max(1, duration / 2.0))


def _speech_overlap(speech_regions: list[dict], start: float, end: float) -> float:
    duration = end - start
    if duration <= 0:
        return 0.0
    overlap = 0.0
    for r in speech_regions:
        ov_start = max(start, r["start"])
        ov_end = min(end, r["end"])
        if ov_end > ov_start:
            overlap += ov_end - ov_start
    return min(1.0, overlap / duration)
