"""Story Composer Agent — arranges highlights into narrative structure."""

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# Narrative structure templates
STRUCTURES = {
    "high": {
        # Hook → Build → Peak → Peak → Ending
        "segments": [
            {"role": "hook", "pct": 0.15, "prefer": "top"},
            {"role": "build", "pct": 0.25, "prefer": "mid"},
            {"role": "peak", "pct": 0.25, "prefer": "top"},
            {"role": "peak2", "pct": 0.20, "prefer": "top"},
            {"role": "ending", "pct": 0.15, "prefer": "mid"},
        ],
    },
    "medium": {
        # Hook → Build → Peak → Ending
        "segments": [
            {"role": "hook", "pct": 0.20, "prefer": "top"},
            {"role": "build", "pct": 0.30, "prefer": "mid"},
            {"role": "peak", "pct": 0.30, "prefer": "top"},
            {"role": "ending", "pct": 0.20, "prefer": "mid"},
        ],
    },
    "low": {
        # Intro → Body → Conclusion
        "segments": [
            {"role": "intro", "pct": 0.25, "prefer": "mid"},
            {"role": "body", "pct": 0.50, "prefer": "sequential"},
            {"role": "conclusion", "pct": 0.25, "prefer": "mid"},
        ],
    },
}


def compose_story(
    plan: dict, highlights: list[dict], storage: StorageManager
) -> list[dict]:
    """
    Arrange highlight segments into a narrative structure based on energy style.

    Returns ordered list of segments saved to plans/story.json:
    [
        {"source": "clip.mp4", "start": 5.0, "end": 8.0, "role": "hook", "score": 0.9}
    ]
    """
    energy = plan.get("style", {}).get("energy", "medium")
    target_duration = plan.get("target_duration")
    structure = STRUCTURES.get(energy, STRUCTURES["medium"])

    if not highlights:
        log.warning("No highlights to compose story from")
        return []

    # Separate highlights into tiers
    sorted_hl = sorted(highlights, key=lambda h: h["score"], reverse=True)
    n = len(sorted_hl)
    top_third = sorted_hl[:max(1, n // 3)]
    mid_third = sorted_hl[max(1, n // 3):max(2, 2 * n // 3)]
    bottom_third = sorted_hl[max(2, 2 * n // 3):]

    # Calculate duration budget per segment
    if target_duration:
        total_budget = target_duration
    else:
        # Use sum of all highlight durations, capped at source duration
        total_budget = sum(h["duration"] for h in highlights[:10])

    story = []
    used_ranges = []  # Track (source, start, end) to avoid overlaps

    for seg_template in structure["segments"]:
        budget = total_budget * seg_template["pct"]
        prefer = seg_template["prefer"]
        role = seg_template["role"]

        # Pick from preferred tier
        if prefer == "top":
            pool = top_third + mid_third
        elif prefer == "sequential":
            # For sequential, use time-ordered highlights
            pool = sorted(highlights, key=lambda h: (h["source"], h["start"]))
        else:
            pool = mid_third + top_third + bottom_third

        # Select segments that fit the budget and don't overlap
        selected = _select_for_budget(pool, budget, used_ranges)

        for seg in selected:
            story.append({
                "source": seg["source"],
                "start": seg["start"],
                "end": seg["end"],
                "duration": seg["duration"],
                "role": role,
                "score": seg["score"],
            })
            used_ranges.append((seg["source"], seg["start"], seg["end"]))

    storage.save_plan("story", story)
    log.info("Story composed: %d segments, %.1fs total, energy=%s",
             len(story), sum(s["duration"] for s in story), energy)
    return story


def _select_for_budget(
    pool: list[dict], budget: float, used_ranges: list[tuple]
) -> list[dict]:
    """Select segments from pool that fit within duration budget, avoiding overlaps."""
    selected = []
    remaining = budget

    for seg in pool:
        if seg["duration"] > remaining:
            continue
        if _overlaps(seg, used_ranges):
            continue

        selected.append(seg)
        remaining -= seg["duration"]

        if remaining <= 0.5:
            break

    return selected


def _overlaps(seg: dict, used: list[tuple]) -> bool:
    """Check if segment overlaps with any already-used range."""
    for src, start, end in used:
        if seg["source"] == src:
            if seg["start"] < end and seg["end"] > start:
                return True
    return False
