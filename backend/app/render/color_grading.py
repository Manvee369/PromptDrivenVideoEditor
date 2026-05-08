"""Color grading presets implemented as FFmpeg filter chains.

We deliberately avoid `lut3d` + .cube files — that requires shipping LUT
binaries alongside the codebase. Instead each preset is built from
composable filters (`eq`, `colorbalance`, `colorchannelmixer`, `curves`,
`hue`, `vignette`) which gives equivalent looks with zero asset weight.
"""

from __future__ import annotations


# Map preset name → comma-separated FFmpeg filter chain. These plug straight
# into the per-clip video chain in ffmpeg_builder.
COLOR_GRADE_PRESETS: dict[str, str] = {
    # No grade — explicit neutral so callers can opt out unconditionally
    "none": "",

    # Cinematic teal-orange: shadows toward teal, highlights toward orange,
    # slightly desaturated overall, mild contrast bump.
    "cinematic": (
        "colorbalance=rs=-0.10:gs=-0.05:bs=0.10"     # cool shadows
        ":rh=0.10:gh=0.03:bh=-0.10"                  # warm highlights
        ",eq=contrast=1.08:saturation=0.95:gamma=0.97"
    ),

    # Warm summer look — red/yellow lift, mild glow.
    "warm": (
        "colorbalance=rh=0.12:gh=0.06:bh=-0.08"
        ",eq=saturation=1.10:gamma=1.02"
    ),

    # Cool / blue-shifted — clinical, modern, podcast-ish.
    "cool": (
        "colorbalance=rs=-0.08:bs=0.10:rh=-0.05:bh=0.08"
        ",eq=saturation=0.95:contrast=1.05"
    ),

    # Teal & orange (more aggressive than cinematic; trailer look)
    "teal_orange": (
        "colorbalance=rs=-0.20:gs=-0.05:bs=0.20"
        ":rh=0.20:gh=0.05:bh=-0.20"
        ",eq=contrast=1.12:saturation=0.92"
    ),

    # Black & white — desaturate via colorchannelmixer for a controlled curve
    "bw": (
        "colorchannelmixer=.30:.40:.30:0:.30:.40:.30:0:.30:.40:.30"
        ",eq=contrast=1.10"
    ),

    # Vintage / faded — washed-out blacks, sepia tilt
    "vintage": (
        "curves=preset=vintage"
        ",eq=saturation=0.85"
    ),

    # High-contrast / dramatic — for sports & action
    "dramatic": (
        "eq=contrast=1.20:saturation=1.15:gamma=0.93"
    ),
}

# Public preset names — the order here drives the UI dropdown.
COLOR_GRADE_PRESET_NAMES: list[str] = [
    "none", "cinematic", "warm", "cool", "teal_orange",
    "bw", "vintage", "dramatic",
]


def filter_for_preset(name: str | None) -> str:
    """Return the FFmpeg filter chain for `name`, or "" for unknown/none."""
    if not name:
        return ""
    return COLOR_GRADE_PRESETS.get(name, "")
