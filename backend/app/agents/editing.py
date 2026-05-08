"""Editing Agent — builds Timeline DSL from plan + signals.

Phase 2: supports highlight-based clip selection, story structure, and beat sync.
"""

from app.core.config import settings
from app.core.logger import get_logger
from app.dsl.schema import ClipRef, FormatSpec, MusicTrack, Timeline, VoiceoverTrack
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

    # Apply transitions (strategy-aware)
    if "add_transitions" in operations:
        clips = _apply_transitions(clips, plan)

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

    # Music + voiceover. Prefer explicitly tagged roles from the upload form;
    # if none are tagged, fall back to "first audio file is music" for back-compat.
    music = None
    voiceover = None

    music_candidates = storage.raw_files_by_role("music")
    voiceover_candidates = storage.raw_files_by_role("voiceover")
    untagged_audio = [
        f for f in storage.raw_audio_files()
        if storage.role_of(f.name) == "music"  # role_of falls back to "music" for audio
        and f not in music_candidates
        and f not in voiceover_candidates
    ]

    music_pick = music_candidates[0] if music_candidates else (
        untagged_audio[0] if untagged_audio else None
    )
    if music_pick:
        music = MusicTrack(
            source=music_pick.name,
            sync_beats="beat_sync" in operations,
        )

    if voiceover_candidates:
        # Lower music volume when voiceover is present so dialogue stays audible.
        voiceover = VoiceoverTrack(source=voiceover_candidates[0].name)
        if music and voiceover.duck_music:
            music.volume = min(music.volume, 0.15)

    # Image clips: any image files uploaded to raw/ are auto-prepended as
    # 3-second intro slides with a default Ken Burns zoom. Order is by
    # filename so users can control the sequence by naming (00_intro.jpg, ...).
    image_clips = _build_image_intros(storage)
    if image_clips:
        clips = image_clips + clips
        log.info("Prepended %d image intro slide(s)", len(image_clips))

    # Smart crop: when output aspect ≠ source aspect, use face data to choose
    # a crop window per video clip instead of letterboxing.
    _apply_smart_crop(clips, fmt, signals)

    timeline = Timeline(format=fmt, clips=clips, music=music, voiceover=voiceover)
    log.info(
        "Timeline built: %d clips, %.1fs total, format=%s",
        len(clips), timeline.total_duration(), fmt.aspect,
    )
    return timeline


DEFAULT_IMAGE_DURATION = 3.0
DEFAULT_KEN_BURNS_ZOOM = 1.15

# When the output aspect differs from the source aspect by less than this
# fraction, smart crop is a no-op and we skip computing it.
ASPECT_MISMATCH_TOLERANCE = 0.02


def _apply_smart_crop(
    clips: list[ClipRef],
    fmt: FormatSpec,
    signals: dict,
) -> None:
    """Set `crop_box` on each video clip when output aspect differs from
    source aspect AND face detections fall within the clip's time range.

    Mutates the clips in place. No-op for image clips and clips whose
    sources are pure-aspect-match. Falls back to centered crop when no
    faces are detected.
    """
    target_aspect = fmt.width / max(1, fmt.height)
    manifest = signals.get("media_manifest", {})
    source_dims: dict[str, tuple[int, int]] = {
        f["filename"]: (int(f.get("width", 0)), int(f.get("height", 0)))
        for f in manifest.get("files", [])
        if f.get("width", 0) > 0
    }
    faces = signals.get("faces") or {}
    faces_by_source: dict[str, list[dict]] = {
        track["source"]: track.get("detections", [])
        for track in faces.get("tracks", [])
    }

    for clip in clips:
        if clip.clip_type == "image":
            continue
        dims = source_dims.get(clip.source)
        if not dims:
            continue
        sw, sh = dims
        if sh <= 0:
            continue
        source_aspect = sw / sh
        if abs(source_aspect - target_aspect) / target_aspect < ASPECT_MISMATCH_TOLERANCE:
            continue  # aspects match — no crop needed

        clip.crop_box = _compute_crop_box(
            source_aspect=source_aspect,
            target_aspect=target_aspect,
            face_detections=faces_by_source.get(clip.source, []),
            clip_start=clip.start,
            clip_end=clip.end,
        )


