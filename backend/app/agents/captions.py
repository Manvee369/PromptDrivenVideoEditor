"""Caption Agent — generates subtitles from transcript mapped to timeline.

Phase 2: supports animated word-by-word TikTok-style captions.
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
        "fontsize_pct": 0.045,  # relative to height
        "primary": "&H00FFFFFF",  # white
        "outline": "&H00000000",  # black
        "bold": -1,
        "outline_width": 3,
        "shadow": 1,
        "alignment": 2,  # bottom center
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
        "alignment": 5,  # center middle
        "margin_v_pct": 0.02,
    },
}

# Words that get highlighted/emphasized
HYPE_WORDS = {
    "amazing", "insane", "crazy", "fire", "best", "worst", "never", "always",
    "incredible", "unbelievable", "huge", "massive", "epic", "legendary",
    "wow", "omg", "no", "yes", "what", "how", "why", "stop", "go",
    "win", "lose", "kill", "clutch", "perfect",
}


def generate_captions(
    timeline: Timeline, signals: dict, storage: StorageManager
) -> Timeline:
    """
    Map transcript segments onto timeline clip boundaries.
    Adjusts timestamps for removed silence gaps.

    Returns Timeline with captions[] populated.
    """
    transcript = signals.get("transcript", {})
    if not transcript.get("tracks"):
        log.warning("No transcript data available for captions")
        return timeline

    time_map = _build_time_map(timeline)

    captions = []
    for track in transcript["tracks"]:
        source = track["source"]
        for seg in track.get("segments", []):
            out_start = _map_time(time_map, source, seg["start"])
            out_end = _map_time(time_map, source, seg["end"])

            if out_start is not None and out_end is not None and out_end > out_start:
                captions.append(CaptionEntry(
                    start=round(out_start, 3),
                    end=round(out_end, 3),
                    text=seg["text"],
                ))

    timeline.captions = captions
    log.info("Generated %d caption entries", len(captions))
    return timeline


def _build_time_map(timeline: Timeline) -> list[dict]:
    """Build source-time → output-time mapping from clip list."""
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


def _map_time(time_map: list[dict], source: str, src_time: float) -> float | None:
    """Map a source timestamp to output timeline position."""
    for m in time_map:
        if m["source"] == source and m["src_start"] <= src_time <= m["src_end"]:
            offset = (src_time - m["src_start"]) / m["speed"]
            return m["out_start"] + offset
    return None


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
                # Highlighted word: yellow, slightly bigger with scale animation
                text = (
                    f"{{\\fscx120\\fscy120\\t(0,100,\\fscx100\\fscy100)}}"
                    f"{escaped_word}"
                )
                lines.append(f"Dialogue: 1,{start_ts},{end_ts},Highlight,,0,0,0,,{text}")
            else:
                # Normal word with subtle fade-in
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
