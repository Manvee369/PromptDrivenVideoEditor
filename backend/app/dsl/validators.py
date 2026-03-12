"""Timeline DSL validation."""

from app.dsl.schema import Timeline
from app.storage.storage_manager import StorageManager


def validate_timeline(timeline: Timeline, storage: StorageManager) -> list[str]:
    """
    Validate a Timeline against storage contents and structural rules.
    Returns list of error strings (empty = valid).
    """
    errors = []

    # Check source files exist
    available = [f.name for f in storage.raw_files()]
    missing = timeline.validate_sources(available)
    for m in missing:
        errors.append(f"Source file not found: {m}")

    # Check clip time ranges
    for i, clip in enumerate(timeline.clips):
        if clip.start < 0:
            errors.append(f"Clip {i}: negative start time {clip.start}")
        if clip.end <= clip.start:
            errors.append(f"Clip {i}: end ({clip.end}) must be > start ({clip.start})")
        if clip.speed <= 0:
            errors.append(f"Clip {i}: speed must be positive, got {clip.speed}")
        if clip.transition_duration < 0:
            errors.append(f"Clip {i}: negative transition duration")
        if clip.transition_duration > clip.effective_duration:
            errors.append(f"Clip {i}: transition duration exceeds clip duration")

    # Check caption time ranges
    for i, cap in enumerate(timeline.captions):
        if cap.start < 0:
            errors.append(f"Caption {i}: negative start time")
        if cap.end <= cap.start:
            errors.append(f"Caption {i}: end must be > start")

    # Check format
    if timeline.format.width <= 0 or timeline.format.height <= 0:
        errors.append("Format: width and height must be positive")
    if timeline.format.fps <= 0:
        errors.append("Format: fps must be positive")

    return errors
