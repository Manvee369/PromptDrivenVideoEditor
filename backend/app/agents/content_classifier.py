"""Content Classifier — determines video type and user intent.

Combines heuristic signal analysis with SigLIP visual classification
to produce a robust content type and user intent classification.

Outputs saved to signals/classification.json.
"""

from __future__ import annotations

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# ── Video type definitions ──────────────────────────────────────────────────

VIDEO_TYPES = {
    "talking_head": "Single person speaking to camera",
    "podcast": "Multi-person conversation or interview",
    "sports": "Athletic or competitive action footage",
    "gaming": "Screen recording of video games",
    "vlog": "Casual personal footage, travel, daily life",
    "tutorial": "Educational, how-to, or demonstration content",
    "event": "Live event, concert, ceremony, or gathering",
    "raw_footage": "Unstructured B-roll or stock footage",
    "cooking": "Food preparation or cooking content",
    "music_performance": "Musical performance or music video",
}

# ── User intent definitions ─────────────────────────────────────────────────

USER_INTENTS = {
    "clean_up": "Remove filler, silence, mistakes — keep content intact",
    "highlight_reel": "Pick best moments for a short, punchy edit",
    "recap": "Summarize key points into a condensed overview",
    "reformat": "Adapt content for a different platform (vertical, square)",
    "full_edit": "Complete edit with transitions, music, captions, effects",
}

# ── Intent keyword mapping ──────────────────────────────────────────────────

INTENT_KEYWORDS = {
    "clean_up": [
        "clean", "cleanup", "clean up", "remove silence", "remove pauses",
        "cut silence", "no silence", "remove filler", "polish", "fix",
    ],
    "highlight_reel": [
        "highlight", "best moments", "best parts", "top moments", "reel",
        "montage", "compilation", "best of", "clips", "short",
    ],
    "recap": [
        "recap", "summary", "summarize", "condense", "tldr", "tl;dr",
        "key points", "overview", "digest",
    ],
    "reformat": [
        "vertical", "tiktok", "reels", "shorts", "square", "instagram",
        "9:16", "1:1", "portrait", "landscape", "reformat", "convert",
    ],
    "full_edit": [
        "edit", "full edit", "produce", "create", "make a video",
        "professional", "cinematic", "complete", "finish",
    ],
}

# ── Mismatch warnings ──────────────────────────────────────────────────────

MISMATCH_WARNINGS = {
    ("talking_head", "highlight_reel"): (
        "This looks like a single-person talking head video. Highlight reels "
        "work best with varied action footage. The result may just be the most "
        "energetic speaking moments."
    ),
    ("podcast", "highlight_reel"): (
        "This appears to be a conversation/podcast. A highlight reel will "
        "extract the most dynamic speaking moments, but may lose conversational "
        "context."
    ),
    ("talking_head", "reformat"): None,  # This is fine
    ("gaming", "clean_up"): (
        "This looks like gaming footage. Clean-up will remove silent moments, "
        "but gaming pauses are often intentional (loading, strategy). Consider "
        "a highlight reel instead."
    ),
    ("sports", "clean_up"): (
        "This appears to be sports footage. Clean-up removes silence, but "
        "sports often has natural pauses between plays. A highlight reel "
        "might better capture the action."
    ),
    ("raw_footage", "recap"): (
        "This looks like raw/unstructured footage. A recap needs clear "
        "narrative structure — the result may be unpredictable. Consider "
        "a highlight reel or full edit instead."
    ),
}


