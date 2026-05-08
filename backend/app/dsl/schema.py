"""Timeline DSL — the single source of truth for rendering."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.config import settings


class FormatSpec(BaseModel):
    """Output video format specification."""
    width: int = settings.default_width
    height: int = settings.default_height
    fps: int = settings.default_fps
    aspect: str = settings.default_aspect


class ClipRef(BaseModel):
    """A reference to a segment of a source file.

    `clip_type` decides how the renderer interprets the source:
        "video": source is a video file; start/end mark the in/out points.
        "image": source is a still image; start should be 0 and end is the
            duration the image is shown for. Audio is silent. The default
            zoom > 1.0 produces a Ken Burns effect.
    """
    source: str                                     # filename in raw/
    start: float                                    # seconds
    end: float                                      # seconds
    speed: float = 1.0
    volume: float = 1.0
    transition_in: str | None = None                # "crossfade", "fade", "flash", None
    transition_duration: float = 0.3
    zoom: float = 1.0                               # 1.0 = no zoom, 1.3 = 30% zoom-in
    filters: list[str] = Field(default_factory=list)  # raw FFmpeg filter strings
    clip_type: str = "video"                        # "video" | "image"
    # Optional color grade preset (see render/color_grading.py). None or
    # "none" → no grade applied. Cinematic / warm / teal_orange etc.
    color_grade: str | None = None
    # Optional smart crop window in relative source coordinates (each value 0-1).
    # When set, the renderer emits `crop=iw*w:ih*h:iw*x:ih*y` instead of
    # letterboxing via pad — used to keep faces in frame on aspect-ratio
    # mismatches (e.g., 16:9 source → 9:16 output). None → use scale+pad.
    crop_box: dict | None = None

    @property
    def raw_duration(self) -> float:
        """Duration before speed adjustment."""
        return self.end - self.start

    @property
    def effective_duration(self) -> float:
        """Duration after speed adjustment."""
        return self.raw_duration / self.speed if self.speed > 0 else self.raw_duration


class CaptionEntry(BaseModel):
    """A single subtitle/caption.

    `words` carries optional word-level timing for karaoke-style rendering.
    Each entry: {start, end, text, probability}. When present, the captions
    agent's karaoke style emits ASS \\k tags for word-by-word highlighting.
    """
    start: float                    # seconds in output timeline
    end: float
    text: str
    style: str = "default"          # "default", "tiktok_bold", etc.
    position: str = "bottom_center"
    words: list[dict] | None = None  # word-level timing (output-timeline coords)


class MusicTrack(BaseModel):
    """Background music configuration."""
    source: str | None = None       # filename in raw/ or None for no music
    volume: float = 0.3
    fade_in: float = 0.0
    fade_out: float = 2.0
    sync_beats: bool = False        # Phase 2


class VoiceoverTrack(BaseModel):
    """Voiceover audio overlaid on the main timeline.

    Mixed at a higher default volume than music since it's the focal
    audio. Can start at an offset (0.0 = aligned with timeline start).
    """
    source: str | None = None       # filename in raw/ or None for no voiceover
    volume: float = 1.0
    offset: float = 0.0             # seconds to delay voiceover start
    fade_in: float = 0.0
    fade_out: float = 0.0
    duck_music: bool = True         # auto-lower music volume when voiceover plays


class Timeline(BaseModel):
    """The complete editing specification. Single source of truth for rendering."""
    version: str = "1.0"
    format: FormatSpec = Field(default_factory=FormatSpec)
    clips: list[ClipRef]
    captions: list[CaptionEntry] = Field(default_factory=list)
    music: MusicTrack | None = None
    voiceover: VoiceoverTrack | None = None
    # Default color grade applied to every clip that doesn't override its own.
    color_grade: str | None = None

    def total_duration(self) -> float:
        """Sum of effective clip durations, accounting for crossfade overlap."""
        total = sum(c.effective_duration for c in self.clips)
        for c in self.clips[1:]:
            if c.transition_in == "crossfade":
                total -= c.transition_duration
        return total

    def validate_sources(self, available_files: list[str]) -> list[str]:
        """Return list of source files referenced but not available."""
        missing = []
        for clip in self.clips:
            if clip.source not in available_files:
                missing.append(clip.source)
        if self.music and self.music.source and self.music.source not in available_files:
            missing.append(self.music.source)
        if self.voiceover and self.voiceover.source and self.voiceover.source not in available_files:
            missing.append(self.voiceover.source)
        return missing
