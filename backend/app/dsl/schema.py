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
    """A reference to a segment of a source file."""
    source: str                                     # filename in raw/
    start: float                                    # seconds
    end: float                                      # seconds
    speed: float = 1.0
    volume: float = 1.0
    transition_in: str | None = None                # "fade", "flash", "cut"
    transition_duration: float = 0.0
    filters: list[str] = Field(default_factory=list)  # raw FFmpeg filter strings

    @property
    def raw_duration(self) -> float:
        """Duration before speed adjustment."""
        return self.end - self.start

    @property
    def effective_duration(self) -> float:
        """Duration after speed adjustment."""
        return self.raw_duration / self.speed if self.speed > 0 else self.raw_duration


class CaptionEntry(BaseModel):
    """A single subtitle/caption."""
    start: float                    # seconds in output timeline
    end: float
    text: str
    style: str = "default"          # "default", "tiktok_bold", etc.
    position: str = "bottom_center"


class MusicTrack(BaseModel):
    """Background music configuration."""
    source: str | None = None       # filename in raw/ or None for no music
    volume: float = 0.3
    fade_in: float = 0.0
    fade_out: float = 2.0
    sync_beats: bool = False        # Phase 2


class Timeline(BaseModel):
    """The complete editing specification. Single source of truth for rendering."""
    version: str = "1.0"
    format: FormatSpec = Field(default_factory=FormatSpec)
    clips: list[ClipRef]
    captions: list[CaptionEntry] = Field(default_factory=list)
    music: MusicTrack | None = None

    def total_duration(self) -> float:
        """Sum of effective clip durations."""
        return sum(c.effective_duration for c in self.clips)

    def validate_sources(self, available_files: list[str]) -> list[str]:
        """Return list of source files referenced but not available."""
        missing = []
        for clip in self.clips:
            if clip.source not in available_files:
                missing.append(clip.source)
        if self.music and self.music.source and self.music.source not in available_files:
            missing.append(self.music.source)
        return missing
