"""Job pipeline orchestrator — runs all stages in sequence.

Resumability: every stage writes its artifact to disk under storage/jobs/<id>/,
so subsequent runs can skip already-completed work. Pass force=True to bypass
the cache and recompute everything.
"""

from typing import Any, Callable

from app.agents.captions import generate_ass_file, generate_captions
from app.agents.content_classifier import classify_content
from app.agents.editing import build_timeline
from app.agents.explanation import generate_explanation
from app.agents.highlight import select_highlights
from app.agents.music import analyze_music
from app.agents.planner import _rule_based_plan, plan_edit
from app.agents.story import compose_story
from app.agents.strategy_router import get_strategy
from app.agents.thumbnail import generate_thumbnail
from app.core.config import settings
from app.core.logger import get_logger
from app.db.jobs_db import JobStatus, jobs_db
from app.dsl.schema import Timeline
from app.intelligence.audio_features import compute_audio_energy, detect_silence
from app.intelligence.diarization import diarize
from app.intelligence.faces import detect_faces
from app.intelligence.motion import detect_motion
from app.intelligence.shots import detect_shots
from app.intelligence.transcribe import transcribe_media
from app.jobs.preprocess import preprocess_media
from app.jobs.workflow import is_simple_workflow, required_signals
from app.render.run_render import render_timeline
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


def _cached_signal(
    storage: StorageManager,
    job_id: str,
    name: str,
    compute: Callable[[], Any],
    *,
    force: bool,
) -> Any:
    """Return a signal from disk if present, else compute and let the function
    persist it. Logs cache hit/miss so the operator can see what was reused."""
    if not force and storage.has_json("signals", name):
        log.info("[%s] Stage cache hit: signals/%s", job_id, name)
        return storage.load_signal(name)
    log.info("[%s] Stage running: signals/%s", job_id, name)
    return compute()


def _cached_plan(
    storage: StorageManager,
    job_id: str,
    name: str,
    compute: Callable[[], Any],
    *,
    force: bool,
) -> Any:
    if not force and storage.has_json("plans", name):
        log.info("[%s] Stage cache hit: plans/%s", job_id, name)
        return storage.load_plan(name)
    log.info("[%s] Stage running: plans/%s", job_id, name)
    return compute()


