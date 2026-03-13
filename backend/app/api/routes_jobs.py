"""Job API routes — create, poll status, download output."""

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
