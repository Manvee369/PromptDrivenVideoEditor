"""Job pipeline orchestrator — runs all stages in sequence."""

from app.agents.captions import generate_ass_file, generate_captions
from app.agents.content_classifier import classify_content
from app.agents.editing import build_timeline
from app.agents.explanation import generate_explanation
from app.agents.highlight import select_highlights
from app.agents.music import analyze_music
from app.agents.planner import plan_edit
from app.agents.story import compose_story
from app.agents.strategy_router import get_strategy
from app.agents.thumbnail import generate_thumbnail
from app.core.config import settings
from app.core.logger import get_logger
from app.db.jobs_db import JobStatus, jobs_db
from app.intelligence.audio_features import compute_audio_energy, detect_silence
from app.intelligence.diarization import diarize
from app.intelligence.faces import detect_faces
from app.intelligence.motion import detect_motion
from app.intelligence.shots import detect_shots
from app.intelligence.transcribe import transcribe_media
from app.jobs.preprocess import preprocess_media
from app.render.run_render import render_timeline
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)


def run_pipeline(job_id: str, prompt: str) -> str:
    """
    Execute the full pipeline synchronously.

    Stages:
        1. Preprocessing  — extract audio, create proxies
        2. Intelligence    — transcribe, silence, audio energy, shots, motion, music
        3. Planning        — parse prompt into structured plan
        4. Agents          — highlights, story, editing, captions
        5. Rendering       — convert Timeline to final video via FFmpeg

    Returns path to final output file.
    """
    storage = StorageManager(job_id)

    try:
        # --- Stage 1: Preprocessing ---
        _update(job_id, JobStatus.PREPROCESSING, 0.05)
        log.info("[%s] Stage 1: Preprocessing", job_id)
        manifest = preprocess_media(storage)

        # --- Stage 2: Intelligence ---
        _update(job_id, JobStatus.INTELLIGENCE, 0.15)
        log.info("[%s] Stage 2: Intelligence — transcription", job_id)
        transcript = transcribe_media(storage)

        # Speaker diarization (depends on transcript)
        diarization = None
        if settings.diarization_enabled:
            _update(job_id, JobStatus.INTELLIGENCE, 0.20)
            log.info("[%s] Stage 2: Intelligence — speaker diarization", job_id)
            try:
                diarization = diarize(storage, max_speakers=settings.diarization_max_speakers)
            except Exception as e:
                log.warning("[%s] Diarization failed (non-fatal): %s", job_id, e)

        _update(job_id, JobStatus.INTELLIGENCE, 0.25)
        log.info("[%s] Stage 2: Intelligence — silence detection", job_id)
        silence = detect_silence(storage)
        audio_energy = compute_audio_energy(storage)

        _update(job_id, JobStatus.INTELLIGENCE, 0.35)
        log.info("[%s] Stage 2: Intelligence — shot detection", job_id)
        shots = detect_shots(storage)

        _update(job_id, JobStatus.INTELLIGENCE, 0.40)
        log.info("[%s] Stage 2: Intelligence — motion detection", job_id)
        motion = detect_motion(storage)

        _update(job_id, JobStatus.INTELLIGENCE, 0.45)
        log.info("[%s] Stage 2: Intelligence — face detection", job_id)
        faces = detect_faces(storage)

        # Music analysis (only if music files uploaded)
        music_analysis = analyze_music(storage)

        # Visual scoring with SigLIP (if enabled)
        visual_scores = None
        if settings.visual_scoring_enabled:
            _update(job_id, JobStatus.INTELLIGENCE, 0.48)
            log.info("[%s] Stage 2: Intelligence — visual scoring (SigLIP)", job_id)
            try:
                from app.intelligence.visual_scoring import compute_visual_scores
                visual_scores = compute_visual_scores(prompt, storage, shots)
            except Exception as e:
                log.warning("[%s] Visual scoring failed (non-fatal): %s", job_id, e)

        # --- Stage 3: Classification + Planning ---
        _update(job_id, JobStatus.PLANNING, 0.50)
        log.info("[%s] Stage 3: Content classification", job_id)
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

        # Classify content type and user intent
        classification = classify_content(prompt, signals, storage)
        signals["classification"] = classification

        # Build strategy from classification
        strategy = get_strategy(classification, prompt)
        signals["strategy"] = strategy

        log.info("[%s] Stage 3: Planning (type=%s, intent=%s)",
                 job_id, classification["video_type"], classification["user_intent"])
        plan = plan_edit(prompt, signals, storage)

        # Merge strategy operations into plan if LLM didn't produce them
        plan_ops = set(plan.get("operations", []))
        strategy_ops = set(strategy.get("operations", []))
        merged_ops = sorted(plan_ops | strategy_ops)
        plan["operations"] = merged_ops

        # Inject strategy into plan for downstream agents
        plan["strategy"] = strategy

        # Override plan energy with strategy energy if the strategy is confident
        if classification.get("video_type_confidence", 0) > 0.4:
            plan["style"]["energy"] = strategy["energy"]

        # Override highlight weights with strategy weights
        if strategy.get("highlight_weights"):
            plan["priorities"] = strategy["highlight_weights"]

        # --- Stage 4: Agents ---
        operations = plan["operations"]

        # Highlight selection (if requested)
        highlights = None
        if "highlight_select" in operations:
            _update(job_id, JobStatus.PLANNING, 0.55)
            log.info("[%s] Stage 4: Selecting highlights", job_id)
            highlights = select_highlights(plan, signals, storage)
            signals["highlights"] = highlights

        # Story composition (if requested and narrative structure allows)
        story = None
        story_structure = strategy.get("story_structure", "medium")
        if "story_compose" in operations and highlights and story_structure != "chronological":
            _update(job_id, JobStatus.PLANNING, 0.60)
            log.info("[%s] Stage 4: Composing story (structure=%s)", job_id, story_structure)
            story = compose_story(plan, highlights, storage)
            signals["story"] = story

        # Build timeline
        log.info("[%s] Stage 4: Building timeline", job_id)
        timeline = build_timeline(plan, signals, storage)

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

            generate_ass_file(
                timeline.captions,
                storage.render_path("captions.ass"),
                width=timeline.format.width,
                height=timeline.format.height,
                style_name=style_name,
                animated=animated,
            )

        # Save the timeline DSL
        storage.save_dsl(timeline.model_dump())
        _update(job_id, JobStatus.RENDERING, 0.70)

        # --- Stage 5: Rendering ---
        log.info("[%s] Stage 5: Rendering", job_id)
        output_path = render_timeline(storage)

        # --- Stage 6: Post-processing (thumbnail + explanation) ---
        _update(job_id, JobStatus.RENDERING, 0.90)
        log.info("[%s] Stage 6: Generating thumbnail", job_id)
        try:
            generate_thumbnail(plan, signals, storage)
        except Exception as e:
            log.warning("[%s] Thumbnail generation failed (non-fatal): %s", job_id, e)

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


def _update(job_id: str, status: JobStatus, progress: float = None, **kwargs):
    """Update job status in the database."""
    jobs_db.update_status(job_id, status, progress=progress, **kwargs)
