from fastapi import APIRouter, UploadFile, File, Form
import uuid
import os

router = APIRouter()

BASE_PATH = "storage/jobs"

@router.post("/")
async def create_job(
    prompt: str = Form(...),
    files: list[UploadFile] = File(...)
):

    job_id = str(uuid.uuid4())

    job_dir = os.path.join(BASE_PATH, job_id)

    os.makedirs(job_dir + "/raw", exist_ok=True)

    for file in files:
        path = os.path.join(job_dir, "raw", file.filename)

        with open(path, "wb") as f:
            f.write(await file.read())

    return {
        "job_id": job_id,
        "status": "uploaded"
    }