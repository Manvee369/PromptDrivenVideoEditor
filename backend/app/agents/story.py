"""Story Composer Agent — arranges highlights into chronological narrative structure.

For sports/event content, preserves the original timeline order so the story
builds naturally toward the climax (e.g., winner at the end).
"""

from app.core.logger import get_logger
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# Narrative structure templates
# Each role defines what portion of the budget it gets and where in the
# source timeline to pull from (early/mid/late/peak)
STRUCTURES = {
    "high": {
        # Hook (exciting teaser) → Early action → Mid build → Climax → Finale
        "segments": [
            {"role": "hook", "pct": 0.12, "source_region": "peak", "order": 0},
            {"role": "early", "pct": 0.20, "source_region": "early", "order": 1},
            {"role": "build", "pct": 0.25, "source_region": "mid", "order": 2},
            {"role": "climax", "pct": 0.25, "source_region": "late", "order": 3},
            {"role": "finale", "pct": 0.18, "source_region": "latest", "order": 4},
        ],
    },
    "medium": {
        # Intro → Development → Peak → Resolution
        "segments": [
            {"role": "intro", "pct": 0.20, "source_region": "early", "order": 0},
            {"role": "development", "pct": 0.30, "source_region": "mid", "order": 1},
            {"role": "peak", "pct": 0.30, "source_region": "late", "order": 2},
            {"role": "resolution", "pct": 0.20, "source_region": "latest", "order": 3},
        ],
    },
    "low": {
        # Sequential — just pick best moments in chronological order
        "segments": [
            {"role": "intro", "pct": 0.25, "source_region": "early", "order": 0},
            {"role": "body", "pct": 0.50, "source_region": "mid", "order": 1},
            {"role": "conclusion", "pct": 0.25, "source_region": "late", "order": 2},
        ],
    },
}


def compose_story(
    plan: dict, highlights: list[dict], storage: StorageManager
) -> list[dict]:
    """
    Arrange highlight segments into a chronological narrative structure.

    Key principle: segments within each story role are ordered by their
    original source timestamp, preserving the natural event timeline.
    For sports content this means the winning moment appears at the end.
    """
    energy = plan.get("style", {}).get("energy", "medium")
    target_duration = plan.get("target_duration")
    structure = STRUCTURES.get(energy, STRUCTURES["medium"])

    if not highlights:
        log.warning("No highlights to compose story from")
        return []

    # Sort all highlights by source time
    time_sorted = sorted(highlights, key=lambda h: (h["source"], h["start"]))

    # Find the total source duration to define regions
    max_time = max(h["end"] for h in highlights) if highlights else 0
    if max_time <= 0:
        return []

    # Duration budget
    if target_duration:
        total_budget = target_duration
    else:
        total_budget = sum(h["duration"] for h in highlights[:10])

    story = []
    used_ranges = []

    for seg_template in structure["segments"]:
        budget = total_budget * seg_template["pct"]
        role = seg_template["role"]
        region = seg_template["source_region"]

        # Filter highlights by source region (where in the original video)
        pool = _filter_by_region(time_sorted, region, max_time)

        # Rank by score within the region, but we'll re-sort by time after selection
        pool = sorted(pool, key=lambda h: h["score"], reverse=True)

        # Select best segments that fit the budget
        selected = _select_for_budget(pool, budget, used_ranges)

        # Sort selected by source time to preserve chronological order
        selected = sorted(selected, key=lambda h: (h["source"], h["start"]))

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


def _filter_by_region(
    highlights: list[dict], region: str, max_time: float
) -> list[dict]:
    """Filter highlights by which region of the source video they come from."""
    if region == "early":
        return [h for h in highlights if h["start"] < max_time * 0.30]
    elif region == "mid":
        return [h for h in highlights if max_time * 0.20 <= h["start"] < max_time * 0.70]
    elif region == "late":
        return [h for h in highlights if h["start"] >= max_time * 0.55]
    elif region == "latest":
        # Last 30% — where the conclusion/winner typically is
        return [h for h in highlights if h["start"] >= max_time * 0.70]
    elif region == "peak":
        # Top scored segments from anywhere (for hook/teaser)
        return sorted(highlights, key=lambda h: h["score"], reverse=True)[:len(highlights) // 3]
    else:
        return highlights


def _select_for_budget(
    pool: list[dict], budget: float, used_ranges: list[tuple]
) -> list[dict]:
    """Select segments from pool that fit within duration budget, avoiding overlaps.
    Trims segments that are longer than remaining budget rather than skipping them."""
    selected = []
    remaining = budget

    for seg in pool:
        if _overlaps(seg, used_ranges):
            continue

        dur = seg["duration"]
        if dur <= remaining:
            selected.append(seg)
            remaining -= dur
        elif remaining >= 2.0:
            # Trim the segment to fit the remaining budget
            trimmed = dict(seg)
            trimmed["end"] = round(seg["start"] + remaining, 3)
            trimmed["duration"] = round(remaining, 3)
            selected.append(trimmed)
            remaining = 0

        if remaining < 0.5:
            break

    return selected


def _overlaps(seg: dict, used: list[tuple]) -> bool:
    """Check if segment overlaps with any already-used range."""
    for src, start, end in used:
        if seg["source"] == src:
            if seg["start"] < end and seg["end"] > start:
                return True
    return False