def run_pipeline(job_id: str, prompt: str, force: bool = False) -> str:
    """
    Execute the full pipeline synchronously.

    Args:
        job_id: the job identifier (its directory must already exist).
        prompt: natural-language editing instruction.
        force: if True, ignore cached per-stage artifacts and recompute everything.

    Returns path to final output file.
    """
    storage = StorageManager(job_id)

    # User-selected overrides persisted on the JobRecord at creation time.
    job_record = jobs_db.get(job_id)
    caption_style_override = job_record.caption_style if job_record else None
    color_grade_override = job_record.color_grade if job_record else None

    try:
        # --- Stage 1: Preprocessing ---
        _update(job_id, JobStatus.PREPROCESSING, 0.05)
        log.info("[%s] Stage 1: Preprocessing", job_id)
        manifest = _cached_signal(
            storage, job_id, "media_manifest",
            lambda: preprocess_media(storage),
            force=force,
        )

        # --- Workflow gating: cheap rule-based pre-plan from the prompt alone
        # decides which intelligence stages are actually needed. Big perf win
        # for simple prompts ("make it black and white") that don't need SigLIP,
        # diarization, motion, or faces.
        pre_plan = _rule_based_plan(prompt, {"media_manifest": manifest})
        pre_ops = set(pre_plan.get("operations", []))
        needed = required_signals(pre_ops)
        simple = is_simple_workflow(pre_ops)
        log.info(
            "[%s] Workflow: mode=%s ops=%s needed=%s",
            job_id, "simple" if simple else "full", sorted(pre_ops), sorted(needed),
        )

        # --- Stage 2: Intelligence (gated) ---
        _update(job_id, JobStatus.INTELLIGENCE, 0.15)
        transcript: dict = {}
        if "transcript" in needed:
            log.info("[%s] Stage 2: transcription", job_id)
            transcript = _cached_signal(
                storage, job_id, "transcript",
                lambda: transcribe_media(storage), force=force,
            )

        diarization = None
        if "diarization" in needed and settings.diarization_enabled:
            _update(job_id, JobStatus.INTELLIGENCE, 0.20)
            log.info("[%s] Stage 2: speaker diarization", job_id)
            try:
                diarization = _cached_signal(
                    storage, job_id, "diarization",
                    lambda: diarize(storage, max_speakers=settings.diarization_max_speakers),
                    force=force,
                )
            except Exception as e:
                log.warning("[%s] Diarization failed (non-fatal): %s", job_id, e)

        _update(job_id, JobStatus.INTELLIGENCE, 0.25)
        silence: dict = {}
        if "silence" in needed:
            log.info("[%s] Stage 2: silence detection", job_id)
            silence = _cached_signal(
                storage, job_id, "silence",
                lambda: detect_silence(storage), force=force,
            )

        audio_energy: dict = {}
        if "audio_energy" in needed:
            audio_energy = _cached_signal(
                storage, job_id, "audio_energy",
                lambda: compute_audio_energy(storage), force=force,
            )

        shots: dict = {}
        if "shots" in needed:
            _update(job_id, JobStatus.INTELLIGENCE, 0.35)
            log.info("[%s] Stage 2: shot detection", job_id)
            shots = _cached_signal(
                storage, job_id, "shots",
                lambda: detect_shots(storage), force=force,
            )

        motion: dict = {}
        if "motion" in needed:
            _update(job_id, JobStatus.INTELLIGENCE, 0.40)
            log.info("[%s] Stage 2: motion detection", job_id)
            motion = _cached_signal(
                storage, job_id, "motion",
                lambda: detect_motion(storage), force=force,
            )

        faces: dict = {}
        if "faces" in needed:
            _update(job_id, JobStatus.INTELLIGENCE, 0.45)
            log.info("[%s] Stage 2: face detection", job_id)
            faces = _cached_signal(
                storage, job_id, "faces",
                lambda: detect_faces(storage), force=force,
            )

        music_analysis: dict = {}
        if "music_analysis" in needed:
            music_analysis = _cached_signal(
                storage, job_id, "music_analysis",
                lambda: analyze_music(storage), force=force,
            )

        # Visual scoring with SigLIP — the heaviest stage. Skipped entirely
        # unless we're building highlights or a story.
        visual_scores = None
        if "visual_scores" in needed and settings.visual_scoring_enabled:
            _update(job_id, JobStatus.INTELLIGENCE, 0.48)
            log.info("[%s] Stage 2: visual scoring (SigLIP)", job_id)
            try:
                from app.intelligence.visual_scoring import compute_visual_scores
                visual_scores = _cached_signal(
                    storage, job_id, "visual_scores",
                    lambda: compute_visual_scores(prompt, storage, shots),
                    force=force,
                )
            except Exception as e:
                log.warning("[%s] Visual scoring failed (non-fatal): %s", job_id, e)

        # --- Stage 3: Classification + Planning ---
        _update(job_id, JobStatus.PLANNING, 0.50)
        signals = {
            "media_manifest": manifest,
            "transcript": transcript,
            "silence": silence,
            "audio_energy": audio_energy,
            "shots": shots,
            "motion": motion,
            "faces": faces,
            "diarization": diarization,
            "music_analysis": music_analysis,
            "visual_scores": visual_scores,
        }

        if simple:
            # Fast path: skip classification + LLM planner. The rule-based
            # pre-plan is the final plan. Strategy is a minimal stub.
            log.info("[%s] Stage 3: simple workflow — using rule-based plan", job_id)
            plan = pre_plan
            classification = {
                "video_type": "raw_footage",
                "user_intent": "simple_transform",
                "video_type_confidence": 0.0,
                "user_intent_confidence": 1.0,
                "warnings": [],
            }
            strategy = {
                "operations": list(pre_ops),
                "energy": pre_plan["style"]["energy"],
                "caption_config": {"animated": False, "style": "default", "speaker_tags": False},
                "story_structure": "chronological",
                "transition_config": {},
            }
            signals["classification"] = classification
            signals["strategy"] = strategy
            plan["strategy"] = strategy
        else:
            log.info("[%s] Stage 3: content classification", job_id)
            classification = _cached_signal(
                storage, job_id, "classification",
                lambda: classify_content(prompt, signals, storage),
                force=force,
            )
            signals["classification"] = classification

            strategy = get_strategy(classification, prompt)
            signals["strategy"] = strategy

            log.info("[%s] Stage 3: Planning (type=%s, intent=%s)",
                     job_id, classification["video_type"], classification["user_intent"])
            plan = _cached_plan(
                storage, job_id, "plan",
                lambda: plan_edit(prompt, signals, storage),
                force=force,
            )

            # Merge strategy operations into plan if LLM didn't produce them
            plan_ops = set(plan.get("operations", []))
            strategy_ops = set(strategy.get("operations", []))
            merged_ops = sorted(plan_ops | strategy_ops)
            plan["operations"] = merged_ops
            plan["strategy"] = strategy

            if classification.get("video_type_confidence", 0) > 0.4:
                plan["style"]["energy"] = strategy["energy"]

            if strategy.get("highlight_weights"):
                plan["priorities"] = strategy["highlight_weights"]

        # User caption-style override wins over both fast-path default and
        # strategy-router choice. Setting `style` is enough; the captions agent
        # reads strategy["caption_config"]["style"] downstream.
        if caption_style_override:
            strategy.setdefault("caption_config", {})["style"] = caption_style_override
            signals["strategy"] = strategy
            log.info("[%s] Caption style override applied: %s",
                     job_id, caption_style_override)

        # --- Stage 4: Agents ---
        operations = plan["operations"]

        # Highlight selection (if requested)
        highlights = None
        if "highlight_select" in operations:
            _update(job_id, JobStatus.PLANNING, 0.55)
            log.info("[%s] Stage 4: Selecting highlights", job_id)
            highlights = _cached_plan(
                storage, job_id, "highlights",
                lambda: select_highlights(plan, signals, storage),
                force=force,
            )
            signals["highlights"] = highlights

        # Story composition (if requested and narrative structure allows)
        story = None
        story_structure = strategy.get("story_structure", "medium")
        if "story_compose" in operations and highlights and story_structure != "chronological":
            _update(job_id, JobStatus.PLANNING, 0.60)
            log.info("[%s] Stage 4: Composing story (structure=%s)", job_id, story_structure)
            story = _cached_plan(
                storage, job_id, "story",
                lambda: compose_story(plan, highlights, storage),
                force=force,
            )
            signals["story"] = story

        # Build timeline (only if no DSL on disk, or force)
        if force or not storage.has_json("dsl", "timeline"):
            log.info("[%s] Stage 4: Building timeline", job_id)
            timeline = build_timeline(plan, signals, storage)

            # User-selected color grade applies to the whole timeline.
            if color_grade_override:
                timeline.color_grade = color_grade_override
                log.info("[%s] Color grade override: %s",
                         job_id, color_grade_override)

            # Add captions if requested
            caption_config = strategy.get("caption_config", {})
            if "add_captions" in operations:
                timeline = generate_captions(
                    timeline, signals, storage,
                    use_speaker_tags=caption_config.get("speaker_tags", False),
                )

                # Caption style from strategy
                animated = caption_config.get("animated", False)
                style_name = caption_config.get("style", "default")

                # Fallback: high energy or vertical → animated
                aspect = plan.get("style", {}).get("aspect", "16:9")
                if not animated:
                    energy = plan.get("style", {}).get("energy", "medium")
                    animated = energy == "high" or aspect == "9:16"
                if style_name == "default" and aspect == "9:16":
                    style_name = "tiktok_bold"

                # Beat times for karaoke beat-sync emphasis
                music_beats = None
                ma = signals.get("music_analysis") or {}
                if ma.get("beats"):
                    music_beats = ma["beats"]

                generate_ass_file(
                    timeline.captions,
                    storage.render_path("captions.ass"),
                    width=timeline.format.width,
                    height=timeline.format.height,
                    style_name=style_name,
                    animated=animated,
                    beats=music_beats,
                )

            # Save the timeline DSL
            storage.save_dsl(timeline.model_dump())
        else:
            log.info("[%s] Stage 4: cache hit dsl/timeline", job_id)

        _update(job_id, JobStatus.RENDERING, 0.70)

        # --- Stage 5: Rendering ---
        # Final output is what we ultimately serve, so always re-render unless
        # the file exists AND we weren't asked to force.
        output_path = storage.output_path("final.mp4")
        if force or not output_path.exists():
            log.info("[%s] Stage 5: Rendering", job_id)
            output_path = render_timeline(storage)
        else:
            log.info("[%s] Stage 5: cache hit outputs/final.mp4", job_id)

        # --- Stage 6: Post-processing (thumbnail + explanation) ---
        _update(job_id, JobStatus.RENDERING, 0.90)
        thumb_path = storage.output_path("thumbnail.png")
        if force or not thumb_path.exists():
            log.info("[%s] Stage 6: Generating thumbnail", job_id)
            try:
                generate_thumbnail(plan, signals, storage)
            except Exception as e:
                log.warning("[%s] Thumbnail generation failed (non-fatal): %s", job_id, e)

        if force or not storage.has_json("outputs", "explanation"):
            log.info("[%s] Stage 6: Generating explanation", job_id)
            try:
                generate_explanation(plan, signals, storage)
            except Exception as e:
                log.warning("[%s] Explanation generation failed (non-fatal): %s", job_id, e)

        # Done
        _update(job_id, JobStatus.COMPLETED, 1.0, output_file=str(output_path))
        log.info("[%s] Pipeline complete: %s", job_id, output_path)
        return str(output_path)

    except Exception as e:
        log.error("[%s] Pipeline failed: %s", job_id, e, exc_info=True)
        _update(job_id, JobStatus.FAILED, error=str(e))
        raise


