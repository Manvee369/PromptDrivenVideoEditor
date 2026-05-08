"""Workflow gating — decide which intelligence stages are needed for a job.

The full pipeline runs Whisper + SigLIP + pyannote + MediaPipe + PySceneDetect
for every job, which is overkill for simple "make it black-and-white" prompts.
This module derives the minimum set of intelligence signals required given the
operations the planner asked for, so the pipeline can skip expensive stages.
"""

from __future__ import annotations


# Operations that don't need any LLM-driven intelligence — pure transforms.
SIMPLE_OPERATIONS: frozenset[str] = frozenset({
    "remove_silence",
    "add_captions",
    "black_and_white",
    "slow_motion",
    "trim",
    "add_transitions",
})


def is_simple_workflow(operations: set[str]) -> bool:
    """True iff every requested operation is a simple transform.

    Simple workflows skip content classification and the LLM planner — the
    rule-based pre-plan is enough.
    """
    return bool(operations) and operations.issubset(SIMPLE_OPERATIONS)


def required_signals(operations: set[str]) -> set[str]:
    """The minimum set of intelligence signals required for the operations.

    Signal names match storage_manager naming. Signals not in this set can
    be skipped during the intelligence stage. Signals always include:
    - media_manifest (set up by preprocessing)
    - transcript (cheap-ish, almost always informative)
    - silence (cheap, broadly useful)
    """
    needed = {"media_manifest", "transcript", "silence"}

    if "remove_silence" in operations:
        needed |= {"audio_energy"}

    if "highlight_select" in operations or "story_compose" in operations:
        # Highlight scoring uses motion + audio peaks + faces + shots + visual.
        needed |= {"audio_energy", "shots", "motion", "faces", "visual_scores"}

    if "story_compose" in operations:
        # Story uses shot boundaries to anchor structure.
        needed |= {"shots"}

    if "beat_sync" in operations:
        needed |= {"music_analysis"}

    if "add_captions" in operations:
        # Diarization powers speaker-tagged captions.
        needed |= {"diarization"}

    return needed
