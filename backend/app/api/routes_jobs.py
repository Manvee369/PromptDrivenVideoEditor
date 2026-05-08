"""Job API routes — create, poll status, download output, analyze."""

import asyncio
import json
import secrets
import shutil
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import settings
from app.core.logger import get_logger
from app.db.jobs_db import JobRecord, JobStatus, jobs_db
from app.agents.captions import STYLE_PRESETS
from app.db.jobs_db import TERMINAL_STATUSES
from app.render.color_grading import COLOR_GRADE_PRESET_NAMES
from app.dsl.schema import Timeline
from app.dsl.validators import validate_timeline
from app.jobs.events import JobEvents
from app.jobs.janitor import cleanup_intermediates
from app.jobs.pipeline import rerender_only, run_pipeline
from app.worker.queue import enqueue
from app.storage.storage_manager import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    StorageManager,
)
from app.utils.ffmpeg_utils import FFmpegError, probe_media

log = get_logger(__name__)
router = APIRouter()

ALLOWED_EXTENSIONS = VIDEO_EXTENSIONS | AUDIO_EXTENSIONS | IMAGE_EXTENSIONS


# --- Upload helpers ---------------------------------------------------------


def _validate_file_count(files: List[UploadFile] | None) -> List[UploadFile]:
    """Reject empty or oversized file lists."""
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if len(files) > settings.max_files_per_job:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files ({len(files)} > {settings.max_files_per_job} limit)",
        )
    return files


def _check_extension(filename: str) -> None:
    """Reject files whose extension isn't in our media whitelist."""
    if not filename:
        raise HTTPException(status_code=400, detail="File has no name")
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Extension '{ext}' not allowed. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )


async def _stream_to_disk(file: UploadFile, dest: Path) -> int:
    """Write the upload to disk in chunks, enforcing the size cap.
    Returns total bytes written. Removes the partial file on failure."""
    total = 0
    limit = settings.max_upload_bytes
    chunk_size = settings.upload_chunk_size

    try:
        with open(dest, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise HTTPException(
                        status_code=413,
                        detail=(
                            f"File '{file.filename}' exceeds "
                            f"{limit / 1024 / 1024:.0f}MB upload limit"
                        ),
                    )
                f.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}") from e

    return total


def _probe_or_reject(path: Path) -> None:
    """Run ffprobe; reject the upload if not a valid media file or zero-duration."""
    try:
        info = probe_media(path)
    except (FFmpegError, Exception) as e:
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"File '{path.name}' is not a valid media file: {e}",
        ) from e

    duration = float(info.get("format", {}).get("duration", 0) or 0)
    if duration <= 0:
        path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"File '{path.name}' has zero duration",
        )


async def _save_uploads(
    files: List[UploadFile],
    storage: StorageManager,
    *,
    role: str = "video",
    skip_probe: bool = False,
) -> list[str]:
    """Validate, stream, and probe each file. Cleans up partial state on failure.

    Returns the list of saved filenames so the caller can record their roles.
    `skip_probe=True` is useful for image uploads (ffprobe can be picky on
    static images via the same flag set we use for video).
    """
    raw_dir = storage.stage_dir("raw")
    saved: list[Path] = []

    try:
        for file in files:
            _check_extension(file.filename)
            dest = raw_dir / file.filename
            size = await _stream_to_disk(file, dest)
            saved.append(dest)
            log.info("Uploaded %s as %s (%d bytes) for job %s",
                     file.filename, role, size, storage.job_id)
            if not skip_probe:
                _probe_or_reject(dest)
    except HTTPException:
        # Roll back any partial files so we don't leave orphans on disk.
        for p in saved:
            p.unlink(missing_ok=True)
        raise

    return [p.name for p in saved]


def _check_download_token(job: JobRecord, token: str | None) -> None:
    """Enforce per-job download token if configured. Constant-time compare."""
    if not settings.download_token_required:
        return
    if not token or not secrets.compare_digest(token, job.download_token):
        raise HTTPException(status_code=403, detail="Invalid or missing download token")


# --- Routes -----------------------------------------------------------------