def _compute_crop_box(
    source_aspect: float,
    target_aspect: float,
    face_detections: list[dict],
    clip_start: float,
    clip_end: float,
) -> dict:
    """Compute a relative crop window (w, h, x, y all in [0, 1]) that keeps
    faces centered. Returns a centered crop when no faces match the range."""
    if source_aspect > target_aspect:
        # Source is wider than target → narrow vertical crop. Height stays
        # full, width is reduced to match target aspect.
        w = target_aspect / source_aspect
        h = 1.0
        # Average face center across the clip's time range
        cx = _average_face_center_x(face_detections, clip_start, clip_end)
        # Position so the crop is centered on cx, clamped within [0, 1-w]
        x = max(0.0, min(1.0 - w, cx - w / 2))
        y = 0.0
    else:
        # Source is taller than target → wide horizontal crop. Width stays
        # full, height is reduced. Center vertically (face data here would
        # require a y-centroid — skipping for v1).
        w = 1.0
        h = source_aspect / target_aspect
        x = 0.0
        y = max(0.0, min(1.0 - h, 0.5 - h / 2))

    return {"w": round(w, 4), "h": round(h, 4),
            "x": round(x, 4), "y": round(y, 4)}


def _average_face_center_x(
    detections: list[dict], clip_start: float, clip_end: float,
) -> float:
    """Mean x-center of all face boxes within [clip_start, clip_end].
    Returns 0.5 (centered) if no faces match the range."""
    centers = []
    for det in detections:
        t = det.get("time", 0)
        if t < clip_start or t > clip_end:
            continue
        for box in det.get("boxes", []):
            cx = box.get("x", 0) + box.get("w", 0) / 2
            centers.append(cx)
    if not centers:
        return 0.5
    return sum(centers) / len(centers)


def _build_image_intros(storage: StorageManager) -> list[ClipRef]:
    """Build a ClipRef per uploaded image file, with default Ken Burns zoom.

    Image clips are returned in alphabetical order so users can shape the
    sequence via filenames (00_title.png, 01_subtitle.jpg, ...).
    """
    images = sorted(storage.raw_image_files(), key=lambda p: p.name)
    return [
        ClipRef(
            source=img.name,
            start=0.0,
            end=DEFAULT_IMAGE_DURATION,
            zoom=DEFAULT_KEN_BURNS_ZOOM,
            clip_type="image",
            transition_in="fade" if i == 0 else "crossfade",
            transition_duration=0.4,
        )
        for i, img in enumerate(images)
    ]


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

        # Only adjust if the shift is small (< 0.25s) for tighter beat sync
        adjusted_duration = beat_end - output_cursor
        if adjusted_duration > 0.5 and abs(adjusted_duration - duration) < 0.25:
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


def _apply_transitions(clips: list[ClipRef], plan: dict) -> list[ClipRef]:
    """Assign transition types between clips based on strategy/energy."""
    if len(clips) <= 1:
        return clips

    strategy = plan.get("strategy", {})
    transition_config = strategy.get("transition_config", {})
    energy = transition_config.get("energy", plan.get("style", {}).get("energy", "medium"))
    transition_style = transition_config.get("style", plan.get("style", {}).get("transitions", "auto"))

    if transition_style == "none":
        return clips

    # Get crossfade duration from strategy or use defaults
    crossfade_dur = transition_config.get("crossfade_duration")

    for i, clip in enumerate(clips):
        if i == 0:
            # First clip: fade in from black
            clip.transition_in = "fade"
            clip.transition_duration = 0.5
            continue

        if transition_style == "minimal":
            # Minimal: simple cuts with occasional crossfade
            if i % 5 == 0:
                clip.transition_in = "crossfade"
                clip.transition_duration = crossfade_dur or 0.5
            # else: hard cut (no transition)
        elif energy == "high" or transition_style == "dynamic":
            # High energy: alternate between crossfade and flash
            if i % 4 == 0:
                clip.transition_in = "flash"
                clip.transition_duration = 0.2
            else:
                clip.transition_in = "crossfade"
                clip.transition_duration = crossfade_dur or 0.3
        elif energy == "low":
            # Low energy: smooth crossfades
            clip.transition_in = "crossfade"
            clip.transition_duration = crossfade_dur or 0.8
        else:
            # Medium: standard crossfades
            clip.transition_in = "crossfade"
            clip.transition_duration = crossfade_dur or 0.5

    return clips


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
