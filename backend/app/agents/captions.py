"""Caption Agent — generates subtitles from transcript mapped to timeline.

Phase 2: supports animated word-by-word TikTok-style captions.
Finds transcript segments that overlap with selected clips (even partially).
"""

from pathlib import Path

from app.core.logger import get_logger
from app.dsl.schema import CaptionEntry, Timeline
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# ASS style definitions
STYLES = {
    "default": {
        "fontname": "Arial",
        "fontsize_pct": 0.045,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "bold": -1,
        "outline_width": 3,
        "shadow": 1,
        "alignment": 2,
        "margin_v_pct": 0.08,
    },
    "tiktok_bold": {
        "fontname": "Arial",
        "fontsize_pct": 0.065,
        "primary": "&H00FFFFFF",
        "outline": "&H00000000",
        "bold": -1,
        "outline_width": 4,
        "shadow": 0,
        "alignment": 5,
        "margin_v_pct": 0.02,
    },
}

HYPE_WORDS = {
    "amazing", "insane", "crazy", "fire", "best", "worst", "never", "always",
    "incredible", "unbelievable", "huge", "massive", "epic", "legendary",
    "wow", "omg", "no", "yes", "what", "how", "why", "stop", "go",
    "win", "lose", "kill", "clutch", "perfect", "champion", "victory",
    "overtake", "crash", "fastest", "record", "lead", "first", "last",
}


def generate_captions(
    timeline: Timeline, signals: dict, storage: StorageManager,
    min_clip_duration: float = 2.0,
    min_overlap_ratio: float = 0.4,
) -> Timeline:
    """
    Find transcript segments that overlap with each clip in the timeline,
    then map them to the output timeline position.

    Filtering rules for clean, human-like captions:
    - Skip clips shorter than min_clip_duration (quick cuts = visual impact, no text)
    - Only include a transcript segment if at least min_overlap_ratio (40%) of it
      falls within the clip — balances clean captions with coverage on short clips
    - One caption at a time — resolve overlapping captions by keeping the longer one
    """
    transcript = signals.get("transcript", {})
    if not transcript.get("tracks"):
        log.warning("No transcript data available for captions")
        return timeline

    # Build lookup: source filename -> list of transcript segments
    seg_lookup = {}
    for track in transcript["tracks"]:
        seg_lookup[track["source"]] = track.get("segments", [])

    # Build speaker lookup from diarization if available
    speaker_lookup = _build_speaker_lookup(signals.get("diarization"))

    time_map = _build_time_map(timeline)
    captions = []

    for mapping in time_map:
        source = mapping["source"]
        src_start = mapping["src_start"]
        src_end = mapping["src_end"]
        clip_duration = src_end - src_start
        out_start = mapping["out_start"]
        speed = mapping["speed"]

        # Rule 1: skip short clips — they're quick cuts, no captions needed
        if clip_duration < min_clip_duration:
            continue

        segments = seg_lookup.get(source, [])

        for seg in segments:
            seg_duration = seg["end"] - seg["start"]
            if seg_duration <= 0:
                continue

            # Check overlap
            overlap_start = max(seg["start"], src_start)
            overlap_end = min(seg["end"], src_end)

            if overlap_end <= overlap_start:
                continue

            overlap_duration = overlap_end - overlap_start

            # Rule 2: only include if most of the sentence is audible in this clip
            if overlap_duration / seg_duration < min_overlap_ratio:
                continue

            # Map to output time
            cap_out_start = out_start + (overlap_start - src_start) / speed
            cap_out_end = out_start + (overlap_end - src_start) / speed

            if cap_out_end > cap_out_start + 0.3:
                text = seg["text"].strip()
                # Prefix with speaker label if multi-speaker
                speaker = _get_speaker(speaker_lookup, source, seg["start"])
                if speaker:
                    text = f"[{speaker}] {text}"
                captions.append(CaptionEntry(
                    start=round(cap_out_start, 3),
                    end=round(cap_out_end, 3),
                    text=text,
                ))

    # Remove duplicates then resolve overlapping captions
    captions = _deduplicate_captions(captions)
    captions = _resolve_overlapping_captions(captions)

    timeline.captions = captions
    log.info("Generated %d caption entries", len(captions))
    return timeline


def _build_time_map(timeline: Timeline) -> list[dict]:
    """Build source-time -> output-time mapping from clip list."""
    mappings = []
    output_cursor = 0.0

    for clip in timeline.clips:
        out_duration = clip.effective_duration
        mappings.append({
            "source": clip.source,
            "src_start": clip.start,
            "src_end": clip.end,
            "out_start": output_cursor,
            "out_end": output_cursor + out_duration,
            "speed": clip.speed,
        })
        output_cursor += out_duration

    return mappings


