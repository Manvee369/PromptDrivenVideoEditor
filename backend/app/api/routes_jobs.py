"""Job API routes — create, poll status, download output, analyze."""

import os
import uuid
from typing import List

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.logger import get_logger
from app.db.jobs_db import jobs_db
from app.jobs.pipeline import run_pipeline
from app.storage.storage_manager import StorageManager

log = get_logger(__name__)
router = APIRouter()


@router.post("/", summary="Create Job")
async def create_job(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    files: List[UploadFile] = None,
):
    """Upload files and start the editing pipeline."""
    job_id = str(uuid.uuid4())
    storage = StorageManager(job_id)
    storage.ensure_dirs()

    if not files:
        from fastapi import HTTPException as _H
        raise _H(status_code=400, detail="At least one file is required")

    # Save uploaded files
    for file in files:
        path = storage.stage_dir("raw") / file.filename
        with open(path, "wb") as f:
            content = await file.read()
            f.write(content)
        log.info("Uploaded %s for job %s", file.filename, job_id)

    # Register job
    jobs_db.create(job_id, prompt)

    # Launch pipeline in background
    background_tasks.add_task(run_pipeline, job_id, prompt)

    return {"job_id": job_id, "status": "created"}


@router.get("/")
async def list_jobs():
    """List all jobs with their status."""
    return [job.model_dump() for job in jobs_db.list_jobs()]


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Get job status and details."""
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()


@router.get("/{job_id}/timeline")
async def get_timeline(job_id: str):
    """Return the Timeline DSL JSON for this job."""
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    storage = StorageManager(job_id)
    if not storage.has_json("dsl", "timeline"):
        raise HTTPException(status_code=404, detail="Timeline not yet generated")

    return storage.load_dsl()


@router.get("/{job_id}/download")
async def download_output(job_id: str):
    """Download the final rendered video."""
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=400, detail=f"Job not complete (status: {job.status})")

    output_path = StorageManager(job_id).output_path("final.mp4")
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    return FileResponse(
        str(output_path),
        media_type="video/mp4",
        filename=f"edited_{job_id[:8]}.mp4",
    )


@router.get("/{job_id}/explanation")
async def get_explanation(job_id: str):
    """Return the explanation of editing decisions for this job."""
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    storage = StorageManager(job_id)
    if not storage.has_json("outputs", "explanation"):
        raise HTTPException(status_code=404, detail="Explanation not yet generated")

    return storage.load_json("outputs", "explanation")


@router.get("/{job_id}/thumbnail")
async def get_thumbnail(job_id: str):
    """Download the generated thumbnail for this job."""
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    output_path = StorageManager(job_id).output_path("thumbnail.png")
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not yet generated")

    return FileResponse(
        str(output_path),
        media_type="image/png",
        filename=f"thumbnail_{job_id[:8]}.png",
    )


@router.post("/analyze", summary="Analyze video before processing")
async def analyze_content(
    prompt: str = Form(...),
    files: List[UploadFile] = None,
):
    """
    Quick content analysis: classifies video type and user intent,
    returns warnings if there's a mismatch.

    This runs preprocessing + basic intelligence (fast) to classify
    the content before committing to the full pipeline.

    Returns:
    {
        "analysis_id": "temp-uuid",
        "video_type": "talking_head",
        "video_type_confidence": 0.82,
        "user_intent": "highlight_reel",
        "user_intent_confidence": 0.75,
        "warnings": ["This looks like a talking head video..."],
        "strategy_summary": {...}
    }
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")

    # Create a temporary job directory for analysis
    analysis_id = f"analyze-{uuid.uuid4()}"
    storage = StorageManager(analysis_id)
    storage.ensure_dirs()

    try:
        # Save uploaded files
        for file in files:
            path = storage.stage_dir("raw") / file.filename
            with open(path, "wb") as f:
                content = await file.read()
                f.write(content)

        # Run lightweight preprocessing
        from app.jobs.preprocess import preprocess_media
        manifest = preprocess_media(storage)

        # Run minimal intelligence (fast signals only)
        from app.intelligence.audio_features import detect_silence
        from app.intelligence.shots import detect_shots
        from app.intelligence.motion import detect_motion
        from app.intelligence.faces import detect_faces

        silence = detect_silence(storage)
        shots = detect_shots(storage)
        motion = detect_motion(storage)
        faces = detect_faces(storage)

        # Diarization for speaker count
        diarization = None
        if settings.diarization_enabled:
            try:
                from app.intelligence.transcribe import transcribe_media
                from app.intelligence.diarization import diarize
                transcribe_media(storage)
                diarization = diarize(storage, max_speakers=settings.diarization_max_speakers)
            except Exception:
                pass

        signals = {
            "media_manifest": manifest,
            "transcript": storage.load_signal("transcript") if storage.has_json("signals", "transcript") else {},
            "silence": silence,
            "audio_energy": {},
            "shots": shots,
            "motion": motion,
            "faces": faces,
            "diarization": diarization,
            "visual_scores": None,
        }

        # Visual scoring if enabled
        if settings.visual_scoring_enabled:
            try:
                from app.intelligence.visual_scoring import compute_visual_scores
                visual_scores = compute_visual_scores(prompt, storage, shots)
                signals["visual_scores"] = visual_scores
            except Exception:
                pass

        # Classify
        from app.agents.content_classifier import classify_content
        from app.agents.strategy_router import get_strategy

        classification = classify_content(prompt, signals, storage)
        strategy = get_strategy(classification, prompt)

        return {
            "analysis_id": analysis_id,
            "video_type": classification["video_type"],
            "video_type_confidence": classification["video_type_confidence"],
            "video_type_scores": classification["video_type_scores"],
            "user_intent": classification["user_intent"],
            "user_intent_confidence": classification["user_intent_confidence"],
            "warnings": classification.get("warnings", []),
            "strategy_summary": {
                "operations": strategy["operations"],
                "energy": strategy["energy"],
                "caption_style": strategy["caption_config"]["style"],
                "speaker_tags": strategy["caption_config"]["speaker_tags"],
                "story_structure": strategy["story_structure"],
            },
        }

    except Exception as e:
        log.error("Analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    finally:
        # Clean up analysis files (they're temporary)
        import shutil
        try:
            shutil.rmtree(storage.job_dir(), ignore_errors=True)
        except Exception:
            pass
