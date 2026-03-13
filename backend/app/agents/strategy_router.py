"""Strategy Router — maps (video_type, user_intent) to editing strategy.

Produces a strategy config that downstream agents use to adapt their behavior:
- Highlight scoring weights
- Caption behavior (speaker tags, style)
- Story narrative structure
- Transition style and timing
- Operations to apply
"""

from __future__ import annotations

from app.core.logger import get_logger

log = get_logger(__name__)


def get_strategy(classification: dict, prompt: str = "") -> dict:
    """
    Map classification result to an editing strategy config.

    Args:
        classification: Output from content_classifier.classify_content()
        prompt: Original user prompt (for additional context)

    Returns strategy dict consumed by all downstream agents:
    {
        "video_type": "talking_head",
        "user_intent": "clean_up",
        "operations": [...],
        "highlight_weights": {...},
        "caption_config": {...},
        "story_structure": "...",
        "transition_config": {...},
        "energy": "...",
        "warnings": [...]
    }
    """
    video_type = classification.get("video_type", "raw_footage")
    intent = classification.get("user_intent", "full_edit")
    warnings = classification.get("warnings", [])

    # Get base strategy for this video type
    base = _BASE_STRATEGIES.get(video_type, _BASE_STRATEGIES["raw_footage"]).copy()

    # Get intent overlay
    intent_overlay = _INTENT_OVERLAYS.get(intent, _INTENT_OVERLAYS["full_edit"])

    # Merge: intent overlays specific fields onto the base
    strategy = _merge_strategy(base, intent_overlay)

    strategy["video_type"] = video_type
    strategy["user_intent"] = intent
    strategy["warnings"] = warnings

    log.info("Strategy resolved: type=%s, intent=%s → ops=%s, energy=%s",
             video_type, intent, strategy["operations"], strategy["energy"])

    return strategy


# ── Base strategies per video type ──────────────────────────────────────────

_BASE_STRATEGIES = {
    "talking_head": {
        "operations": ["remove_silence", "add_captions"],
        "highlight_weights": {
            "motion": 0.05,
            "audio_peak": 0.20,
            "speech": 0.40,
            "shot_variety": 0.05,
            "face": 0.15,
            "visual_relevance": 0.15,
        },
        "caption_config": {
            "speaker_tags": False,
            "style": "default",
            "animated": False,
        },
        "story_structure": "chronological",
        "transition_config": {
            "style": "minimal",
            "energy": "low",
            "crossfade_duration": 0.5,
        },
        "energy": "low",
    },

    "podcast": {
        "operations": ["remove_silence", "add_captions", "highlight_select"],
        "highlight_weights": {
            "motion": 0.05,
            "audio_peak": 0.25,
            "speech": 0.35,
            "shot_variety": 0.05,
            "face": 0.15,
            "visual_relevance": 0.15,
        },
        "caption_config": {
            "speaker_tags": True,
            "style": "default",
            "animated": False,
        },
        "story_structure": "medium",
        "transition_config": {
            "style": "crossfade",
            "energy": "low",
            "crossfade_duration": 0.6,
        },
        "energy": "low",
    },

    "sports": {
        "operations": [
            "highlight_select", "story_compose", "add_captions",
            "add_transitions", "beat_sync",
        ],
        "highlight_weights": {
            "motion": 0.35,
            "audio_peak": 0.20,
            "speech": 0.05,
            "shot_variety": 0.10,
            "face": 0.10,
            "visual_relevance": 0.20,
        },
        "caption_config": {
            "speaker_tags": False,
            "style": "tiktok_bold",
            "animated": True,
        },
        "story_structure": "high",
        "transition_config": {
            "style": "dynamic",
            "energy": "high",
            "crossfade_duration": 0.3,
        },
        "energy": "high",
    },

    "gaming": {
        "operations": [
            "highlight_select", "story_compose", "add_captions",
            "add_transitions",
        ],
        "highlight_weights": {
            "motion": 0.25,
            "audio_peak": 0.25,
            "speech": 0.15,
            "shot_variety": 0.10,
            "face": 0.05,
            "visual_relevance": 0.20,
        },
        "caption_config": {
            "speaker_tags": False,
            "style": "tiktok_bold",
            "animated": True,
        },
        "story_structure": "high",
        "transition_config": {
            "style": "dynamic",
            "energy": "high",
            "crossfade_duration": 0.25,
        },
        "energy": "high",
    },

    "vlog": {
        "operations": [
            "remove_silence", "highlight_select", "add_captions",
            "add_transitions",
        ],
        "highlight_weights": {
            "motion": 0.15,
            "audio_peak": 0.15,
            "speech": 0.25,
            "shot_variety": 0.15,
            "face": 0.15,
            "visual_relevance": 0.15,
        },
        "caption_config": {
            "speaker_tags": False,
            "style": "default",
            "animated": False,
        },
        "story_structure": "medium",
        "transition_config": {
            "style": "crossfade",
            "energy": "medium",
            "crossfade_duration": 0.5,
        },
        "energy": "medium",
    },

    "tutorial": {
        "operations": ["remove_silence", "add_captions"],
        "highlight_weights": {
            "motion": 0.05,
            "audio_peak": 0.15,
            "speech": 0.45,
            "shot_variety": 0.05,
            "face": 0.10,
            "visual_relevance": 0.20,
        },
        "caption_config": {
            "speaker_tags": False,
            "style": "default",
            "animated": False,
        },
        "story_structure": "chronological",
        "transition_config": {
            "style": "minimal",
            "energy": "low",
            "crossfade_duration": 0.5,
        },
        "energy": "low",
    },

    "event": {
        "operations": [
            "highlight_select", "story_compose", "add_transitions",
            "add_captions",
        ],
        "highlight_weights": {
            "motion": 0.25,
            "audio_peak": 0.25,
            "speech": 0.05,
            "shot_variety": 0.15,
            "face": 0.10,
            "visual_relevance": 0.20,
        },
        "caption_config": {
            "speaker_tags": False,
            "style": "default",
            "animated": False,
        },
        "story_structure": "high",
        "transition_config": {
            "style": "dynamic",
            "energy": "high",
            "crossfade_duration": 0.3,
        },
        "energy": "high",
    },

    "raw_footage": {
        "operations": [
            "highlight_select", "story_compose", "add_transitions",
            "add_captions",
        ],
        "highlight_weights": {
            "motion": 0.25,
            "audio_peak": 0.20,
            "speech": 0.10,
            "shot_variety": 0.15,
            "face": 0.10,
            "visual_relevance": 0.20,
        },
        "caption_config": {
            "speaker_tags": False,
            "style": "default",
            "animated": False,
        },
        "story_structure": "medium",
        "transition_config": {
            "style": "crossfade",
            "energy": "medium",
            "crossfade_duration": 0.5,
        },
        "energy": "medium",
    },

    "cooking": {
        "operations": ["remove_silence", "add_captions", "add_transitions"],
        "highlight_weights": {
            "motion": 0.15,
            "audio_peak": 0.10,
            "speech": 0.35,
            "shot_variety": 0.10,
            "face": 0.10,
            "visual_relevance": 0.20,
        },
        "caption_config": {
            "speaker_tags": False,
            "style": "default",
            "animated": False,
        },
        "story_structure": "chronological",
        "transition_config": {
            "style": "crossfade",
            "energy": "low",
            "crossfade_duration": 0.6,
        },
        "energy": "low",
    },

    "music_performance": {
        "operations": [
            "highlight_select", "story_compose", "beat_sync",
            "add_transitions",
        ],
        "highlight_weights": {
            "motion": 0.25,
            "audio_peak": 0.30,
            "speech": 0.00,
            "shot_variety": 0.15,
            "face": 0.10,
            "visual_relevance": 0.20,
        },
        "caption_config": {
            "speaker_tags": False,
            "style": "default",
            "animated": False,
        },
        "story_structure": "high",
        "transition_config": {
            "style": "dynamic",
            "energy": "high",
            "crossfade_duration": 0.2,
        },
        "energy": "high",
    },
}


