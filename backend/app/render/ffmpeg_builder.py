"""Translates a Timeline DSL into FFmpeg commands.

Supports transitions (crossfade, fade, flash), zoom effects, and music mixing.
"""

from pathlib import Path

from app.core.config import settings
from app.core.logger import get_logger
from app.dsl.schema import Timeline
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


class FFmpegCommandBuilder:
    """Build FFmpeg commands from a Timeline DSL."""

    def __init__(self, timeline: Timeline, storage: StorageManager):
        self.timeline = timeline
        self.storage = storage
        self.fmt = timeline.format

    def build(self) -> list[str]:
        """Build the full FFmpeg command as a list of args."""
        if not self.timeline.clips:
            raise ValueError("Timeline has no clips")

        # Group clips by source file to minimize inputs
        sources = list(dict.fromkeys(c.source for c in self.timeline.clips))
        source_index = {name: i for i, name in enumerate(sources)}

        cmd = [settings.ffmpeg_path]

        # Input files
        for source in sources:
            raw_path = self.storage.stage_dir("raw") / source
            cmd.extend(["-i", str(raw_path)])

        # Build complex filtergraph
        has_crossfade = any(
            c.transition_in == "crossfade" for c in self.timeline.clips[1:]
        )

        if has_crossfade:
            filtergraph, out_v, out_a = self._build_filtergraph_with_xfade(source_index)
        else:
            filtergraph, out_v, out_a = self._build_filtergraph(source_index)

        # Check for subtitle file
        ass_path = self.storage.render_path("captions.ass")
        if ass_path.exists():
            ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
            filtergraph += f";[{out_v}]ass='{ass_escaped}'[subbed]"
            out_v = "subbed"

        cmd.extend(["-filter_complex", filtergraph])
        cmd.extend(["-map", f"[{out_v}]"])
        cmd.extend(["-map", f"[{out_a}]"])

        # Output encoding
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            "-y",
        ])

        # Output path
        output = self.storage.output_path("final.mp4")
        cmd.append(str(output))

        return cmd

    def _build_clip_chains(self, source_index: dict[str, int]) -> tuple[list[str], list[str], list[str]]:
        """Build per-clip video and audio filter chains.
        Returns: (filters, video_labels, audio_labels)"""
        filters = []
        v_labels = []
        a_labels = []
        w, h = self.fmt.width, self.fmt.height

        for i, clip in enumerate(self.timeline.clips):
            idx = source_index[clip.source]
            v_label = f"v{i}"
            a_label = f"a{i}"

            # Video chain: trim -> setpts -> speed -> zoom -> filters -> scale -> pad
            v_chain = (
                f"[{idx}:v]trim={clip.start}:{clip.end},setpts=PTS-STARTPTS"
            )

            if clip.speed != 1.0:
                v_chain += f",setpts=PTS/{clip.speed}"

            # Zoom effect (zoompan)
            if clip.zoom > 1.0:
                z = clip.zoom
                v_chain += (
                    f",zoompan=z={z}:d=1"
                    f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                    f":s={w}x{h}:fps={self.fmt.fps}"
                )

            # Custom filters
            for filt in clip.filters:
                v_chain += f",{filt}"

            v_chain += (
                f",scale={w}:{h}:force_original_aspect_ratio=decrease"
                f",pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
                f",setsar=1"
            )

            # Per-clip fade/flash transitions (non-crossfade)
            if clip.transition_in == "fade" and i > 0:
                d = clip.transition_duration
                v_chain += f",fade=t=in:d={d}"
            elif clip.transition_in == "flash" and i > 0:
                d = clip.transition_duration
                v_chain += f",fade=t=in:d={d}:color=white"

            v_chain += f"[{v_label}]"
            filters.append(v_chain)

            # Audio chain: atrim -> asetpts -> volume -> tempo -> fade
            a_chain = (
                f"[{idx}:a]atrim={clip.start}:{clip.end},asetpts=PTS-STARTPTS"
            )

            if clip.volume != 1.0:
                a_chain += f",volume={clip.volume}"

            if clip.speed != 1.0:
                a_chain += f",atempo={clip.speed}"

            if clip.transition_in in ("fade", "flash") and i > 0:
                d = clip.transition_duration
                a_chain += f",afade=t=in:d={d}"

            a_chain += f"[{a_label}]"
            filters.append(a_chain)

            v_labels.append(v_label)
            a_labels.append(a_label)

        return filters, v_labels, a_labels

    def _build_filtergraph(self, source_index: dict[str, int]) -> tuple[str, str, str]:
        """Build filtergraph with concat (no crossfade transitions)."""
        filters, v_labels, a_labels = self._build_clip_chains(source_index)

        # Concatenate all clips
        n = len(self.timeline.clips)
        concat_inputs = "".join(f"[{v}][{a}]" for v, a in zip(v_labels, a_labels))
        concat = concat_inputs + f"concat=n={n}:v=1:a=1[outv][outa]"
        filters.append(concat)

        # Mix in background music if present
        out_a = "outa"
        if self.timeline.music and self.timeline.music.source:
            out_a = self._add_music_mix(filters, source_index)

        filtergraph = ";".join(filters)
        return filtergraph, "outv", out_a

    def _build_filtergraph_with_xfade(self, source_index: dict[str, int]) -> tuple[str, str, str]:
        """Build filtergraph using xfade for crossfade transitions."""
        filters, v_labels, a_labels = self._build_clip_chains(source_index)

        clips = self.timeline.clips

        # Chain xfade between video streams
        current_v = v_labels[0]
        current_a = a_labels[0]
        accumulated_dur = clips[0].effective_duration

        for i in range(1, len(clips)):
            clip = clips[i]

            if clip.transition_in == "crossfade":
                d = min(clip.transition_duration, accumulated_dur * 0.5, clip.effective_duration * 0.5)
                d = max(d, 0.1)
                offset = round(accumulated_dur - d, 3)

                xf_v = f"xfv{i}"
                xf_a = f"xfa{i}"

                filters.append(
                    f"[{current_v}][{v_labels[i]}]xfade=transition=fade:duration={d}:offset={offset}[{xf_v}]"
                )
                filters.append(
                    f"[{current_a}][{a_labels[i]}]acrossfade=d={d}[{xf_a}]"
                )

                current_v = xf_v
                current_a = xf_a
                accumulated_dur = offset + clip.effective_duration
            else:
                # No crossfade — concat this pair
                pair_v = f"pv{i}"
                pair_a = f"pa{i}"
                filters.append(
                    f"[{current_v}][{current_a}][{v_labels[i]}][{a_labels[i]}]"
                    f"concat=n=2:v=1:a=1[{pair_v}][{pair_a}]"
                )
                current_v = pair_v
                current_a = pair_a
                accumulated_dur += clip.effective_duration

        # Rename final labels
        filters.append(f"[{current_v}]null[outv]")
        filters.append(f"[{current_a}]anull[outa]")

        # Mix in background music if present
        out_a = "outa"
        if self.timeline.music and self.timeline.music.source:
            out_a = self._add_music_mix(filters, source_index)

        filtergraph = ";".join(filters)
        return filtergraph, "outv", out_a

    def _add_music_mix(self, filters: list[str], source_index: dict[str, int]) -> str:
        """Add background music mixing to the filtergraph. Returns output audio label."""
        music = self.timeline.music
        if not music or not music.source:
            return "outa"

        if music.source not in source_index:
            log.warning("Music source %s not in inputs, skipping", music.source)
            return "outa"

        idx = source_index[music.source]
        total_dur = self.timeline.total_duration()

        music_chain = f"[{idx}:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS"
        music_chain += f",volume={music.volume}"
        if music.fade_in > 0:
            music_chain += f",afade=t=in:d={music.fade_in}"
        if music.fade_out > 0:
            music_chain += f",afade=t=out:st={max(0, total_dur - music.fade_out)}:d={music.fade_out}"
        music_chain += "[music]"
        filters.append(music_chain)

        filters.append("[outa][music]amix=inputs=2:duration=first[mixed]")
        return "mixed"
