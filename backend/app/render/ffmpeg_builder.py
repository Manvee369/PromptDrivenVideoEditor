"""Translates a Timeline DSL into FFmpeg commands.

Supports transitions (crossfade, fade, flash, zoom, whip), zoom effects,
music mixing, voiceover mixing, color grading, and EBU R128 loudness
normalization.
"""

from pathlib import Path

from app.core.config import settings
from app.core.logger import get_logger
from app.dsl.schema import Timeline
from app.render.color_grading import filter_for_preset
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)

# Map our transition_in names → FFmpeg `xfade` `transition=` value.
# https://ffmpeg.org/ffmpeg-filters.html#xfade
XFADE_TRANSITION_TYPES: dict[str, str] = {
    "crossfade": "fade",         # plain alpha blend
    "zoom": "zoomin",            # outgoing clip zooms in while incoming reveals
    "whip": "slideleft",         # hard slide — reads as whip-pan with motion blur
}


def _crop_expr(box: dict) -> str:
    """Build an FFmpeg `crop=` expression from a relative crop_box dict.

    Box values are in [0, 1] of the source frame. Using FFmpeg expressions
    referencing iw/ih lets us emit the same filter regardless of source
    resolution — the editing agent doesn't need to know pixel dims.
    """
    w = float(box.get("w", 1.0))
    h = float(box.get("h", 1.0))
    x = float(box.get("x", 0.0))
    y = float(box.get("y", 0.0))
    # Round to keep filter string compact and stable for golden tests.
    return (
        f"crop=iw*{round(w, 4)}:ih*{round(h, 4)}"
        f":iw*{round(x, 4)}:ih*{round(y, 4)}"
    )


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

        # Plan the FFmpeg inputs. Video clips deduplicate by source filename
        # (re-using the same `-i` for multiple clip ranges). Image clips each
        # need their own `-i` because the `-loop 1 -t <dur>` pre-args vary
        # per clip. Music and voiceover sources are appended at the tail.
        clip_input_idx, input_specs, audio_extras_idx = self._enumerate_inputs()

        cmd = [settings.ffmpeg_path]
        for source, pre_args in input_specs:
            cmd.extend(pre_args)
            raw_path = self.storage.stage_dir("raw") / source
            cmd.extend(["-i", str(raw_path)])

        # Use the xfade-style filtergraph for any transition that's a
        # cross-clip blend. crossfade/zoom/whip all use FFmpeg's `xfade`
        # filter — they only differ in the `transition=` parameter we pass.
        has_blend_transition = any(
            c.transition_in in XFADE_TRANSITION_TYPES
            for c in self.timeline.clips[1:]
        )

        if has_blend_transition:
            filtergraph, out_v, out_a = self._build_filtergraph_with_xfade(
                clip_input_idx, audio_extras_idx,
            )
        else:
            filtergraph, out_v, out_a = self._build_filtergraph(
                clip_input_idx, audio_extras_idx,
            )

        # Check for subtitle file
        ass_path = self.storage.render_path("captions.ass")
        if ass_path.exists():
            ass_escaped = str(ass_path).replace("\\", "/").replace(":", "\\:")
            filtergraph += f";[{out_v}]ass='{ass_escaped}'[subbed]"
            out_v = "subbed"

        # EBU R128 loudness normalization on the final mix. Single-pass
        # `loudnorm` is good enough for our purposes — two-pass would require
        # a separate analysis run and isn't worth the latency for short clips.
        if settings.loudnorm_target_lufs != 0:
            i = settings.loudnorm_target_lufs
            lra = settings.loudnorm_target_lra
            tp = settings.loudnorm_target_tp
            filtergraph += (
                f";[{out_a}]loudnorm=I={i}:LRA={lra}:TP={tp}[normalized]"
            )
            out_a = "normalized"

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

    def _enumerate_inputs(
        self,
    ) -> tuple[list[int], list[tuple[str, list[str]]], dict[str, int]]:
        """Plan the FFmpeg `-i` inputs for the timeline.

        Returns:
            clip_input_idx: per-clip input index (parallel to self.timeline.clips)
            input_specs: list of (source_filename, pre_args) tuples in input order
            audio_extras_idx: input index for music + voiceover, keyed by name
        """
        input_specs: list[tuple[str, list[str]]] = []
        clip_input_idx: list[int] = []
        video_seen: dict[str, int] = {}
        audio_extras_idx: dict[str, int] = {}

        for clip in self.timeline.clips:
            if clip.clip_type == "image":
                # Each image clip is its own input — duration is per-clip.
                duration = clip.effective_duration
                pre_args = [
                    "-loop", "1",
                    "-framerate", str(self.fmt.fps),
                    "-t", f"{duration:.6f}",
                ]
                input_specs.append((clip.source, pre_args))
                clip_input_idx.append(len(input_specs) - 1)
            else:
                if clip.source not in video_seen:
                    input_specs.append((clip.source, []))
                    video_seen[clip.source] = len(input_specs) - 1
                clip_input_idx.append(video_seen[clip.source])

        # Music / voiceover always come after clip inputs so per-clip indices
        # in the existing tests don't shift around.
        if self.timeline.music and self.timeline.music.source:
            name = self.timeline.music.source
            if name not in video_seen and name not in audio_extras_idx:
                input_specs.append((name, []))
                audio_extras_idx[name] = len(input_specs) - 1
            elif name in video_seen:
                # If a clip already used this filename as its source (rare),
                # the same input index is reused for music.
                audio_extras_idx[name] = video_seen[name]

        if self.timeline.voiceover and self.timeline.voiceover.source:
            name = self.timeline.voiceover.source
            if name not in video_seen and name not in audio_extras_idx:
                input_specs.append((name, []))
                audio_extras_idx[name] = len(input_specs) - 1
            elif name in video_seen:
                audio_extras_idx[name] = video_seen[name]

        return clip_input_idx, input_specs, audio_extras_idx

    def _build_clip_chains(
        self, clip_input_idx: list[int],
    ) -> tuple[list[str], list[str], list[str]]:
        """Build per-clip video and audio filter chains.
        Returns: (filters, video_labels, audio_labels)"""
        filters = []
        v_labels = []
        a_labels = []
        w, h = self.fmt.width, self.fmt.height

        for i, clip in enumerate(self.timeline.clips):
            idx = clip_input_idx[i]
            v_label = f"v{i}"
            a_label = f"a{i}"

            if clip.clip_type == "image":
                # Image clip: input is a still photo looped to clip duration via
                # `-loop 1 -t <dur>` pre-args. We synthesize Ken Burns motion via
                # animated zoompan, plus a silent audio track.
                v_chain = self._build_image_video_chain(i, idx, clip, v_label)
                a_chain = self._build_image_audio_chain(i, clip, a_label)
                filters.append(v_chain)
                filters.append(a_chain)
                v_labels.append(v_label)
                a_labels.append(a_label)
                continue

            # Video chain: trim -> setpts -> speed -> zoom -> filters -> scale -> pad
            v_chain = (
                f"[{idx}:v]trim={clip.start}:{clip.end},setpts=PTS-STARTPTS"
            )

            if clip.speed != 1.0:
                v_chain += f",setpts=PTS/{clip.speed}"

            # Zoom effect (zoompan) — static for video clips
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

            # Color grade (per-clip override falls back to timeline default)
            grade = filter_for_preset(clip.color_grade or self.timeline.color_grade)
            if grade:
                v_chain += f",{grade}"

            # Smart crop (face/motion-centered) — runs before scale+pad so the
            # following stages see an already-aspect-correct frame.
            if clip.crop_box:
                v_chain += f",{_crop_expr(clip.crop_box)}"

            v_chain += (
                f",scale={w}:{h}:force_original_aspect_ratio=decrease"
                f",pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
                f",setsar=1,fps={self.fmt.fps},settb=AVTB"
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

            # Transition-driven fade-in (longer, intentional). Otherwise apply
            # a tiny smoothing fade so hard cuts don't click. acrossfade
            # transitions handle their own smoothing — skip if next clip
            # crossfades into us.
            has_transition_fade_in = clip.transition_in in ("fade", "flash") and i > 0
            smooth = settings.audio_cut_smooth_seconds
            if has_transition_fade_in:
                a_chain += f",afade=t=in:d={clip.transition_duration}"
            elif i > 0 and smooth > 0:
                a_chain += f",afade=t=in:d={smooth}"

            # Symmetric fade-out at clip end, but only if there's room and the
            # next clip isn't doing a blend transition (acrossfade overlaps the audio).
            next_is_crossfade = (
                i + 1 < len(self.timeline.clips)
                and self.timeline.clips[i + 1].transition_in in XFADE_TRANSITION_TYPES
            )
            clip_dur = clip.effective_duration
            if smooth > 0 and not next_is_crossfade and clip_dur > smooth * 2:
                fade_start = round(clip_dur - smooth, 3)
                a_chain += f",afade=t=out:st={fade_start}:d={smooth}"

            a_chain += f"[{a_label}]"
            filters.append(a_chain)

            v_labels.append(v_label)
            a_labels.append(a_label)

        return filters, v_labels, a_labels

    def _build_image_video_chain(
        self, i: int, idx: int, clip, v_label: str,
    ) -> str:
        """Video chain for an image clip — Ken Burns animated zoompan."""
        w, h = self.fmt.width, self.fmt.height
        fps = self.fmt.fps
        duration = clip.effective_duration
        n_frames = max(1, int(round(duration * fps)))

        # Default Ken Burns zoom of 1.15 if the user didn't specify one. The
        # animated step lets zoompan ramp from 1.0 → target_zoom across the clip.
        target_zoom = clip.zoom if clip.zoom > 1.0 else 1.15
        zoom_step = (target_zoom - 1.0) / n_frames

        v_chain = (
            f"[{idx}:v]setpts=PTS-STARTPTS"
            f",zoompan=z='min(zoom+{zoom_step:.6f},{target_zoom})'"
            f":d={n_frames}"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":s={w}x{h}:fps={fps}"
        )

        for filt in clip.filters:
            v_chain += f",{filt}"

        # Color grade (per-clip override falls back to timeline default)
        grade = filter_for_preset(clip.color_grade or self.timeline.color_grade)
        if grade:
            v_chain += f",{grade}"

        v_chain += (
            f",scale={w}:{h}:force_original_aspect_ratio=decrease"
            f",pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
            f",setsar=1,fps={fps},settb=AVTB"
        )

        if clip.transition_in == "fade" and i > 0:
            v_chain += f",fade=t=in:d={clip.transition_duration}"
        elif clip.transition_in == "flash" and i > 0:
            v_chain += f",fade=t=in:d={clip.transition_duration}:color=white"

        v_chain += f"[{v_label}]"
        return v_chain

    def _build_image_audio_chain(self, i: int, clip, a_label: str) -> str:
        """Audio chain for an image clip — synthesized silence matching duration."""
        duration = clip.effective_duration
        # anullsrc generates a silent stereo track. afade applies if a fade-in
        # transition was requested for visual consistency.
        chain = (
            f"anullsrc=channel_layout=stereo:sample_rate=48000"
            f":duration={duration:.6f}"
        )
        if clip.volume != 1.0:
            chain += f",volume={clip.volume}"
        if clip.transition_in in ("fade", "flash") and i > 0:
            chain += f",afade=t=in:d={clip.transition_duration}"
        chain += f"[{a_label}]"
        return chain

    def _build_filtergraph(
        self,
        clip_input_idx: list[int],
        audio_extras_idx: dict[str, int],
    ) -> tuple[str, str, str]:
        """Build filtergraph with concat (no crossfade transitions)."""
        filters, v_labels, a_labels = self._build_clip_chains(clip_input_idx)

        # Concatenate all clips
        n = len(self.timeline.clips)
        concat_inputs = "".join(f"[{v}][{a}]" for v, a in zip(v_labels, a_labels))
        concat = concat_inputs + f"concat=n={n}:v=1:a=1[outv][outa]"
        filters.append(concat)

        # Mix in background music + voiceover if either is present.
        out_a = "outa"
        if self._has_extra_audio():
            out_a = self._add_music_mix(filters, audio_extras_idx)

        filtergraph = ";".join(filters)
        return filtergraph, "outv", out_a

    def _build_filtergraph_with_xfade(
        self,
        clip_input_idx: list[int],
        audio_extras_idx: dict[str, int],
    ) -> tuple[str, str, str]:
        """Build filtergraph using xfade for crossfade transitions."""
        filters, v_labels, a_labels = self._build_clip_chains(clip_input_idx)

        clips = self.timeline.clips

        # Chain xfade between video streams
        current_v = v_labels[0]
        current_a = a_labels[0]
        accumulated_dur = clips[0].effective_duration

        for i in range(1, len(clips)):
            clip = clips[i]

            if clip.transition_in in XFADE_TRANSITION_TYPES:
                # crossfade / zoom / whip — all share the xfade machinery,
                # only differing in the `transition=` value FFmpeg uses.
                xfade_kind = XFADE_TRANSITION_TYPES[clip.transition_in]
                d = min(clip.transition_duration, accumulated_dur * 0.5, clip.effective_duration * 0.5)
                d = max(d, 0.1)
                offset = round(accumulated_dur - d, 3)

                xf_v = f"xfv{i}"
                xf_a = f"xfa{i}"

                filters.append(
                    f"[{current_v}][{v_labels[i]}]"
                    f"xfade=transition={xfade_kind}:duration={d}:offset={offset}"
                    f"[{xf_v}]"
                )
                # Audio always uses an acrossfade (an alpha-blend equivalent
                # for audio), regardless of the visual transition style.
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

        # Mix in background music + voiceover if either is present.
        out_a = "outa"
        if self._has_extra_audio():
            out_a = self._add_music_mix(filters, audio_extras_idx)

        filtergraph = ";".join(filters)
        return filtergraph, "outv", out_a

    def _has_extra_audio(self) -> bool:
        """True if music or voiceover would contribute to the output mix."""
        m = self.timeline.music
        v = self.timeline.voiceover
        return bool((m and m.source) or (v and v.source))

    def _add_music_mix(self, filters: list[str], audio_extras_idx: dict[str, int]) -> str:
        """Mix background music + voiceover into the main audio.

        Whichever of music/voiceover are configured (and have valid sources)
        get their own chains and are amix'd with the main audio. Returns the
        final audio label name. Kept named `_add_music_mix` for backward
        compatibility — the function now handles both extra audio tracks.
        """
        music_label = self._build_music_chain(filters, audio_extras_idx)
        voice_label = self._build_voiceover_chain(filters, audio_extras_idx)

        extras = [lbl for lbl in (music_label, voice_label) if lbl is not None]
        if not extras:
            return "outa"

        inputs = "[outa]" + "".join(f"[{lbl}]" for lbl in extras)
        n = 1 + len(extras)
        filters.append(f"{inputs}amix=inputs={n}:duration=first[mixed]")
        return "mixed"

    def _build_music_chain(
        self, filters: list[str], audio_extras_idx: dict[str, int],
    ) -> str | None:
        music = self.timeline.music
        if not music or not music.source:
            return None
        if music.source not in audio_extras_idx:
            log.warning("Music source %s not in inputs, skipping", music.source)
            return None

        idx = audio_extras_idx[music.source]
        total_dur = self.timeline.total_duration()

        chain = f"[{idx}:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS"
        chain += f",volume={music.volume}"
        if music.fade_in > 0:
            chain += f",afade=t=in:d={music.fade_in}"
        if music.fade_out > 0:
            chain += f",afade=t=out:st={max(0, total_dur - music.fade_out)}:d={music.fade_out}"
        chain += "[music]"
        filters.append(chain)
        return "music"

    def _build_voiceover_chain(
        self, filters: list[str], audio_extras_idx: dict[str, int],
    ) -> str | None:
        voice = self.timeline.voiceover
        if not voice or not voice.source:
            return None
        if voice.source not in audio_extras_idx:
            log.warning("Voiceover source %s not in inputs, skipping", voice.source)
            return None

        idx = audio_extras_idx[voice.source]
        total_dur = self.timeline.total_duration()

        chain = f"[{idx}:a]"
        if voice.offset > 0:
            # adelay accepts per-channel delays in ms; we apply the same
            # delay to both stereo channels.
            delay_ms = int(voice.offset * 1000)
            chain += f"adelay={delay_ms}|{delay_ms},"
        chain += f"atrim=0:{total_dur},asetpts=PTS-STARTPTS"
        chain += f",volume={voice.volume}"
        if voice.fade_in > 0:
            chain += f",afade=t=in:d={voice.fade_in}"
        if voice.fade_out > 0:
            chain += f",afade=t=out:st={max(0, total_dur - voice.fade_out)}:d={voice.fade_out}"
        chain += "[voice]"
        filters.append(chain)
        return "voice"
