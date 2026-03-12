"""Translates a Timeline DSL into FFmpeg commands."""

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
        filtergraph, out_v, out_a = self._build_filtergraph(source_index)

        # Check for subtitle file
        ass_path = self.storage.render_path("captions.ass")
        if ass_path.exists():
            # Escape Windows path backslashes and colons for ASS filter
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

    def _build_filtergraph(self, source_index: dict[str, int]) -> tuple[str, str, str]:
        """
        Build a complex filtergraph that trims, scales, and concatenates clips.

        Returns: (filtergraph_string, video_output_label, audio_output_label)
        """
        filters = []
        concat_inputs = []
        w, h = self.fmt.width, self.fmt.height

        for i, clip in enumerate(self.timeline.clips):
            idx = source_index[clip.source]
            v_label = f"v{i}"
            a_label = f"a{i}"

            # Video: trim -> setpts -> optional speed -> scale -> pad
            v_chain = (
                f"[{idx}:v]trim={clip.start}:{clip.end},setpts=PTS-STARTPTS"
            )

            if clip.speed != 1.0:
                v_chain += f",setpts=PTS/{clip.speed}"

            # Apply custom filters
            for filt in clip.filters:
                v_chain += f",{filt}"

            v_chain += (
                f",scale={w}:{h}:force_original_aspect_ratio=decrease"
                f",pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
                f",setsar=1"
                f"[{v_label}]"
            )
            filters.append(v_chain)

            # Audio: atrim -> asetpts -> optional tempo
            a_chain = (
                f"[{idx}:a]atrim={clip.start}:{clip.end},asetpts=PTS-STARTPTS"
            )

            if clip.volume != 1.0:
                a_chain += f",volume={clip.volume}"

            if clip.speed != 1.0:
                a_chain += f",atempo={clip.speed}"

            a_chain += f"[{a_label}]"
            filters.append(a_chain)

            concat_inputs.append(f"[{v_label}][{a_label}]")

        # Concatenate all clips
        n = len(self.timeline.clips)
        concat = "".join(concat_inputs) + f"concat=n={n}:v=1:a=1[outv][outa]"
        filters.append(concat)

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

        # Music source might be an additional input
        if music.source not in source_index:
            # We'd need to add it as a separate input — for now skip
            log.warning("Music source %s not in inputs, skipping", music.source)
            return "outa"

        idx = source_index[music.source]
        total_dur = self.timeline.total_duration()

        # Trim music to total duration, apply volume and fades
        music_chain = f"[{idx}:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS"
        music_chain += f",volume={music.volume}"
        if music.fade_in > 0:
            music_chain += f",afade=t=in:d={music.fade_in}"
        if music.fade_out > 0:
            music_chain += f",afade=t=out:st={max(0, total_dur - music.fade_out)}:d={music.fade_out}"
        music_chain += "[music]"
        filters.append(music_chain)

        # Mix speech audio with music
        filters.append("[outa][music]amix=inputs=2:duration=first[mixed]")
        return "mixed"