def rerender_only(job_id: str) -> str:
    """Re-run only the render stage from the existing DSL on disk.

    Used after the user edits the timeline (Phase 3 UI) — skips all the
    expensive LLM/Whisper/SigLIP work and just regenerates final.mp4 from
    whatever is in dsl/timeline.json. Captions ASS file is regenerated from
    the timeline's caption list so DSL edits to captions take effect.
    """
    storage = StorageManager(job_id)
    if not storage.has_json("dsl", "timeline"):
        raise FileNotFoundError(f"Job {job_id} has no DSL to render")

    try:
        _update(job_id, JobStatus.RENDERING, 0.5)

        # Regenerate the captions ASS file from the (possibly edited) DSL.
        timeline = Timeline(**storage.load_dsl())
        if timeline.captions:
            # Use sensible defaults; the strategy isn't available without re-planning.
            aspect = timeline.format.aspect
            generate_ass_file(
                timeline.captions,
                storage.render_path("captions.ass"),
                width=timeline.format.width,
                height=timeline.format.height,
                style_name="tiktok_bold" if aspect == "9:16" else "default",
                animated=aspect == "9:16",
            )

        log.info("[%s] Rerender starting", job_id)
        output_path = render_timeline(storage)
        _update(job_id, JobStatus.COMPLETED, 1.0, output_file=str(output_path))
        log.info("[%s] Rerender complete: %s", job_id, output_path)
        return str(output_path)

    except Exception as e:
        log.error("[%s] Rerender failed: %s", job_id, e, exc_info=True)
        _update(job_id, JobStatus.FAILED, error=str(e))
        raise


def _update(job_id: str, status: JobStatus, progress: float = None, **kwargs):
    """Update job status in the database."""
    jobs_db.update_status(job_id, status, progress=progress, **kwargs)