# ── Intent overlays ─────────────────────────────────────────────────────────

_INTENT_OVERLAYS = {
    "clean_up": {
        "operations_add": ["remove_silence"],
        "operations_remove": ["highlight_select", "story_compose", "beat_sync"],
        "story_structure": "chronological",
        "energy_override": None,  # keep base energy
    },
    "highlight_reel": {
        "operations_add": ["highlight_select", "story_compose", "add_transitions"],
        "operations_remove": [],
        "caption_config_override": {
            "animated": True,
            "style": "tiktok_bold",
        },
        "story_structure": "high",
        "energy_override": "high",
    },
    "recap": {
        "operations_add": ["highlight_select", "add_captions"],
        "operations_remove": ["beat_sync"],
        "story_structure": "medium",
        "energy_override": "medium",
    },
    "reformat": {
        "operations_add": [],
        "operations_remove": [],
        "story_structure": None,  # keep base
        "energy_override": None,
    },
    "full_edit": {
        "operations_add": ["add_captions", "add_transitions"],
        "operations_remove": [],
        "story_structure": None,  # keep base
        "energy_override": None,
    },
}


def _merge_strategy(base: dict, overlay: dict) -> dict:
    """Merge intent overlay onto base video-type strategy."""
    import copy
    strategy = copy.deepcopy(base)

    # Merge operations
    ops = set(strategy.get("operations", []))
    ops.update(overlay.get("operations_add", []))
    ops -= set(overlay.get("operations_remove", []))
    strategy["operations"] = sorted(ops)

    # Override story structure if specified
    if overlay.get("story_structure"):
        strategy["story_structure"] = overlay["story_structure"]

    # Override energy if specified
    if overlay.get("energy_override"):
        strategy["energy"] = overlay["energy_override"]
        strategy["transition_config"]["energy"] = overlay["energy_override"]

    # Override caption config fields if specified
    cap_override = overlay.get("caption_config_override")
    if cap_override:
        strategy["caption_config"].update(cap_override)

    return strategy
