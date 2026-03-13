"""Planner Agent — rule-based prompt parsing with Phase 2 signal awareness.

Reads user prompt + signal summaries, outputs a structured plan.
Same function signature as a future LLM-based planner.
"""

import re

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# Aspect ratio keywords
ASPECT_KEYWORDS = {
    "vertical": "9:16", "portrait": "9:16", "9:16": "9:16",
    "tiktok": "9:16", "reels": "9:16", "shorts": "9:16",
    "horizontal": "16:9", "landscape": "16:9", "16:9": "16:9",
    "square": "1:1", "1:1": "1:1",
}

ASPECT_DIMENSIONS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}


def plan_edit(prompt: str, signals: dict, storage: StorageManager) -> dict:
    """
    Parse prompt for editing intent and produce a structured plan.

    Args:
        prompt: User's natural language editing prompt
        signals: Dict with keys like "media_manifest", "transcript", "silence", "shots", "motion"
        storage: StorageManager for saving the plan

    Returns:
        Plan dict saved to plans/plan.json
    """
    prompt_lower = prompt.lower()
    operations = []

    # Detect target duration
    target_duration = _parse_duration(prompt_lower)

    # Detect aspect ratio
    aspect = "16:9"
    for keyword, ratio in ASPECT_KEYWORDS.items():
        if keyword in prompt_lower:
            aspect = ratio
            break

    width, height = ASPECT_DIMENSIONS.get(aspect, (1920, 1080))

    # Detect operations
    if any(kw in prompt_lower for kw in ["remove silence", "cut silence", "no silence", "remove pauses"]):
        operations.append("remove_silence")

    if any(kw in prompt_lower for kw in ["subtitle", "subtitles", "caption", "captions", "text"]):
        operations.append("add_captions")

    if any(kw in prompt_lower for kw in ["slow motion", "slow-mo", "slowmo"]):
        operations.append("slow_motion")

    if any(kw in prompt_lower for kw in ["black and white", "b&w", "grayscale"]):
        operations.append("black_and_white")

    if any(kw in prompt_lower for kw in ["trim", "short", "clip", "cut to"]):
        operations.append("trim")

    # Phase 2 operations
    if any(kw in prompt_lower for kw in ["highlight", "best moments", "best parts", "top moments"]):
        operations.append("highlight_select")

    if any(kw in prompt_lower for kw in ["montage", "edit", "compilation", "reel"]):
        operations.append("highlight_select")
        operations.append("story_compose")

    if any(kw in prompt_lower for kw in ["music", "beat", "beat sync", "rhythm"]):
        operations.append("beat_sync")

    # Deduplicate
    operations = list(dict.fromkeys(operations))

    # Detect energy/style
    energy = "medium"
    if any(kw in prompt_lower for kw in ["hype", "energetic", "fast", "intense", "montage"]):
        energy = "high"
    elif any(kw in prompt_lower for kw in ["calm", "slow", "relaxed", "chill"]):
        energy = "low"

    # Calculate total media duration from manifest
    total_media_duration = 0.0
    if "media_manifest" in signals:
        for f in signals["media_manifest"].get("files", []):
            total_media_duration += f.get("duration", 0)

    # Build highlight scoring priorities based on energy
    if energy == "high":
        priorities = {"motion": 0.35, "audio_peak": 0.25, "speech": 0.10, "shot_variety": 0.15, "face": 0.15}
    elif energy == "low":
        priorities = {"motion": 0.10, "audio_peak": 0.15, "speech": 0.35, "shot_variety": 0.15, "face": 0.25}
    else:
        priorities = {"motion": 0.30, "audio_peak": 0.25, "speech": 0.15, "shot_variety": 0.15, "face": 0.15}

    plan = {
        "goal": prompt,
        "target_duration": target_duration,
        "total_media_duration": total_media_duration,
        "style": {
            "aspect": aspect,
            "width": width,
            "height": height,
            "energy": energy,
        },
        "operations": operations,
        "priorities": priorities,
        "constraints": {},
    }

    storage.save_plan("plan", plan)
    log.info("Plan created: operations=%s, duration=%s, aspect=%s, energy=%s",
             operations, target_duration, aspect, energy)
    return plan


def _parse_duration(text: str) -> float | None:
    """Extract target duration from prompt text. Returns seconds or None."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s\b)", text)
    if match:
        return float(match.group(1))

    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m\b)", text)
    if match:
        return float(match.group(1)) * 60

    return None
