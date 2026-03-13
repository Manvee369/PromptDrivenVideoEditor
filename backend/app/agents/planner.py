"""Planner Agent — tries LLM-based planning first, falls back to rule-based.

Reads user prompt + signal summaries, outputs a structured plan.
"""

import re

from app.core.config import settings
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
    Produce a structured editing plan from the prompt.

    Tries LLM planner first (if API key configured), falls back to rule-based.
    """
    # Try LLM planner
    if settings.llm_planner_enabled and settings.llm_api_key:
        try:
            from app.agents.llm_planner import llm_plan_edit
            llm_plan = llm_plan_edit(prompt, signals)
            if llm_plan:
                # Add computed fields
                llm_plan["total_media_duration"] = _total_media_duration(signals)
                storage.save_plan("plan", llm_plan)
                log.info("LLM plan created: operations=%s, energy=%s",
                         llm_plan.get("operations"), llm_plan.get("style", {}).get("energy"))
                return llm_plan
        except Exception as e:
            log.warning("LLM planner failed, falling back to rules: %s", e)

    # Rule-based fallback
    plan = _rule_based_plan(prompt, signals)
    storage.save_plan("plan", plan)
    log.info("Rule-based plan created: operations=%s, duration=%s, aspect=%s, energy=%s",
             plan["operations"], plan["target_duration"],
             plan["style"]["aspect"], plan["style"]["energy"])
    return plan


def _rule_based_plan(prompt: str, signals: dict) -> dict:
    """Original keyword-matching planner logic."""
    prompt_lower = prompt.lower()
    operations = []

    target_duration = _parse_duration(prompt_lower)

    aspect = "16:9"
    for keyword, ratio in ASPECT_KEYWORDS.items():
        if keyword in prompt_lower:
            aspect = ratio
            break

    width, height = ASPECT_DIMENSIONS.get(aspect, (1920, 1080))

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

    if any(kw in prompt_lower for kw in ["highlight", "best moments", "best parts", "top moments"]):
        operations.append("highlight_select")

    if any(kw in prompt_lower for kw in ["montage", "edit", "compilation", "reel"]):
        operations.append("highlight_select")
        operations.append("story_compose")

    if any(kw in prompt_lower for kw in ["music", "beat", "beat sync", "rhythm"]):
        operations.append("beat_sync")

    if any(kw in prompt_lower for kw in ["transition", "crossfade", "smooth", "flash", "zoom"]):
        operations.append("add_transitions")

    # Auto-add transitions for montages and reels
    if any(op in operations for op in ["highlight_select", "story_compose"]):
        if "add_transitions" not in operations:
            operations.append("add_transitions")

    operations = list(dict.fromkeys(operations))

    energy = "medium"
    if any(kw in prompt_lower for kw in ["hype", "energetic", "fast", "intense", "montage"]):
        energy = "high"
    elif any(kw in prompt_lower for kw in ["calm", "slow", "relaxed", "chill"]):
        energy = "low"

    if energy == "high":
        priorities = {"motion": 0.35, "audio_peak": 0.25, "speech": 0.10, "shot_variety": 0.15, "face": 0.15}
    elif energy == "low":
        priorities = {"motion": 0.10, "audio_peak": 0.15, "speech": 0.35, "shot_variety": 0.15, "face": 0.25}
    else:
        priorities = {"motion": 0.30, "audio_peak": 0.25, "speech": 0.15, "shot_variety": 0.15, "face": 0.15}

    return {
        "goal": prompt,
        "target_duration": target_duration,
        "total_media_duration": _total_media_duration(signals),
        "style": {
            "aspect": aspect,
            "width": width,
            "height": height,
            "energy": energy,
        },
        "operations": operations,
        "priorities": priorities,
        "constraints": {},
        "planner": "rule_based",
    }


def _total_media_duration(signals: dict) -> float:
    """Sum duration of all media files."""
    total = 0.0
    if "media_manifest" in signals:
        for f in signals["media_manifest"].get("files", []):
            total += f.get("duration", 0)
    return total


def _parse_duration(text: str) -> float | None:
    """Extract target duration from prompt text. Returns seconds or None."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s\b)", text)
    if match:
        return float(match.group(1))

    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m\b)", text)
    if match:
        return float(match.group(1)) * 60

    return None