@router.post("/", summary="Create Job")
async def create_job(
    background_tasks: BackgroundTasks,
    prompt: str = Form(...),
    files: List[UploadFile] = None,
    music_files: List[UploadFile] = None,
    voiceover_files: List[UploadFile] = None,
    caption_style: str | None = Form(None),
    color_grade: str | None = Form(None),
    analysis_id: str | None = Form(None),
):
    """Upload files and start the editing pipeline.

    Form fields:
        files[]:       required. Source video(s).
        music_files[]: optional. Audio used as background music.
        voiceover_files[]: optional. Audio overlaid as narration.
        analysis_id:   optional. If provided and the matching analyze-* job
                       directory is still on disk, its cached signals (transcript,
                       diarization, visual scores, etc.) are copied into this job
                       so the pipeline skips those expensive ML stages entirely.

    Returns the new job_id and its download_token; the token is required on
    subsequent /download and /thumbnail requests when token enforcement is on.
    """
    # The primary files[] field is still required; music/voiceover are extras.
    files = _validate_file_count(files)

    # Validate caption style up front (small set, server-defined).
    if caption_style is not None and caption_style not in STYLE_PRESETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid caption_style '{caption_style}'. "
                   f"Allowed: {STYLE_PRESETS}",
        )
    if color_grade is not None and color_grade not in COLOR_GRADE_PRESET_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid color_grade '{color_grade}'. "
                   f"Allowed: {COLOR_GRADE_PRESET_NAMES}",
        )

    # Combined count cap covers all role buckets.
    total_count = len(files) + len(music_files or []) + len(voiceover_files or [])
    if total_count > settings.max_files_per_job:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Too many files ({total_count} > {settings.max_files_per_job} limit, "
                f"summed across files/music/voiceover)"
            ),
        )

    job_id = str(uuid.uuid4())
    storage = StorageManager(job_id)
    storage.ensure_dirs()

    try:
        roles: dict[str, str] = {}
        for name in await _save_uploads(files, storage, role="video"):
            # Default role inferred by extension; explicit override below.
            roles[name] = storage.role_of(name)

        if music_files:
            for name in await _save_uploads(music_files, storage, role="music"):
                roles[name] = "music"
        if voiceover_files:
            for name in await _save_uploads(voiceover_files, storage, role="voiceover"):
                roles[name] = "voiceover"

        storage.save_roles(roles)
    except HTTPException:
        # Tear down the empty job dir so we don't leave litter.
        shutil.rmtree(storage.job_dir(), ignore_errors=True)
        raise

    # --- Signal cache inheritance from /analyze ---
    # If the frontend passed back an analysis_id from a recent /analyze call,
    # and that temp directory is still on disk, copy its signals/ and prep/
    # artifacts into the real job. The pipeline's per-stage cache check will
    # then skip Whisper, diarization, SigLIP, etc. — they're already done.
    if analysis_id and analysis_id.startswith("analyze-"):
        analyze_storage = StorageManager(analysis_id)
        analyze_dir = analyze_storage.job_dir()
        if analyze_dir.exists():
            for stage in ("signals", "prep"):
                src = analyze_dir / stage
                dst = storage.job_dir() / stage
                if src.exists():
                    shutil.copytree(src, dst, dirs_exist_ok=True)
            log.info(
                "[%s] Inherited cached signals from analyze job %s — skipping ML stages",
                job_id, analysis_id,
            )
            # Clean up the temp analyze dir now that we've consumed it.
            shutil.rmtree(analyze_dir, ignore_errors=True)
        else:
            log.info("[%s] analysis_id %s not found on disk — running full pipeline",
                     job_id, analysis_id)

    record = jobs_db.create(
        job_id, prompt,
        caption_style=caption_style,
        color_grade=color_grade,
    )
    enqueue(run_pipeline, job_id, prompt, fallback_add_task=background_tasks.add_task)

    return {
        "job_id": job_id,
        "status": "created",
        "download_token": record.download_token,
    }


@router.get("/")
async def list_jobs():
    """List all jobs with their status."""
    return [job.model_dump() for job in jobs_db.list_jobs()]


@router.get("/caption-styles")
async def caption_style_presets():
    """Return the list of supported caption_style values for the New-Job form."""
    return {"presets": STYLE_PRESETS}


