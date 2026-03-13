"""Job pipeline orchestrator — runs all stages in sequence."""

from app.agents.captions import generate_ass_file, generate_captions
from app.agents.editing import build_timeline
from app.agents.explanation import generate_explanation
from app.agents.highlight import select_highlights
from app.agents.music import analyze_music
from app.agents.planner import plan_edit
from app.agents.story import compose_story
from app.agents.thumbnail import generate_thumbnail
from app.core.logger import get_logger
from app.db.jobs_db import JobStatus, jobs_db
from app.intelligence.audio_features import compute_audio_energy, detect_silence
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

        # --- Stage 3: Planning ---
        _update(job_id, JobStatus.PLANNING, 0.50)
        log.info("[%s] Stage 3: Planning", job_id)
        signals = {
            "media_manifest": manifest,
            "transcript": transcript,
            "silence": silence,
            "audio_energy": audio_energy,
            "shots": shots,
            "motion": motion,
            "faces": faces,
            "music_analysis": music_analysis,
        }
        plan = plan_edit(prompt, signals, storage)

        # --- Stage 4: Agents ---
        operations = plan.get("operations", [])

        # Highlight selection (if requested)
        highlights = None
        if "highlight_select" in operations:
            _update(job_id, JobStatus.PLANNING, 0.55)
            log.info("[%s] Stage 4: Selecting highlights", job_id)
            highlights = select_highlights(plan, signals, storage)
            signals["highlights"] = highlights

        # Story composition (if requested)
        story = None
        if "story_compose" in operations and highlights:
            _update(job_id, JobStatus.PLANNING, 0.60)
            log.info("[%s] Stage 4: Composing story", job_id)
            story = compose_story(plan, highlights, storage)
            signals["story"] = story

        # Build timeline
        log.info("[%s] Stage 4: Building timeline", job_id)
        timeline = build_timeline(plan, signals, storage)

        # Add captions if requested
        if "add_captions" in operations:
            timeline = generate_captions(timeline, signals, storage)

            # Use animated captions for high-energy or TikTok style
            energy = plan.get("style", {}).get("energy", "medium")
            aspect = plan.get("style", {}).get("aspect", "16:9")
            animated = energy == "high" or aspect == "9:16"
            style_name = "tiktok_bold" if aspect == "9:16" else "default"

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