def _deduplicate_captions(captions: list[CaptionEntry]) -> list[CaptionEntry]:
    """Remove duplicate captions that have the same text and overlapping times."""
    if not captions:
        return captions

    # Sort by start time
    captions.sort(key=lambda c: c.start)
    result = [captions[0]]

    for cap in captions[1:]:
        prev = result[-1]
        # Skip if same text and start times are very close
        if cap.text == prev.text and abs(cap.start - prev.start) < 0.5:
            # Keep the longer one
            if cap.end > prev.end:
                result[-1] = cap
            continue
        result.append(cap)

    return result


def _resolve_overlapping_captions(captions: list[CaptionEntry]) -> list[CaptionEntry]:
    """Ensure only one caption is on screen at a time.
    When two captions overlap, keep the longer one."""
    if len(captions) <= 1:
        return captions

    captions.sort(key=lambda c: c.start)
    result = [captions[0]]

    for cap in captions[1:]:
        prev = result[-1]
        if cap.start < prev.end:
            # Overlap — keep whichever is longer
            prev_dur = prev.end - prev.start
            cap_dur = cap.end - cap.start
            if cap_dur > prev_dur:
                result[-1] = cap
        else:
            result.append(cap)

    return result


def generate_ass_file(
    captions: list[CaptionEntry],
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    style_name: str = "default",
    animated: bool = False,
) -> Path:
    """
    Convert CaptionEntry list to ASS subtitle file.

    Args:
        animated: If True, generate word-by-word animated captions (TikTok style).
    """
    style_def = STYLES.get(style_name, STYLES["default"])
    fontsize = int(height * style_def["fontsize_pct"])
    margin_v = int(height * style_def["margin_v_pct"])

    header = f"""[Script Info]
Title: Video Captions
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style_def['fontname']},{fontsize},{style_def['primary']},&H000000FF,{style_def['outline']},&H80000000,{style_def['bold']},0,0,0,100,100,0,0,1,{style_def['outline_width']},{style_def['shadow']},{style_def['alignment']},20,20,{margin_v},1
Style: Highlight,{style_def['fontname']},{int(fontsize * 1.15)},&H0000FFFF,&H000000FF,{style_def['outline']},&H80000000,-1,0,0,0,100,100,0,0,1,{style_def['outline_width']},{style_def['shadow']},{style_def['alignment']},20,20,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    lines = [header.strip()]

    if animated:
        lines.extend(_generate_animated_lines(captions))
    else:
        lines.extend(_generate_static_lines(captions))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Generated ASS file: %s (%d entries, animated=%s)",
             output_path.name, len(captions), animated)
    return output_path


def _generate_static_lines(captions: list[CaptionEntry]) -> list[str]:
    """Simple static subtitle lines."""
    lines = []
    for cap in captions:
        start_ts = _seconds_to_ass_time(cap.start)
        end_ts = _seconds_to_ass_time(cap.end)
        text = _escape_ass(cap.text)
        lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}")
    return lines


def _generate_animated_lines(captions: list[CaptionEntry]) -> list[str]:
    """
    Word-by-word animated captions — each word appears with a pop-in effect,
    and hype words get highlighted.
    """
    lines = []

    for cap in captions:
        words = cap.text.strip().split()
        if not words:
            continue

        duration = cap.end - cap.start
        word_duration = duration / len(words)

        for i, word in enumerate(words):
            w_start = cap.start + i * word_duration
            w_end = cap.start + (i + 1) * word_duration
            start_ts = _seconds_to_ass_time(w_start)
            end_ts = _seconds_to_ass_time(w_end)

            clean_word = word.strip(".,!?;:\"'").lower()
            escaped_word = _escape_ass(word)

            if clean_word in HYPE_WORDS:
                text = (
                    f"{{\\fscx120\\fscy120\\t(0,100,\\fscx100\\fscy100)}}"
                    f"{escaped_word}"
                )
                lines.append(f"Dialogue: 1,{start_ts},{end_ts},Highlight,,0,0,0,,{text}")
            else:
                text = (
                    f"{{\\fad(80,0)}}"
                    f"{escaped_word}"
                )
                lines.append(f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}")

    return lines


def _escape_ass(text: str) -> str:
    """Escape special ASS characters."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format: H:MM:SS.CC"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _build_speaker_lookup(diarization: dict | None) -> dict:
    """Build lookup: (source, time) -> speaker label. Only for multi-speaker tracks."""
    if not diarization:
        return {}
    lookup = {}
    for track in diarization.get("tracks", []):
        if track.get("num_speakers", 1) <= 1:
            continue
        source = track["source"]
        lookup[source] = track.get("segments", [])
    return lookup


def _get_speaker(speaker_lookup: dict, source: str, time: float) -> str | None:
    """Find speaker label for a given source and time."""
    segments = speaker_lookup.get(source)
    if not segments:
        return None
    for seg in segments:
        if seg["start"] <= time <= seg["end"]:
            return seg["speaker"]
    return None