@router.get("/color-grades")
async def color_grade_presets():
    """Return the list of supported color_grade values for the New-Job form."""
    return {"presets": COLOR_GRADE_PRESET_NAMES}


@router.get("/{job_id}")
async def get_job(job_id: str):
    """Get job status and details (includes the download_token)."""
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.model_dump()


@router.post("/{job_id}/rerun")
async def rerun_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
):
    """Re-run the pipeline for an existing job.

    Per-stage artifacts already on disk are reused, so an INTERRUPTED job
    typically resumes from where it stopped. Pass ?force=true to discard
    cached artifacts and start over.
    """
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    storage = StorageManager(job_id)
    if not storage.job_dir().exists():
        raise HTTPException(status_code=404, detail="Job directory missing on disk")

    jobs_db.update_status(job_id, JobStatus.CREATED, progress=0.0, error=None)
    enqueue(run_pipeline, job_id, job.prompt, force, fallback_add_task=background_tasks.add_task)

    return {"job_id": job_id, "status": "restarted", "force": force}


@router.post("/{job_id}/cleanup")
async def cleanup_job(job_id: str):
    """Manually free intermediate disk space for a completed job.

    Removes prep/, render/, and signals/. Keeps raw/, dsl/, plans/, outputs/.
    The job remains downloadable; re-running the pipeline regenerates everything.
    """
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    storage = StorageManager(job_id)
    if not storage.job_dir().exists():
        raise HTTPException(status_code=404, detail="Job directory missing")

    report = cleanup_intermediates(storage)
    return {"job_id": job_id, **report}


@router.post("/{job_id}/rerender")
async def rerender_job(job_id: str, background_tasks: BackgroundTasks):
    """Re-render the final video from the existing DSL.

    Used after the timeline has been edited. Skips all upstream work — only
    runs the FFmpeg render stage. Requires dsl/timeline.json on disk.
    """
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    storage = StorageManager(job_id)
    if not storage.has_json("dsl", "timeline"):
        raise HTTPException(
            status_code=400,
            detail="No timeline DSL on disk — run the full pipeline first",
        )

    jobs_db.update_status(job_id, JobStatus.RENDERING, progress=0.5, error=None)
    enqueue(rerender_only, job_id, fallback_add_task=background_tasks.add_task)

    return {"job_id": job_id, "status": "rerendering"}


@router.get("/{job_id}/events")
async def job_events_sse(job_id: str):
    """Server-sent events stream for live job progress.

    Emits a JSON `data:` line whenever the job's status, top-level progress,
    or sub-stage progress changes. Closes when the job reaches a terminal
    state. Frontend can use a plain `EventSource` or fall back to polling
    `/jobs/{id}` if SSE isn't available.
    """
    if not jobs_db.get(job_id):
        raise HTTPException(status_code=404, detail="Job not found")

    storage = StorageManager(job_id)

    async def event_stream():
        events = JobEvents(storage)
        last_payload: dict | None = None

        # An initial probe so reconnecting clients immediately see current state.
        for _ in range(0, 24 * 60 * 60 * 2):  # ~24h soft cap at 0.5s ticks
            job = jobs_db.get(job_id)
            if not job:
                yield "event: error\ndata: {\"detail\":\"job vanished\"}\n\n"
                return

            sub = events.read()
            payload = {
                "status": job.status.value,
                "progress": round(job.progress, 4),
                "error": job.error,
                "substage": sub.get("substage"),
                "substage_progress": sub.get("progress"),
                "frame": sub.get("frame"),
                "fps": sub.get("fps"),
                "speed": sub.get("speed"),
                "message": sub.get("message"),
            }
            if payload != last_payload:
                yield f"data: {json.dumps(payload)}\n\n"
                last_payload = payload

            if job.status in TERMINAL_STATUSES:
                yield "event: done\ndata: {}\n\n"
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if proxied
        },
    )


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