def classify_content(
    prompt: str,
    signals: dict,
    storage: StorageManager,
) -> dict:
    """
    Classify video content type and parse user intent from prompt.

    Combines:
    - SigLIP visual classification (if available)
    - Heuristic signals (speaker count, motion, faces, speech ratio, shots)
    - Prompt keyword analysis for user intent

    Returns classification saved to signals/classification.json:
    {
        "video_type": "talking_head",
        "video_type_confidence": 0.82,
        "video_type_scores": {"talking_head": 0.82, "podcast": 0.10, ...},
        "user_intent": "clean_up",
        "user_intent_confidence": 0.90,
        "intent_scores": {"clean_up": 0.90, ...},
        "warnings": ["..."],
        "heuristic_signals": {...}
    }
    """
    # ── Gather heuristic signals ────────────────────────────────────────

    heuristics = _compute_heuristics(signals)

    # ── Video type classification ───────────────────────────────────────

    # Start with heuristic scores
    type_scores = _heuristic_type_scores(heuristics)

    # Blend with SigLIP visual scores if available
    visual_scores = signals.get("visual_scores")
    if visual_scores:
        visual_type_scores = _aggregate_visual_type_scores(visual_scores)
        # Weighted blend: 40% heuristic, 60% visual (visual is more reliable)
        for key in type_scores:
            h_score = type_scores.get(key, 0.0)
            v_score = visual_type_scores.get(key, 0.0)
            type_scores[key] = round(0.4 * h_score + 0.6 * v_score, 4)

    # Normalize
    total = sum(type_scores.values())
    if total > 0:
        type_scores = {k: round(v / total, 4) for k, v in type_scores.items()}

    top_type = max(type_scores, key=type_scores.get)
    top_type_confidence = type_scores[top_type]

    # ── User intent classification ──────────────────────────────────────

    intent_scores = _parse_user_intent(prompt)
    top_intent = max(intent_scores, key=intent_scores.get)
    top_intent_confidence = intent_scores[top_intent]

    # ── Mismatch warnings ──────────────────────────────────────────────

    warnings = _check_mismatches(top_type, top_intent, top_type_confidence)

    result = {
        "video_type": top_type,
        "video_type_confidence": round(top_type_confidence, 4),
        "video_type_scores": type_scores,
        "user_intent": top_intent,
        "user_intent_confidence": round(top_intent_confidence, 4),
        "intent_scores": intent_scores,
        "warnings": warnings,
        "heuristic_signals": heuristics,
    }

    storage.save_signal("classification", result)
    log.info(
        "Content classified: type=%s (%.2f), intent=%s (%.2f), warnings=%d",
        top_type, top_type_confidence, top_intent, top_intent_confidence, len(warnings),
    )
    return result


def _compute_heuristics(signals: dict) -> dict:
    """Extract key heuristic features from intelligence signals."""
    manifest = signals.get("media_manifest", {})
    files = manifest.get("files", [])
    total_duration = sum(f.get("duration", 0) for f in files)
    video_count = sum(1 for f in files if f.get("width", 0) > 0)

    # Speaker count
    diarization = signals.get("diarization")
    num_speakers = 1
    if diarization:
        for track in diarization.get("tracks", []):
            num_speakers = max(num_speakers, track.get("num_speakers", 1))

    # Speech ratio (how much of the video has speech)
    silence = signals.get("silence", {})
    speech_duration = 0.0
    for track in silence.get("tracks", []):
        for region in track.get("speech_regions", []):
            speech_duration += region.get("end", 0) - region.get("start", 0)
    speech_ratio = speech_duration / total_duration if total_duration > 0 else 0.0

    # Motion intensity
    motion = signals.get("motion", {})
    avg_motion = 0.0
    high_motion_count = 0
    for track in motion.get("tracks", []):
        scores = track.get("scores", [])
        if scores:
            avg_motion = sum(s["intensity"] for s in scores) / len(scores)
        high_motion_count += len(track.get("high_motion_regions", []))

    # Face presence
    faces = signals.get("faces", {})
    face_frame_ratio = 0.0
    avg_face_count = 0.0
    for track in faces.get("tracks", []):
        detections = track.get("detections", [])
        if detections:
            with_face = sum(1 for d in detections if d.get("count", 0) > 0)
            face_frame_ratio = with_face / len(detections)
            avg_face_count = sum(d.get("count", 0) for d in detections) / len(detections)

    # Shot count and variety
    shots = signals.get("shots", {})
    total_shots = 0
    avg_shot_duration = 0.0
    for track in shots.get("tracks", []):
        shot_list = track.get("shots", [])
        total_shots += len(shot_list)
        if shot_list:
            avg_shot_duration = sum(s.get("duration", 0) for s in shot_list) / len(shot_list)

    return {
        "total_duration": round(total_duration, 2),
        "video_count": video_count,
        "num_speakers": num_speakers,
        "speech_ratio": round(speech_ratio, 4),
        "avg_motion": round(avg_motion, 4),
        "high_motion_count": high_motion_count,
        "face_frame_ratio": round(face_frame_ratio, 4),
        "avg_face_count": round(avg_face_count, 2),
        "total_shots": total_shots,
        "avg_shot_duration": round(avg_shot_duration, 2),
    }


