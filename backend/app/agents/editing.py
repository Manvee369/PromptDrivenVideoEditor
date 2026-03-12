"""Editing Agent — builds Timeline DSL from plan + signals.

Phase 2: supports highlight-based clip selection, story structure, and beat sync.
"""

from app.core.config import settings
from app.core.logger import get_logger
from app.dsl.schema import ClipRef, FormatSpec, MusicTrack, Timeline
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


def build_timeline(plan: dict, signals: dict, storage: StorageManager) -> Timeline:
    """
    Convert plan + signals into a Timeline DSL object.

    Modes:
    1. highlight_select + story_compose → use story-ordered highlights as clips
    2. highlight_select (no story) → use top-N highlights in time order
    3. remove_silence → build clips from speech regions
    4. Default → full source clips
    """
    style = plan.get("style", {})
    fmt = FormatSpec(
        width=style.get("width", settings.default_width),
        height=style.get("height", settings.default_height),
        fps=settings.default_fps,
        aspect=style.get("aspect", settings.default_aspect),
    )

    operations = plan.get("operations", [])
    manifest = signals.get("media_manifest", {})
    silence = signals.get("silence", {})
    story = signals.get("story")
    highlights = signals.get("highlights")

    clips = []

    if "story_compose" in operations and story:
        # Use story-ordered segments
        clips = _clips_from_story(story)
        log.info("Built clips from story: %d segments", len(clips))

    elif "highlight_select" in operations and highlights:
        # Use top highlights, ordered by time
        clips = _clips_from_highlights(highlights, plan)
        log.info("Built clips from highlights: %d segments", len(clips))

    else:
        # Phase 1 fallback: silence removal or full clips
        for file_info in manifest.get("files", []):
            if file_info.get("width", 0) == 0:
                continue

            filename = file_info["filename"]
            duration = file_info["duration"]

            if "remove_silence" in operations:
                speech_regions = _get_speech_regions(silence, filename)
                if speech_regions:
                    for region in speech_regions:
                        clips.append(ClipRef(
                            source=filename,
                            start=region["start"],
                            end=region["end"],
                        ))
                else:
                    clips.append(ClipRef(source=filename, start=0.0, end=duration))
            else:
                clips.append(ClipRef(source=filename, start=0.0, end=duration))

    # Apply speed modification
    if "slow_motion" in operations:
        for clip in clips:
            clip.speed = 0.5

    # Apply filters
    if "black_and_white" in operations:
        for clip in clips:
            clip.filters.append("colorchannelmixer=.3:.4:.3:0:.3:.4:.3:0:.3:.4:.3")

    # Beat sync: snap cut points to beats
    if "beat_sync" in operations:
        music_analysis = signals.get("music_analysis")
        if music_analysis and music_analysis.get("beats"):
            clips = _beat_sync_clips(clips, music_analysis["beats"])
            log.info("Beat-synced %d clips", len(clips))

    # Trim to target duration
    target = plan.get("target_duration")
    if target and target > 0:
        clips = _trim_to_duration(clips, target)

    # Music track
    music = None
    audio_files = storage.raw_audio_files()
    if audio_files:
        music = MusicTrack(
            source=audio_files[0].name,
            sync_beats="beat_sync" in operations,
        )

    timeline = Timeline(format=fmt, clips=clips, music=music)
    log.info(
        "Timeline built: %d clips, %.1fs total, format=%s",
        len(clips), timeline.total_duration(), fmt.aspect,
    )
    return timeline


def _clips_from_story(story: list[dict]) -> list[ClipRef]:
    """Convert story segments to ClipRef list (already ordered by story agent)."""
    return [
        ClipRef(source=s["source"], start=s["start"], end=s["end"])
        for s in story
    ]


def _clips_from_highlights(highlights: list[dict], plan: dict) -> list[ClipRef]:
    """Pick top highlights, sort by time for coherent playback."""
    target = plan.get("target_duration")

    # Determine how many to pick
    if target:
        selected = []
        total = 0.0
        for h in highlights:
            if total + h["duration"] > target:
                break
            selected.append(h)
            total += h["duration"]
    else:
        # Take top 10 or all if fewer
        selected = highlights[:10]

    # Sort by source file then time for coherent playback
    selected.sort(key=lambda h: (h["source"], h["start"]))

    return [
        ClipRef(source=h["source"], start=h["start"], end=h["end"])
        for h in selected
    ]


def _beat_sync_clips(clips: list[ClipRef], beats: list[float]) -> list[ClipRef]:
    """Snap clip boundaries to nearest beat."""
    import numpy as np
    beats_arr = np.array(beats)

    # We need to map output-timeline positions to beats.
    # For each clip, try to adjust its duration to end on a beat.
    synced = []
    output_cursor = 0.0

    for clip in clips:
        duration = clip.effective_duration

        # Find the nearest beat to where this clip would end in output timeline
        target_end = output_cursor + duration
        nearest_idx = int(np.argmin(np.abs(beats_arr - target_end)))
        beat_end = float(beats_arr[nearest_idx])

        # Only adjust if the shift is small (< 0.5s)
        adjusted_duration = beat_end - output_cursor
        if adjusted_duration > 0.5 and abs(adjusted_duration - duration) < 0.5:
            # Adjust the source end time
            new_end = clip.start + (adjusted_duration * clip.speed)
            synced.append(ClipRef(
                source=clip.source,
                start=clip.start,
                end=round(new_end, 3),
                speed=clip.speed,
                volume=clip.volume,
                filters=list(clip.filters),
            ))
            output_cursor = beat_end
        else:
            synced.append(clip)
            output_cursor += duration

    return synced


def _get_speech_regions(silence_data: dict, filename: str) -> list[dict]:
    """Get speech regions for a specific file from silence signals."""
    for track in silence_data.get("tracks", []):
        if track["source"] == filename:
            return track.get("speech_regions", [])
    return []


def _trim_to_duration(clips: list[ClipRef], target: float) -> list[ClipRef]:
    """Trim clip list to fit within target duration."""
    total = sum(c.effective_duration for c in clips)
    if total <= target:
        return clips

    result = []
    remaining = target
    for clip in clips:
        dur = clip.effective_duration
        if dur <= remaining:
            result.append(clip)
            remaining -= dur
        else:
            trimmed_end = clip.start + (remaining * clip.speed)
            result.append(ClipRef(
                source=clip.source,
                start=clip.start,
                end=trimmed_end,
                speed=clip.speed,
                volume=clip.volume,
                filters=list(clip.filters),
            ))
            break

    return result
