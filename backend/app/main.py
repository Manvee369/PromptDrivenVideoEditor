"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_jobs import router as jobs_router
from app.video_processing import remove_silence

app = FastAPI(
    title="Prompt-Driven Video Editor",
    version="0.1.0",
)

# CORS for future frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Job pipeline routes
app.include_router(jobs_router, prefix="/jobs", tags=["jobs"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/remove-silence")
def process_video(filename: str):
    """Standalone utility: remove silence from a video."""
    input_path = f"uploads/{filename}"
    output_path = f"processed/nosilence_{filename}"
    remove_silence(input_path, output_path)
    return {"status": "done", "output": output_path}