def _heuristic_type_scores(h: dict) -> dict:
    """Score each video type based on heuristic signal patterns."""
    scores = {k: 0.0 for k in VIDEO_TYPES}

    # Talking head: 1 speaker, high face presence, low motion, few shots, high speech
    if h["num_speakers"] == 1 and h["face_frame_ratio"] > 0.6:
        scores["talking_head"] += 0.4
    if h["speech_ratio"] > 0.7 and h["avg_motion"] < 0.1:
        scores["talking_head"] += 0.3
    if h["total_shots"] <= 3:
        scores["talking_head"] += 0.2

    # Podcast: 2+ speakers, high speech, moderate face, few shots
    if h["num_speakers"] >= 2:
        scores["podcast"] += 0.5
    if h["num_speakers"] >= 2 and h["speech_ratio"] > 0.6:
        scores["podcast"] += 0.3
    if h["face_frame_ratio"] > 0.3 and h["avg_face_count"] > 1.3:
        scores["podcast"] += 0.2

    # Sports: high motion, low speech, many shots
    if h["avg_motion"] > 0.15 and h["speech_ratio"] < 0.3:
        scores["sports"] += 0.5
    if h["high_motion_count"] > 5:
        scores["sports"] += 0.2
    if h["total_shots"] > 10:
        scores["sports"] += 0.2

    # Gaming: low motion variance (screen recording), moderate speech (commentary)
    if h["avg_motion"] > 0.05 and h["avg_motion"] < 0.12:
        scores["gaming"] += 0.3
    if h["face_frame_ratio"] < 0.2 and h["speech_ratio"] > 0.3:
        scores["gaming"] += 0.3
    if h["total_shots"] <= 5 and h["total_duration"] > 120:
        scores["gaming"] += 0.2

    # Vlog: 1 speaker, moderate motion (moving camera), face present
    if h["num_speakers"] == 1 and h["avg_motion"] > 0.05:
        scores["vlog"] += 0.3
    if h["face_frame_ratio"] > 0.3 and h["total_shots"] > 3:
        scores["vlog"] += 0.3

    # Tutorial: 1 speaker, high speech, low motion
    if h["num_speakers"] == 1 and h["speech_ratio"] > 0.7:
        scores["tutorial"] += 0.3
    if h["avg_motion"] < 0.08 and h["face_frame_ratio"] < 0.5:
        scores["tutorial"] += 0.3

    # Event: many shots, moderate motion, low speech
    if h["total_shots"] > 15 and h["speech_ratio"] < 0.3:
        scores["event"] += 0.4
    if h["avg_motion"] > 0.08:
        scores["event"] += 0.2

    # Raw footage: low speech, few faces, varied motion
    if h["speech_ratio"] < 0.15 and h["face_frame_ratio"] < 0.1:
        scores["raw_footage"] += 0.5
    if h["video_count"] > 1:
        scores["raw_footage"] += 0.2

    # Cooking: moderate speech (narration), low motion, face sometimes present
    if h["speech_ratio"] > 0.4 and h["avg_motion"] < 0.10:
        scores["cooking"] += 0.2

    # Music performance: low speech, high motion or audio peaks
    if h["speech_ratio"] < 0.2 and h["avg_motion"] > 0.10:
        scores["music_performance"] += 0.3

    # Ensure at least a small base score for everything (prevents zero division)
    for key in scores:
        scores[key] = max(scores[key], 0.01)

    return scores


def _aggregate_visual_type_scores(visual_scores: dict) -> dict:
    """Average SigLIP classification scores across all tracks and keyframes."""
    from app.intelligence.visual_scoring import VIDEO_TYPE_KEYS

    accum = {k: 0.0 for k in VIDEO_TYPE_KEYS}
    count = 0

    for track in visual_scores.get("tracks", []):
        classification = track.get("classification")
        if classification:
            for key, val in classification.items():
                accum[key] = accum.get(key, 0.0) + val
            count += 1

    if count > 0:
        accum = {k: v / count for k, v in accum.items()}

    return accum


def _parse_user_intent(prompt: str) -> dict:
    """Score each intent based on keyword matching against the prompt."""
    prompt_lower = prompt.lower()
    scores = {}

    for intent, keywords in INTENT_KEYWORDS.items():
        score = 0.0
        for kw in keywords:
            if kw in prompt_lower:
                # Longer keyword matches are more specific → higher weight
                score += 0.2 + (len(kw.split()) - 1) * 0.15
        scores[intent] = min(round(score, 4), 1.0)

    # If no intent detected, default to full_edit with moderate confidence
    if max(scores.values()) < 0.1:
        scores["full_edit"] = 0.5

    # Ensure minimums
    for key in scores:
        scores[key] = max(scores[key], 0.01)

    # Normalize
    total = sum(scores.values())
    if total > 0:
        scores = {k: round(v / total, 4) for k, v in scores.items()}

    return scores


def _check_mismatches(
    video_type: str, intent: str, type_confidence: float
) -> list[str]:
    """Check for mismatches between detected video type and user intent."""
    warnings = []

    # Only warn if we're reasonably confident about the video type
    if type_confidence < 0.3:
        return warnings

    pair = (video_type, intent)
    if pair in MISMATCH_WARNINGS:
        msg = MISMATCH_WARNINGS[pair]
        if msg is not None:
            warnings.append(msg)

    return warnings