@router.put("/{job_id}/timeline")
async def update_timeline(job_id: str, timeline_data: dict):
    """Replace the Timeline DSL for this job.

    Validates the payload against the DSL schema and storage state. Does NOT
    trigger a re-render — call POST /jobs/{id}/rerender after editing.

    Returns the validated Timeline as it was stored.
    """
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    storage = StorageManager(job_id)
    if not storage.job_dir().exists():
        raise HTTPException(status_code=404, detail="Job directory missing")

    # Schema validation: Pydantic catches type/structure errors with a 422.
    try:
        timeline = Timeline(**timeline_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid timeline schema: {e}") from e

    # Semantic validation: check source files exist, time ranges sane, etc.
    errors = validate_timeline(timeline, storage)
    if errors:
        raise HTTPException(
            status_code=422,
            detail={"message": "Timeline validation failed", "errors": errors},
        )

    storage.save_dsl(timeline.model_dump())
    log.info("Timeline updated for job %s: %d clips", job_id, len(timeline.clips))

    return timeline.model_dump()


@router.get("/{job_id}/download")
async def download_output(job_id: str, token: str | None = None):
    """Download the final rendered video. Requires ?token=... when enforcement is on."""
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    _check_download_token(job, token)

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
async def get_thumbnail(job_id: str, token: str | None = None):
    """Download the generated thumbnail. Requires ?token=... when enforcement is on."""
    job = jobs_db.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    _check_download_token(job, token)

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
    Content analysis: classifies video type and user intent, returns warnings.

    Runs the full intelligence stack (transcription, diarization, visual
    scoring, shot/motion/face detection) and caches all signals to disk.
    The returned `analysis_id` can be passed to POST /jobs/ so the real
    pipeline inherits the cached signals and skips expensive ML stages.

    The temp directory is kept alive on disk so POST /jobs/ can consume it.
    It is cleaned up by the caller on job creation, or by the janitor if
    the user never confirms.
    """
    files = _validate_file_count(files)

    analysis_id = f"analyze-{uuid.uuid4()}"
    storage = StorageManager(analysis_id)
    storage.ensure_dirs()

    # NOTE: no finally-cleanup here — the directory is intentionally kept
    # so POST /jobs/ can copy its signals. The janitor sweeps it up if
    # the user abandons the flow (it treats it like any orphaned job dir).
    try:
        await _save_uploads(files, storage)

        # Stage 1: preprocessing (audio extract + proxy)
        from app.jobs.preprocess import preprocess_media
        manifest = preprocess_media(storage)

        # Stage 2: fast signals
        from app.intelligence.audio_features import detect_silence
        from app.intelligence.shots import detect_shots
        from app.intelligence.motion import detect_motion
        from app.intelligence.faces import detect_faces

        silence = detect_silence(storage)
        shots = detect_shots(storage)
        motion = detect_motion(storage)
        faces = detect_faces(storage)

        # Stage 2: transcription + diarization (heavy, but cached for reuse)
        diarization = None
        if settings.diarization_enabled:
            try:
                from app.intelligence.transcribe import transcribe_media
                from app.intelligence.diarization import diarize
                transcribe_media(storage)  # saves signals/transcript.json
                diarization = diarize(storage, max_speakers=settings.diarization_max_speakers)
            except Exception as e:
                log.warning("Analyze: transcription/diarization failed (non-fatal): %s", e)

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

        # Stage 2: visual scoring (saves signals/visual_scores.json)
        if settings.visual_scoring_enabled:
            try:
                from app.intelligence.visual_scoring import compute_visual_scores
                visual_scores = compute_visual_scores(prompt, storage, shots)
                signals["visual_scores"] = visual_scores
            except Exception as e:
                log.warning("Analyze: visual scoring failed (non-fatal): %s", e)

        from app.agents.content_classifier import classify_content
        from app.agents.strategy_router import get_strategy

        classification = classify_content(prompt, signals, storage)
        strategy = get_strategy(classification, prompt)

        log.info(
            "Analyze %s complete: type=%s (%.2f), intent=%s — signals cached for reuse",
            analysis_id, classification["video_type"],
            classification["video_type_confidence"], classification["user_intent"],
        )

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

    except HTTPException:
        # On validation error, clean up immediately — user can't recover this.
        shutil.rmtree(storage.job_dir(), ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(storage.job_dir(), ignore_errors=True)
        log.error("Analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
